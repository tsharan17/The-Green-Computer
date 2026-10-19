"""Account endpoints. Browser sessions use an HttpOnly cookie; scripts use bearer API tokens."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import service as auth
from app.auth.deps import COOKIE, CSRF_HEADER, Ctx, get_db, require_ctx
from app.config import get_settings
from app.db import repository as repo
from app.db.models import UserRow
from app.security import LIMITER, _int_env, client_ip, demo_mode
from app.services import audit
from app.services.seed import example_spec

router = APIRouter(prefix="/auth", tags=["auth"])


def _csrf(request: Request) -> None:
    """Unauthenticated state-changing calls (sign-in, sign-up, reset) also need the header, so
    another site cannot sign a visitor in to an attacker's account (login CSRF)."""
    if request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(403, "Missing X-GC-CSRF header (cross-site request refused).")


def _limit(request: Request, bucket: str, key: str, max_calls: int, window_s: float) -> None:
    wait = LIMITER.check(f"{bucket}:{key}", max_calls, window_s)
    if wait is not None:
        raise HTTPException(
            429, f"Too many attempts. Try again in about {int(wait) + 1} seconds.",
            headers={"Retry-After": str(int(wait) + 1)},
        )  # fmt: skip


def _raise(e: auth.AuthError) -> None:
    raise HTTPException(e.status, e.message) from e


def _set_cookie(request: Request, response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        COOKIE, token, max_age=s.session_days * 86400, httponly=True, samesite="lax",
        secure=s.cookie_secure or request.url.scheme == "https", path="/",
    )  # fmt: skip


def me_view(db: Session, user: UserRow, active_ws: int | None) -> dict[str, Any]:
    ws = [
        {"id": w.id, "name": w.name, "personal": w.personal, "legacy": w.legacy, "role": role}
        for w, role in auth.memberships(db, user.id)
    ]
    active = active_ws or (ws[0]["id"] if ws else None)
    return {
        "user": {"id": user.id, "email": user.email, "display_name": user.display_name,
                 "created_at": user.created_at.isoformat()},
        "workspaces": ws,
        "active_workspace_id": active,
        "role": next((w["role"] for w in ws if w["id"] == active), None),
    }  # fmt: skip


@router.get("/config")
def auth_config() -> dict[str, Any]:
    s = get_settings()
    from app.providers.email import make_email_sender

    return {
        "signup_allowed": s.allow_signup,
        "environment": s.environment,
        "email_delivery": make_email_sender().name,
        "password_min_length": 10,
        "demo_mode": demo_mode(),
    }


class SignupIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)
    display_name: str = Field("", max_length=120)


@router.post("/signup", status_code=201)
def signup(body: SignupIn, request: Request, response: Response,
           db: Session = Depends(get_db)) -> dict[str, Any]:  # fmt: skip
    _csrf(request)
    s = get_settings()
    if not s.allow_signup:
        raise HTTPException(403, "Sign-up is closed on this server. Ask an administrator.")
    ip = client_ip(request)
    _limit(request, "signup", ip, _int_env("GC_SIGNUP_RATE_PER_HOUR", 10, 30), 3600.0)
    try:
        user, info = auth.signup(db, body.email, body.password, body.display_name)
    except auth.AuthError as e:
        _raise(e)
    ws_id = info["workspace_id"]
    # A ready-made example so a new account can analyse something immediately.
    repo.create_project(db, example_spec(), ws_id, user.id)
    token, _ = auth.create_session(db, user, days=s.session_days, user_agent=request.headers.get(
        "user-agent", ""), ip=ip)  # fmt: skip
    audit.audit(db, "account.created", workspace_id=ws_id, user_id=user.id, target_type="user",
                target_id=user.id, ip=ip,
                detail={"claimed_legacy_workspace": info["claimed_legacy_workspace"]})  # fmt: skip
    _set_cookie(request, response, token)
    return me_view(db, user, ws_id)


class SigninIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)


@router.post("/signin")
def signin(body: SigninIn, request: Request, response: Response,
           db: Session = Depends(get_db)) -> dict[str, Any]:  # fmt: skip
    _csrf(request)
    s = get_settings()
    ip = client_ip(request)
    _limit(request, "signin-ip", ip, _int_env("GC_SIGNIN_RATE_PER_15MIN", 30, 60), 900.0)
    _limit(request, "signin-email", body.email.strip().lower()[:320], 10, 900.0)
    try:
        user = auth.authenticate(db, body.email, body.password)
    except auth.AuthError as e:
        audit.audit(db, "account.signin_failed", workspace_id=None, user_id=None, ip=ip,
                    detail={"reason": "bad credentials"})  # fmt: skip
        _raise(e)
    token, _ = auth.create_session(db, user, days=s.session_days, user_agent=request.headers.get(
        "user-agent", ""), ip=ip)  # fmt: skip
    ws = auth.default_workspace_id(db, user.id)
    audit.audit(db, "account.signed_in", workspace_id=ws, user_id=user.id, ip=ip)
    _set_cookie(request, response, token)
    return me_view(db, user, ws)


@router.post("/signout")
def signout(response: Response, ctx: Ctx = Depends(require_ctx),
            db: Session = Depends(get_db)) -> dict[str, bool]:  # fmt: skip
    auth.revoke_session(db, ctx.session.id, ctx.user_id)
    response.delete_cookie(COOKIE, path="/")
    return {"signed_out": True}


