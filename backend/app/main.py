from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.v1.agent import router as agent_router
from app.api.v1.auth import router as auth_router
from app.api.v1.executions import router as executions_router
from app.api.v1.export import router as export_router
from app.api.v1.files import router as files_router
from app.api.v1.guide import router as guide_router
from app.api.v1.hardware import router as hardware_router
from app.api.v1.intake import router as intake_router
from app.api.v1.measurements import router as measurement_router
from app.api.v1.physics import router as physics_router
from app.api.v1.plans import router as plans_router
from app.api.v1.routes import router
from app.api.v1.system_graph import router as system_graph_router
from app.api.v1.twin import router as twin_router
from app.api.v1.workspace import router as workspace_router
from app.config import get_settings
from app.db import models  # noqa: F401  (register tables)
from app.db.migrate import current_revision, head_revision, upgrade
from app.db.session import make_engine, make_session_factory
from app.providers.email import make_email_sender
from app.providers.storage import LocalBlobStore, default_data_dir
from app.security import OriginCheck, SecurityHeaders
from app.services import execution_service, hardware_service, measurement_service

STATIC_DIR = Path(__file__).parent / "static"
log = logging.getLogger("green_computer")


def create_app(db_url: str | None = None, data_dir: str | None = None) -> FastAPI:
    settings = get_settings()
    url = db_url or settings.db_url
    engine = make_engine(url)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.auto_migrate:
            upgrade(engine)
        elif current_revision(engine) != head_revision():
            raise RuntimeError(
                "The database schema is not up to date. Run: python -m alembic upgrade head "
                "(or unset GC_AUTO_MIGRATE=0)."
            )
        with session_factory() as db:
            hardware_service.load_confirmed(db)
            measurement_service.replay_committed(db)
            execution_service.recover_stale(db)
        yield

    app = FastAPI(
        title="The Green Computer API",
        version=__version__,
        lifespan=lifespan,
        description=(
            "Versioned under /api/v1 (additive changes only within a major version). Sign in with "
            "POST /api/v1/auth/signin (browser cookie + X-GC-CSRF: 1 header) or use a bearer API "
            "token from POST /api/v1/auth/tokens. Every number carries provenance and a band."
        ),
    )
    app.add_middleware(SecurityHeaders)
    app.add_middleware(OriginCheck, allowed=settings.allowed_origins)
    app.state.session_factory = session_factory
    app.state.engine = engine
    app.state.blobs = LocalBlobStore(default_data_dir(url, data_dir or settings.data_dir) / "blobs")
    app.state.email_sender = make_email_sender()
    for r in (auth_router, workspace_router, router, measurement_router, agent_router,
              export_router, hardware_router, files_router, intake_router, twin_router, plans_router,
              executions_router, guide_router, system_graph_router, physics_router):  # fmt: skip
        app.include_router(r, prefix=settings.api_prefix)

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
    else:

        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        def ui_not_built() -> str:
            return (
                "<h1>The Green Computer API is running</h1>"
                "<p>The web UI has not been built. Run <code>npm install &amp;&amp; npm run build</code> "
                "in <code>frontend/</code> (output goes to <code>backend/app/static</code>), then "
                "reload. API docs: <a href='/docs'>/docs</a>.</p>"
            )

    return app


app = create_app()
