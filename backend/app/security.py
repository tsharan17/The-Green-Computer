"""Safeguards for a shared server: rate limits, caps, a switch for heavy actions, security headers.

A public server is shared by strangers. Two modes turn the safeguards on:
- `GC_HOSTED=1`, the hosted product: rate limits and caps, uploads capped (`GC_MAX_UPLOAD_MB`, default
  50), and nothing is executed on the server (model runs and INT8 conversion belong on the user's own
  machine or a paired device). It also requires `GC_SECRET_KEY` and `GC_AGENT_SIGNING_SECRET`, since
  hosted disks are usually wiped on restart.
- `GC_PUBLIC_DEMO=1`, a throwaway demo: the same limits, uploads capped at 10 MB, and a demo banner.
Locally nothing here restricts anything unless you set the limits yourself.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import quote

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def demo_mode() -> bool:
    return _truthy(os.environ.get("GC_PUBLIC_DEMO"))


def hosted() -> bool:
    return _truthy(os.environ.get("GC_HOSTED"))


def shared_server() -> bool:
    """Strangers share this server (hosted product or public demo): limits apply by default."""
    return hosted() or demo_mode()


HOSTED_SECRETS = ("GC_SECRET_KEY", "GC_AGENT_SIGNING_SECRET")


def check_hosted_secrets() -> None:
    """Hosted servers must not create keys on a disk that may be wiped: refuse to start without them."""
    missing = [k for k in HOSTED_SECRETS if not os.environ.get(k)]
    if hosted() and missing:
        raise RuntimeError(f"GC_HOSTED=1 needs {', '.join(missing)} set (random values of 32+ characters). "
                           "Without them, sign-in secrets and paired devices break on every restart.")  # fmt: skip


def _int_env(name: str, demo_default: int, local_default: int = 0) -> int:
    raw = os.environ.get(name)
    if raw not in (None, ""):
        try:
            return int(raw)
        except ValueError:
            pass
    return demo_default if shared_server() else local_default


def client_ip(request: Request) -> str:
    """The caller's address, used for rate limits and the audit log.

    Behind a known proxy (GC_TRUST_PROXY=1) the caller can write anything into X-Forwarded-For and
    proxies only append, so the leftmost entries prove nothing. Trust, in order: the single header the
    proxy overwrites (GC_CLIENT_IP_HEADER, e.g. CF-Connecting-IP), then the entry added by the outermost
    of GC_TRUSTED_PROXY_HOPS proxies, counted from the right.
    """
    if _truthy(os.environ.get("GC_TRUST_PROXY")):
        name = os.environ.get("GC_CLIENT_IP_HEADER", "").strip()
        value = request.headers.get(name.lower(), "").strip() if name else ""
        if value:
            return value
        entries = [e.strip() for e in request.headers.get("x-forwarded-for", "").split(",") if e.strip()]
        if entries:
            hops = max(_int_env("GC_TRUSTED_PROXY_HOPS", 1, 1), 1)
            return entries[-min(hops, len(entries))]
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


class DatabaseRateLimiter:
    """Shared across processes and machines: sliding-window counters in the `rate_limits` table.

    The estimate is previous_window * (share of it still inside the window) + current_window, the
    usual sliding-window counter. Each call increments atomically (INSERT .. ON CONFLICT DO UPDATE ..
    RETURNING), so concurrent workers cannot both slip under the limit.
    """

    def __init__(self, engine) -> None:  # type: ignore[no-untyped-def]
        self.engine = engine
        self.dialect = engine.dialect.name
        self._calls = 0

    def _incr(self, conn, key: str, start: int) -> int:  # type: ignore[no-untyped-def]
        from sqlalchemy.dialects import postgresql, sqlite

        from app.db.models import RateLimitRow

        t = RateLimitRow.__table__
        ins = (postgresql.insert if self.dialect == "postgresql" else sqlite.insert)(RateLimitRow).values(key=key, window_start=start, count=1)
        stmt = ins.on_conflict_do_update(index_elements=["key", "window_start"], set_={"count": t.c.count + 1}).returning(t.c.count)
        return int(conn.execute(stmt).scalar_one())

    def check(self, key: str, max_calls: int, window_s: float) -> float | None:
        if max_calls <= 0:
            return None
        from sqlalchemy import delete, select

        from app.db.models import RateLimitRow

        w = max(int(window_s), 1)
        now = time.time()
        cur = int(now // w) * w
        k = f"{key}|{w}"[:200]
        t = RateLimitRow.__table__
        with self.engine.begin() as conn:
            n = self._incr(conn, k, cur)
            prev = conn.execute(select(t.c.count).where(t.c.key == k, t.c.window_start == cur - w)).scalar() or 0
            self._calls += 1
            if self._calls % 500 == 0:  # occasional clean-up of windows nobody can still need
                conn.execute(delete(RateLimitRow).where(RateLimitRow.window_start < int(now) - 2 * 86400))
        estimate = prev * (1 - (now - cur) / w) + n
        if estimate > max_calls:
            return max(w - (now - cur), 1.0)
        return None

    def reset(self) -> None:
        from sqlalchemy import delete

        from app.db.models import RateLimitRow

        with self.engine.begin() as conn:
            conn.execute(delete(RateLimitRow))


class SharedLimiter:
    """The limiter every route uses; the backend is chosen when the app starts (configure_limiter)."""

    def __init__(self) -> None:
        self.backend: RateLimiter | DatabaseRateLimiter = RateLimiter()
        self.kind = "memory"

    def check(self, key: str, max_calls: int, window_s: float) -> float | None:
        return self.backend.check(key, max_calls, window_s)

    def reset(self) -> None:
        self.backend.reset()


LIMITER = SharedLimiter()


def configure_limiter(engine) -> str:  # type: ignore[no-untyped-def]
    """GC_RATE_LIMIT_BACKEND = memory | database | auto (default: database on PostgreSQL, where
    several workers share one database; memory on SQLite, a single process)."""
    choice = os.environ.get("GC_RATE_LIMIT_BACKEND", "auto").lower()
    if choice == "database" or (choice == "auto" and engine.dialect.name == "postgresql"):
        if engine.dialect.name in ("postgresql", "sqlite"):
            LIMITER.backend, LIMITER.kind = DatabaseRateLimiter(engine), "database"
            return LIMITER.kind
    LIMITER.backend, LIMITER.kind = RateLimiter(), "memory"
    return LIMITER.kind


def _limit(request: Request, bucket: str, max_calls: int, window_s: float, what: str) -> None:
    wait = LIMITER.check(f"{bucket}:{client_ip(request)}", max_calls, window_s)
    if wait is not None:
        raise HTTPException(
            429,
            f"Too many {what} from your address. This service limits usage to keep it fair for "
            f"everyone; try again in about {int(wait) + 1} seconds.",
            headers={"Retry-After": str(int(wait) + 1)},
        )


def limit_datasheet(request: Request) -> None:
    """Reading a datasheet PDF is CPU heavy: a few per hour in the demo."""
    _limit(request, "datasheet", _int_env("GC_DATASHEET_RATE_PER_HOUR", 5), 3600.0, "datasheet imports")


def limit_analyse(request: Request) -> None:
    _limit(request, "analyse", _int_env("GC_ANALYSE_RATE_PER_MIN", 30), 60.0, "analyses")


SERVER_RUNS_OFF = ("{feature} is off on this hosted service: it would run your model on the shared server. "
                   "Pair your own device under Run on a device, or run The Green Computer on your own machine.")


def block_on_shared_server(feature: str) -> None:
    """Refuse an action that executes user models on a shared server."""
    if shared_server():
        raise HTTPException(403, SERVER_RUNS_OFF.format(feature=feature))


def max_projects() -> int:
    return _int_env("GC_MAX_PROJECTS", 5000)


def max_custom_items() -> int:
    return _int_env("GC_MAX_CUSTOM_ITEMS", 50)


def max_workspaces_per_user() -> int:
    return _int_env("GC_MAX_WORKSPACES_PER_USER", 5)


def max_workspace_storage_bytes() -> int:
    """Kept file bytes per workspace. Files live in the database on the free plan, so this matters."""
    return _int_env("GC_MAX_WORKSPACE_STORAGE_MB", 150) * 1024 * 1024


_ANALYSES: threading.BoundedSemaphore | None = None
_ANALYSES_LOCK = threading.Lock()


@contextmanager
def analysis_slot() -> Iterator[None]:
    """On a shared server, only so many searches run at once; the next person is told to retry."""
    global _ANALYSES
    if not shared_server():
        yield
        return
    with _ANALYSES_LOCK:
        if _ANALYSES is None:
            _ANALYSES = threading.BoundedSemaphore(_int_env("GC_MAX_CONCURRENT_ANALYSES", 2))
    if not _ANALYSES.acquire(blocking=False):
        raise HTTPException(503, "The service is busy with other analyses. Try again in a moment.",
                            headers={"Retry-After": "15"})  # fmt: skip
    try:
        yield
    finally:
        _ANALYSES.release()


def limit_daily_runs(user_id: int) -> None:
    """A daily allowance per account, which changing address does not reset."""
    wait = LIMITER.check(f"runs:u{user_id}", _int_env("GC_MAX_RUNS_PER_DAY", 300), 86400.0)
    if wait is not None:
        raise HTTPException(
            429, "You have reached today's limit of analyses on this free service. Try again tomorrow.",
            headers={"Retry-After": str(int(wait) + 1)},
        )  # fmt: skip


def attachment(filename: str) -> str:
    """A Content-Disposition value that is safe for any file name (RFC 6266 and RFC 5987)."""
    plain = "".join(c if c.isascii() and c.isprintable() and c not in '"\\;' else "_" for c in filename) or "download"
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(filename, safe='')}"


def max_upload_bytes(default: int) -> int:
    if not shared_server():
        return default
    return min(default, _int_env("GC_MAX_UPLOAD_MB", 50 if hosted() else 10) * 1024 * 1024)


# Routes whose body is a file; every other route takes a small JSON document.
FILE_BODY_PATHS = ("/models/upload", "/intake/upload", "/files/inspect", "/measurements/import")
LARGEST_UPLOAD_BYTES = 100 * 1024 * 1024


def _body_limit(path: str) -> int:
    """Largest request body for this path in bytes; 0 means no limit (a private local install)."""
    if not shared_server():
        return 0
    if path.endswith(FILE_BODY_PATHS):
        return max_upload_bytes(LARGEST_UPLOAD_BYTES)
    return _int_env("GC_MAX_JSON_BODY_KB", 2048) * 1024


def _too_large(limit: int) -> str:
    size = f"{limit // (1024 * 1024)} MB" if limit >= 1024 * 1024 else f"{limit // 1024} KB"
    return f"file too large (limit {size})"


class IdBounds:
    """A path id too long to be any real row is simply not found, whatever the database thinks of it."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and any(s.isdigit() and len(s) > 18 for s in scope["path"].split("/")):
            await JSONResponse({"detail": "Not found."}, status_code=404)(scope, receive, send)
            return
        await self.app(scope, receive, send)


