from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def normalise_url(url: str) -> str:
    """Hosted databases (Neon, Render, Heroku) hand out postgres:// or postgresql:// URLs; the app's
    driver is psycopg 3, so use it unless the URL already names a driver."""
    for scheme in ("postgres://", "postgresql://"):
        if url.startswith(scheme):
            return "postgresql+psycopg://" + url[len(scheme):]
    return url


def make_engine(url: str):
    url = normalise_url(url)
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url or url == "sqlite://":
            kwargs["poolclass"] = StaticPool
    else:
        # Managed PostgreSQL (for example Neon) closes idle connections and pauses itself; test a pooled
        # connection before using it, and do not keep one for longer than five minutes.
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 300
    return create_engine(url, **kwargs)


def make_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
