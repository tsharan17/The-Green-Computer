from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.agent import router as agent_router
from app.api.v1.export import router as export_router
from app.api.v1.hardware import router as hardware_router
from app.api.v1.measurements import router as measurement_router
from app.api.v1.routes import router
from app.config import get_settings
from app.db import models  # noqa: F401  (register tables)
from app.db.session import Base, make_engine, make_session_factory
from app.services import hardware_service, measurement_service
from app.services.seed import seed_example

STATIC_DIR = Path(__file__).parent / "static"


def create_app(db_url: str | None = None) -> FastAPI:
    settings = get_settings()
    engine = make_engine(db_url or settings.db_url)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(engine)
        with session_factory() as db:
            hardware_service.load_confirmed(db)
            seed_example(db)
            measurement_service.replay_committed(db)
        yield

    app = FastAPI(title="The Green Computer", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = session_factory
    app.include_router(router, prefix=settings.api_prefix)
    app.include_router(measurement_router, prefix=settings.api_prefix)
    app.include_router(agent_router, prefix=settings.api_prefix)
    app.include_router(export_router, prefix=settings.api_prefix)
    app.include_router(hardware_router, prefix=settings.api_prefix)

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
