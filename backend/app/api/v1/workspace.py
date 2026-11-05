"""Workspaces, members, uploaded files, audit trail and usage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth import service as auth
from app.auth.deps import Ctx, get_db, require_ctx, require_verified, require_writer
from app.config import get_settings
from app.db.models import ArtifactRow, InvitationRow, MembershipRow, UserRow, WorkspaceRow
from app.security import LIMITER, _int_env, attachment, max_workspaces_per_user
from app.services import audit, intake

router = APIRouter(tags=["workspace"])


def _owner(ctx: Ctx) -> None:
    if ctx.role != "owner":
        raise HTTPException(403, "Only a workspace owner can do this.")


@router.get("/workspaces")
def list_workspaces(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)) -> list[dict]:
    return [{"id": w.id, "name": w.name, "personal": w.personal, "legacy": w.legacy, "role": r}
            for w, r in auth.memberships(db, ctx.user_id)]  # fmt: skip


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.post("/workspaces", status_code=201)
def create_workspace(body: WorkspaceIn, ctx: Ctx = Depends(require_verified),
                     db: Session = Depends(get_db)) -> dict[str, Any]:  # fmt: skip
    cap = max_workspaces_per_user()
    owned = db.scalar(select(func.count()).select_from(MembershipRow).where(
        MembershipRow.user_id == ctx.user_id, MembershipRow.role == "owner")) or 0  # fmt: skip
    if cap and owned >= cap:
        raise HTTPException(503, f"You have reached the limit of {cap} workspaces on this service.")
    ws = auth.create_workspace(db, ctx.user, body.name.strip(), personal=False)
    db.commit()
    audit.audit(db, "workspace.created", workspace_id=ws.id, user_id=ctx.user_id,
                target_type="workspace", target_id=ws.id, ip=ctx.ip)  # fmt: skip
    return {"id": ws.id, "name": ws.name, "personal": False, "legacy": False, "role": "owner"}


@router.patch("/workspaces/current")
def rename_workspace(body: WorkspaceIn, ctx: Ctx = Depends(require_ctx),
                     db: Session = Depends(get_db)) -> dict[str, Any]:  # fmt: skip
    _owner(ctx)
    ws = db.get(WorkspaceRow, ctx.workspace_id)
    assert ws is not None
    ws.name = body.name.strip()
    db.commit()
    return {"id": ws.id, "name": ws.name}


@router.get("/workspaces/current/members")
def members(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(MembershipRow, UserRow).join(UserRow, UserRow.id == MembershipRow.user_id)
        .where(MembershipRow.workspace_id == ctx.workspace_id).order_by(MembershipRow.id)
    ).all()  # fmt: skip
    return [{"user_id": u.id, "email": u.email, "display_name": u.display_name, "role": m.role}
            for m, u in rows]  # fmt: skip


class MemberIn(BaseModel):
    email: str = Field(max_length=320)
    role: Literal["owner", "editor", "viewer"] = "editor"


INVITE_DAYS = 14
MAX_PENDING_INVITES = 50


def _aware(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=UTC)


@router.post("/workspaces/current/members", status_code=201)
def add_member(body: MemberIn, request: Request, background: BackgroundTasks, ctx: Ctx = Depends(require_verified),
               db: Session = Depends(get_db)) -> dict[str, Any]:  # fmt: skip
    """Invite someone to this workspace. They join only when they accept from their own account, and
    the answer is the same whether or not that address has an account."""
    _owner(ctx)
    ws = db.get(WorkspaceRow, ctx.workspace_id)
    if ws is not None and ws.personal:
        raise HTTPException(422, "Personal workspaces are private. Create a team workspace to share.")
    try:
        email = auth.normalise_email(body.email)
    except auth.AuthError as e:
        raise HTTPException(e.status, e.message) from e
    member = db.scalars(select(UserRow).where(UserRow.email == email)).first()
    if member is not None and auth.role_in(db, member.id, ctx.workspace_id):
        raise HTTPException(409, "Already a member.")
    if LIMITER.check(f"invites:u{ctx.user_id}", _int_env("GC_MAX_INVITES_PER_DAY", 30), 86400.0) is not None:
        raise HTTPException(429, "You have sent too many invitations today. Try again tomorrow.")
    row = db.scalars(select(InvitationRow).where(
        InvitationRow.workspace_id == ctx.workspace_id, InvitationRow.email == email)).first()  # fmt: skip
    if row is None:
        pending = db.scalar(select(func.count()).select_from(InvitationRow).where(
            InvitationRow.workspace_id == ctx.workspace_id)) or 0  # fmt: skip
        if pending >= MAX_PENDING_INVITES:
            raise HTTPException(422, "Too many open invitations. Cancel some first.")
        row = InvitationRow(workspace_id=ctx.workspace_id, email=email)
        db.add(row)
    row.role, row.invited_by = body.role, ctx.user_id
    row.expires_at = datetime.now(UTC) + timedelta(days=INVITE_DAYS)
    db.commit()
    audit.audit(db, "workspace.member_invited", workspace_id=ctx.workspace_id, user_id=ctx.user_id,
                target_type="invitation", target_id=row.id, detail={"role": body.role}, ip=ctx.ip)  # fmt: skip
    url = get_settings().public_url
    background.add_task(
        request.app.state.email_sender.send, email, "You have been invited to a team on The Green Computer",
        f"{ctx.user.email} invited you to the workspace \"{ws.name if ws else ''}\" as {body.role}.\n\n"
        f"Sign in or create an account with this address to accept or decline:\n{url}/#/account\n\n"
        f"The invitation lasts {INVITE_DAYS} days. If you do not know this person, ignore this email.",
    )  # fmt: skip
    return {"invited": True, "id": row.id, "email": email, "role": body.role}


def _invite_view(row: InvitationRow, ws_name: str | None = None) -> dict[str, Any]:
    out = {"id": row.id, "email": row.email, "role": row.role, "expires_at": _aware(row.expires_at).isoformat()}
    return {**out, "workspace": ws_name} if ws_name is not None else out


@router.get("/workspaces/current/invitations")
def workspace_invitations(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)) -> list[dict]:
    _owner(ctx)
    rows = db.scalars(select(InvitationRow).where(InvitationRow.workspace_id == ctx.workspace_id).order_by(InvitationRow.id))
    return [_invite_view(r) for r in rows]


@router.delete("/workspaces/current/invitations/{invitation_id}")
def cancel_invitation(invitation_id: int, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)) -> dict[str, bool]:
    _owner(ctx)
    row = db.get(InvitationRow, invitation_id)
    if row is None or row.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "invitation not found")
    db.delete(row)
    db.commit()
    return {"cancelled": True}


def _my_invitation(db: Session, ctx: Ctx, invitation_id: int) -> InvitationRow:
    row = db.get(InvitationRow, invitation_id)
    if row is None or row.email != ctx.user.email or _aware(row.expires_at) <= datetime.now(UTC):
        raise HTTPException(404, "This invitation does not exist or has expired.")
    return row


@router.get("/invitations")
def my_invitations(ctx: Ctx = Depends(require_verified), db: Session = Depends(get_db)) -> list[dict]:
    """Invitations sent to the signed-in address. A confirmed address is what proves they are yours."""
    rows = db.execute(
        select(InvitationRow, WorkspaceRow).join(WorkspaceRow, WorkspaceRow.id == InvitationRow.workspace_id)
        .where(InvitationRow.email == ctx.user.email).order_by(InvitationRow.id)
    ).all()  # fmt: skip
    return [_invite_view(i, w.name) for i, w in rows if _aware(i.expires_at) > datetime.now(UTC)]


@router.post("/invitations/{invitation_id}/accept")
def accept_invitation(invitation_id: int, ctx: Ctx = Depends(require_verified), db: Session = Depends(get_db)) -> dict[str, Any]:
    row = _my_invitation(db, ctx, invitation_id)
    ws, role = row.workspace_id, row.role
    if not auth.role_in(db, ctx.user_id, ws):
        db.add(MembershipRow(workspace_id=ws, user_id=ctx.user_id, role=role))
    db.delete(row)
    db.commit()
    audit.audit(db, "workspace.member_added", workspace_id=ws, user_id=ctx.user_id,
                target_type="user", target_id=ctx.user_id, detail={"role": role}, ip=ctx.ip)  # fmt: skip
    return {"workspace_id": ws, "role": role}


@router.post("/invitations/{invitation_id}/decline")
def decline_invitation(invitation_id: int, ctx: Ctx = Depends(require_verified), db: Session = Depends(get_db)) -> dict[str, bool]:
    db.delete(_my_invitation(db, ctx, invitation_id))
    db.commit()
    return {"declined": True}


@router.delete("/workspaces/current/members/{user_id}")
def remove_member(user_id: int, ctx: Ctx = Depends(require_ctx),
                  db: Session = Depends(get_db)) -> dict[str, bool]:  # fmt: skip
    _owner(ctx)
    if user_id == ctx.user_id:
        raise HTTPException(422, "You cannot remove yourself; delete your account or hand over first.")
    n = db.execute(delete(MembershipRow).where(
        MembershipRow.workspace_id == ctx.workspace_id, MembershipRow.user_id == user_id
    )).rowcount  # type: ignore[attr-defined]  # fmt: skip
    db.commit()
    if not n:
        raise HTTPException(404, "member not found")
    audit.audit(db, "workspace.member_removed", workspace_id=ctx.workspace_id,
                user_id=ctx.user_id, target_type="user", target_id=user_id, ip=ctx.ip)  # fmt: skip
    return {"removed": True}


# --- files --------------------------------------------------------------------------------


@router.get("/artifacts")
def artifacts(project_id: int | None = None, kind: str | None = None,
              ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)) -> list[dict]:  # fmt: skip
    return intake.list_artifacts(db, ctx.workspace_id, project_id, kind)


@router.get("/artifacts/{artifact_id}")
def artifact(artifact_id: int, ctx: Ctx = Depends(require_ctx),
             db: Session = Depends(get_db)) -> dict[str, Any]:  # fmt: skip
    row = intake.get_artifact(db, ctx.workspace_id, artifact_id)
    if row is None:
        raise HTTPException(404, "file not found")
    return intake.artifact_view(row)


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: int, request: Request, ctx: Ctx = Depends(require_ctx),
                      db: Session = Depends(get_db)) -> Response:  # fmt: skip
    row = intake.get_artifact(db, ctx.workspace_id, artifact_id)
    if row is None or row.blob_key is None:
        raise HTTPException(404, "file not found (refused uploads are not stored)")
    data = request.app.state.blobs.get(row.blob_key)
    return Response(data, media_type="application/octet-stream", headers={
        "Content-Disposition": attachment(row.filename),
        "X-Content-Type-Options": "nosniff"})  # fmt: skip


@router.delete("/artifacts/{artifact_id}")
def delete_artifact(artifact_id: int, request: Request, ctx: Ctx = Depends(require_writer),
                    db: Session = Depends(get_db)) -> dict[str, bool]:  # fmt: skip
    """Remove the stored bytes; the metadata stays (marked deleted) for the audit trail."""
    row = intake.get_artifact(db, ctx.workspace_id, artifact_id)
    if row is None:
        raise HTTPException(404, "file not found")
    key = row.blob_key
    row.deleted_at = datetime.now(UTC)
    row.blob_key = None
    db.commit()
    if key and not db.scalars(select(ArtifactRow.id).where(
        ArtifactRow.blob_key == key, ArtifactRow.deleted_at.is_(None)
    )).first():  # fmt: skip
        request.app.state.blobs.delete(key)
    audit.audit(db, "file.deleted", workspace_id=ctx.workspace_id, user_id=ctx.user_id,
                target_type="artifact", target_id=artifact_id,
                detail={"filename": row.filename}, ip=ctx.ip)  # fmt: skip
    return {"deleted": True}


# --- audit and usage ----------------------------------------------------------------------


@router.get("/audit")
def audit_log(project_id: int | None = None, limit: int = 200, ctx: Ctx = Depends(require_ctx),
              db: Session = Depends(get_db)) -> list[dict]:  # fmt: skip
    return audit.audit_list(db, ctx.workspace_id, min(max(limit, 1), 1000), project_id)


@router.get("/usage")
def usage(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    return audit.usage_summary(db, ctx.workspace_id)


# --- data: retention, export --------------------------------------------------------------------


@router.get("/workspaces/current/retention")
def retention_rules(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.services import workspace_data as wd

    return {"rules": wd.get_retention(db, ctx.workspace_id), "labels": wd.RULES, "audit_min_days": wd.AUDIT_MIN_DAYS}


@router.put("/workspaces/current/retention")
def set_retention_rules(body: dict[str, int | None], ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Owner only. Days to keep each category; empty keeps it for ever."""
    from app.services import workspace_data as wd

    _owner(ctx)
    try:
        return {"rules": wd.set_retention(db, ctx.workspace_id, ctx.user_id, body)}
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/workspaces/current/retention/apply")
def apply_retention_rules(request: Request, dry_run: bool = True, ctx: Ctx = Depends(require_ctx),
                          db: Session = Depends(get_db)) -> dict[str, Any]:  # fmt: skip
    """Owner only. With dry_run (the default) nothing is deleted; the counts say what would go."""
    from app.services import workspace_data as wd

    _owner(ctx)
    return wd.apply_retention(db, request.app.state.blobs, ctx.workspace_id, ctx.user_id, dry_run)


@router.get("/workspaces/current/export")
def export_workspace(request: Request, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)) -> Response:
    """Owner only. Everything the workspace holds, as one zip with a hashed manifest."""
    from app.services import workspace_data as wd

    _owner(ctx)
    data, _ = wd.export_workspace(db, request.app.state.blobs, ctx.workspace_id, ctx.user_id)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="workspace-{ctx.workspace_id}-{stamp}.zip"'})  # fmt: skip