@router.get("/me")
def me(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    return me_view(db, ctx.user, ctx.workspace_id)


class ForgotIn(BaseModel):
    email: str = Field(max_length=320)


@router.post("/password/forgot", status_code=202)
def forgot(body: ForgotIn, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    _csrf(request)
    _limit(request, "forgot", client_ip(request), 10, 3600.0)
    s = get_settings()
    token = auth.request_reset(db, body.email, request.app.state.email_sender, s.public_url)
    out: dict[str, Any] = {
        "sent": True,
        "message": "If an account exists for that address, a reset link has been sent.",
    }
    if token and not s.is_production and request.app.state.email_sender.name == "console":
        # Development only: there is no mail server, so show the link that was "sent".
        out["dev_reset_url"] = f"{s.public_url}/#/reset?token={token}"
        out["dev_note"] = ("Development mode: email is printed to the server log instead of being "
                           "sent. This link is never shown when GC_ENV=production.")  # fmt: skip
    return out


class ResetIn(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(max_length=256)


@router.post("/password/reset")
def reset(body: ResetIn, request: Request, db: Session = Depends(get_db)) -> dict[str, bool]:
    _csrf(request)
    _limit(request, "reset", client_ip(request), 20, 3600.0)
    try:
        user = auth.reset_password(db, body.token, body.password)
    except auth.AuthError as e:
        _raise(e)
    audit.audit(db, "account.password_reset", workspace_id=auth.default_workspace_id(db, user.id),
                user_id=user.id, ip=client_ip(request))  # fmt: skip
    return {"reset": True}


class ChangeIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


@router.post("/password/change")
def change(body: ChangeIn, ctx: Ctx = Depends(require_ctx),
           db: Session = Depends(get_db)) -> dict[str, Any]:  # fmt: skip
    try:
        auth.change_password(db, ctx.user, body.current_password, body.new_password)
    except auth.AuthError as e:
        _raise(e)
    n = auth.revoke_all(db, ctx.user_id, except_id=ctx.session.id)
    audit.audit(db, "account.password_changed", workspace_id=ctx.workspace_id, user_id=ctx.user_id,
                ip=ctx.ip, detail={"other_sessions_signed_out": n})  # fmt: skip
    return {"changed": True, "other_sessions_signed_out": n}


PREF_KEYS = {"mode": ("simple", "engineering"), "onboarded": (True, False)}


@router.get("/preferences")
def get_preferences(ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    return {"mode": "simple", "onboarded": False, **(ctx.user.preferences or {})}


@router.put("/preferences")
def set_preferences(body: dict[str, Any], ctx: Ctx = Depends(require_ctx),
                    db: Session = Depends(get_db)) -> dict[str, Any]:  # fmt: skip
    """Presentation only: display density and whether the first-run guide was completed."""
    bad = [k for k, v in body.items() if k not in PREF_KEYS or v not in PREF_KEYS[k]]
    if bad:
        raise HTTPException(422, f"unknown preference or value: {', '.join(bad)}")
    user = db.get(UserRow, ctx.user_id)
    assert user is not None
    user.preferences = {**(user.preferences or {}), **body}
    db.commit()
    return {"mode": "simple", "onboarded": False, **user.preferences}


@router.get("/sessions")
def sessions(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)) -> list[dict]:
    rows = auth.list_sessions(db, ctx.user_id)
    for r in rows:
        r["current"] = r["id"] == ctx.session.id
    return rows


@router.post("/sessions/{session_id}/revoke")
def revoke(session_id: int, ctx: Ctx = Depends(require_ctx),
           db: Session = Depends(get_db)) -> dict[str, bool]:  # fmt: skip
    if not auth.revoke_session(db, session_id, ctx.user_id):
        raise HTTPException(404, "session not found")
    return {"revoked": True}


class TokenIn(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    days: int = Field(90, ge=1, le=365)


@router.post("/tokens", status_code=201)
def create_token(body: TokenIn, ctx: Ctx = Depends(require_ctx),
                 db: Session = Depends(get_db)) -> dict[str, Any]:  # fmt: skip
    """An API token for the CLI or scripts (Authorization: Bearer ...). Shown once."""
    token, row = auth.create_session(db, ctx.user, days=body.days, kind="api", label=body.label,
                                     ip=ctx.ip)  # fmt: skip
    audit.audit(db, "account.api_token_created", workspace_id=ctx.workspace_id,
                user_id=ctx.user_id, target_type="session", target_id=row.id, ip=ctx.ip,
                detail={"label": body.label})  # fmt: skip
    return {"id": row.id, "token": token, "expires_at": row.expires_at.isoformat(),
            "note": "Copy it now: it is not shown again."}  # fmt: skip


class DeleteIn(BaseModel):
    password: str = Field(max_length=256)
    confirm: str = Field(max_length=20)


@router.post("/account/delete")
def delete_account(body: DeleteIn, response: Response, request: Request,
                   ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:  # fmt: skip
    try:
        summary = auth.delete_account(db, ctx.user, body.password, body.confirm,
                                      request.app.state.blobs)  # fmt: skip
    except auth.AuthError as e:
        _raise(e)
    response.delete_cookie(COOKIE, path="/")
    return {"deleted": True, **summary.__dict__}
