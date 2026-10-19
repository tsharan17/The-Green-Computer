"""Safeguards for a public demo: rate limits, a switch for billed actions, security headers.

A judge-facing URL spends real credits (Token Factory tokens, Tavily searches, GPU time) and is
shared by strangers, so in demo mode (`GC_PUBLIC_DEMO=1`) billed or abusable actions are refused
and the Green Agent and the analysis endpoint are rate limited per client IP. Locally nothing here
restricts anything unless you set the limits yourself.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def demo_mode() -> bool:
    return _truthy(os.environ.get("GC_PUBLIC_DEMO"))


def _int_env(name: str, demo_default: int, local_default: int = 0) -> int:
    raw = os.environ.get(name)
    if raw not in (None, ""):
        try:
            return int(raw)
        except ValueError:
            pass
    return demo_default if demo_mode() else local_default


def client_ip(request: Request) -> str:
    """The caller's address. X-Forwarded-For is trusted only behind a known proxy."""
    if _truthy(os.environ.get("GC_TRUST_PROXY")):
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Sliding-window limiter, in memory (one process). max_calls <= 0 disables it."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, max_calls: int, window_s: float) -> float | None:
        """None if allowed, else seconds until the next call would be allowed."""
        if max_calls <= 0:
            return None
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_s:
                q.popleft()
            if len(q) >= max_calls:
                return window_s - (now - q[0])
            q.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


LIMITER = RateLimiter()


def _limit(request: Request, bucket: str, max_calls: int, window_s: float, what: str) -> None:
    wait = LIMITER.check(f"{bucket}:{client_ip(request)}", max_calls, window_s)
    if wait is not None:
        raise HTTPException(
            429,
            f"Too many {what} from your address. This public demo limits usage to protect its "
            f"credits; try again in about {int(wait) + 1} seconds.",
            headers={"Retry-After": str(int(wait) + 1)},
        )


def limit_agent(request: Request) -> None:
    _limit(request, "agent", _int_env("GC_AGENT_RATE_PER_HOUR", 40), 3600.0, "agent questions")


def limit_analyse(request: Request) -> None:
    _limit(request, "analyse", _int_env("GC_ANALYSE_RATE_PER_MIN", 30), 60.0, "analyses")


def block_in_demo(feature: str) -> None:
    """Refuse a billed or abusable action in the public demo."""
    if demo_mode():
        raise HTTPException(
            403,
            f"{feature} is turned off in the public demo because it spends real credits. "
            "Run your own copy (see the README) to use it.",
        )


def max_projects() -> int:
    return _int_env("GC_MAX_PROJECTS", 5000)


def max_custom_items() -> int:
    return _int_env("GC_MAX_CUSTOM_ITEMS", 50)


def max_upload_bytes(default: int) -> int:
    return min(default, _int_env("GC_MAX_UPLOAD_MB", 10) * 1024 * 1024) if demo_mode() else default


CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; frame-src 'self' about:; base-uri 'self'; "
    "form-action 'self'; object-src 'none'"
)


class OriginCheck(BaseHTTPMiddleware):
    """Refuse state-changing API calls whose Origin is neither this server nor an allowed origin
    (defence in depth on top of the SameSite cookie and the CSRF header)."""

    def __init__(self, app, allowed: tuple[str, ...] = ()) -> None:
        super().__init__(app)
        self.allowed = {o.rstrip("/") for o in allowed}

    async def dispatch(self, request: Request, call_next) -> Response:
        origin = request.headers.get("origin")
        if (
            origin
            and request.method not in ("GET", "HEAD", "OPTIONS")
            and request.url.path.startswith("/api/")
        ):
            own = f"{request.url.scheme}://{request.headers.get('host', '')}"
            if origin.rstrip("/") not in self.allowed | {own}:
                return Response(
                    '{"detail":"Cross-origin request refused."}', status_code=403,
                    media_type="application/json",
                )  # fmt: skip
        return await call_next(request)


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        if not request.url.path.startswith(("/docs", "/redoc", "/openapi")):
            resp.headers.setdefault("Content-Security-Policy", CSP)
        return resp
