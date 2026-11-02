"""Blob storage for uploaded files and generated artifacts, behind a small interface.

``LocalBlobStore`` keeps files on disk under ``<data_dir>/blobs/<workspace>/<sha256>``: one copy per
workspace (so deleting one tenant's data never touches another's) and content-addressed within it
(re-uploading the same file stores it once). ``S3BlobStore`` (providers/s3.py) keeps the same keys in an
S3-compatible bucket; ``DatabaseBlobStore`` keeps them in the app's own database (one service fewer
on a small free host). ``make_blob_store`` picks one from GC_BLOB_BACKEND.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

import sqlalchemy as sa

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_KEY = re.compile(r"^(ws\d+|library)/[0-9a-f]{64}$")


class BlobStore(Protocol):
    name: str

    def put(self, namespace: str, data: bytes) -> tuple[str, str]: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def delete_namespace(self, namespace: str) -> None: ...
    def path(self, key: str) -> Path | None: ...


class LocalBlobStore:
    name = "local"

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _file(self, key: str) -> Path:
        if not _KEY.match(key):
            raise ValueError("invalid blob key")
        return self.root / key

    def put(self, namespace: str, data: bytes) -> tuple[str, str]:
        """Store bytes; returns (key, sha256)."""
        if not re.fullmatch(r"ws\d+|library", namespace):
            raise ValueError("invalid namespace")
        digest = hashlib.sha256(data).hexdigest()
        key = f"{namespace}/{digest}"
        dest = self._file(key)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=dest.parent)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
        return key, digest

    def get(self, key: str) -> bytes:
        return self._file(key).read_bytes()

    def path(self, key: str) -> Path | None:
        p = self._file(key)
        return p if p.is_file() else None

    def delete(self, key: str) -> None:
        p = self._file(key)
        if p.exists():
            p.unlink()

    def delete_namespace(self, namespace: str) -> None:
        if not re.fullmatch(r"ws\d+", namespace):
            raise ValueError("invalid namespace")
        shutil.rmtree(self.root / namespace, ignore_errors=True)

    def has_namespace(self, namespace: str) -> bool:
        if not re.fullmatch(r"ws\d+", namespace):
            raise ValueError("invalid namespace")
        d = self.root / namespace
        return d.exists() and any(d.rglob("*"))


def _blobs() -> sa.Table:
    from app.db.models import BlobRow  # the ORM models import the session module, so imported late

    return cast(sa.Table, BlobRow.__table__)


class DatabaseBlobStore:
    """Files as rows of the ``blobs`` table, with the same keys as the other stores. Suits a small
    hosted deployment on a free database plan; reads are cached on local disk for ``path``."""

    name = "database"

    def __init__(self, engine: Engine, cache_dir: Path | None = None) -> None:
        self.engine = engine
        self.cache = cache_dir or Path(tempfile.gettempdir()) / "gc_blob_cache"

    @staticmethod
    def _check(key: str) -> None:
        if not _KEY.match(key):
            raise ValueError("invalid blob key")

    def put(self, namespace: str, data: bytes) -> tuple[str, str]:
        if not re.fullmatch(r"ws\d+|library", namespace):
            raise ValueError("invalid namespace")
        digest = hashlib.sha256(data).hexdigest()
        key = f"{namespace}/{digest}"
        t = _blobs()
        with self.engine.begin() as c:
            if c.execute(sa.select(t.c.key).where(t.c.key == key)).first() is None:
                c.execute(t.insert().values(key=key, namespace=namespace, size=len(data), data=data))
        return key, digest

    def get(self, key: str) -> bytes:
        self._check(key)
        t = _blobs()
        with self.engine.connect() as c:
            data = c.execute(sa.select(t.c.data).where(t.c.key == key)).scalar_one_or_none()
        if data is None:
            raise FileNotFoundError(key)
        return bytes(data)

    def path(self, key: str) -> Path | None:
        self._check(key)
        local = self.cache / key
        if local.is_file():
            return local
        try:
            data = self.get(key)
        except FileNotFoundError:
            return None
        local.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=local.parent)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, local)
        return local

    def delete(self, key: str) -> None:
        self._check(key)
        t = _blobs()
        with self.engine.begin() as c:
            c.execute(t.delete().where(t.c.key == key))
        (self.cache / key).unlink(missing_ok=True)

    def delete_namespace(self, namespace: str) -> None:
        if not re.fullmatch(r"ws\d+", namespace):
            raise ValueError("invalid namespace")
        t = _blobs()
        with self.engine.begin() as c:
            c.execute(t.delete().where(t.c.namespace == namespace))
        shutil.rmtree(self.cache / namespace, ignore_errors=True)

    def has_namespace(self, namespace: str) -> bool:
        if not re.fullmatch(r"ws\d+", namespace):
            raise ValueError("invalid namespace")
        t = _blobs()
        with self.engine.connect() as c:
            return c.execute(sa.select(t.c.key).where(t.c.namespace == namespace).limit(1)).first() is not None


def make_blob_store(data_dir: Path, engine: Engine | None = None) -> BlobStore:
    """Local disk by default; an S3-compatible bucket (Cloudflare R2, S3, MinIO) with GC_BLOB_BACKEND=s3;
    the app's own database with GC_BLOB_BACKEND=database."""
    kind = (os.environ.get("GC_BLOB_BACKEND") or "local").strip().lower()
    if kind == "database":
        if engine is None:
            raise RuntimeError("GC_BLOB_BACKEND=database needs the app's database engine")
        return DatabaseBlobStore(engine, data_dir / "blob_cache")
    if kind == "s3":
        from app.providers.s3 import S3BlobStore

        store = S3BlobStore.from_env()
        store.cache = data_dir / "blob_cache"
        return store
    if kind != "local":
        raise RuntimeError(f"GC_BLOB_BACKEND must be local, s3 or database, not {kind!r}")
    return LocalBlobStore(data_dir / "blobs")


def default_data_dir(db_url: str, configured: str | None) -> Path:
    if configured:
        return Path(configured)
    if db_url.startswith("sqlite:///") and ":memory:" not in db_url:
        return Path(db_url[len("sqlite:///") :]).resolve().parent / "gc_data"
    if db_url.startswith("sqlite"):
        return Path(tempfile.mkdtemp(prefix="gc_data_"))
    return Path("./gc_data").resolve()
