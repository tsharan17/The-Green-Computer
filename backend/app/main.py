from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.v1.routes import router
from app.config import get_settings
from app.db import models  # noqa: F401  (register tables)
from app.db.session import Base, make_engine, make_session_factory
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
            seed_example(db)
        yield

    app = FastAPI(title="The Green Computer", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = session_factory
    app.include_router(router, prefix=settings.api_prefix)

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
    return app


app = create_app()