class BodyLimit:
    """Refuse oversized request bodies while they arrive, so none is ever held whole in memory.

    Content-Length is checked first, and the bytes are counted too because a chunked request need not
    declare a length. Sits inside the app's error handling, so the 413 is an ordinary response.
    """

    def __init__(self, app) -> None:  # type: ignore[no-untyped-def]
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        limit = _body_limit(scope["path"]) if scope["type"] == "http" else 0
        if not limit:
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            await JSONResponse({"detail": _too_large(limit)}, status_code=413)(scope, receive, send)
            return
        seen = 0

        async def counted():  # type: ignore[no-untyped-def]
            nonlocal seen
            message = await receive()
            seen += len(message.get("body", b""))
            if seen > limit:
                raise HTTPException(413, _too_large(limit))
            return message

        await self.app(scope, counted, send)


async def raw_body(request: Request) -> bytes:
    """A file sent as the request body. Declared last on a route, after sign-in checks, so strangers
    cannot make the server read; reading here lets the route itself run off the event loop."""
    return await request.body()


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
            scheme = request.url.scheme
            if _truthy(os.environ.get("GC_TRUST_PROXY")):
                # Behind a TLS-terminating proxy (Cloud Run, Render) the app itself sees plain http.
                scheme = request.headers.get("x-forwarded-proto", scheme).split(",")[0].strip()
            own = f"{scheme}://{request.headers.get('host', '')}"
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
        scheme = request.url.scheme
        if _truthy(os.environ.get("GC_TRUST_PROXY")):  # TLS ends at the host's proxy (Render)
            scheme = request.headers.get("x-forwarded-proto", scheme).split(",")[0].strip()
        if scheme == "https":  # browsers keep to HTTPS for a year; never sent over plain http
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return resp
