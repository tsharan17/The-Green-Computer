"""Free-hosting fit: the S3-compatible and database blob stores, hosted mode and its required secrets."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from app.data_loader import clear_custom_devices
from app.db.session import normalise_url
from app.main import create_app
from app.providers.s3 import EMPTY_SHA256, S3BlobStore, sign_v4
from app.providers.storage import DatabaseBlobStore, LocalBlobStore, make_blob_store
from tests.helpers import AuthedClient, tiny_cnn_bytes

P = "/api/v1"
OCTET = {"Content-Type": "application/octet-stream"}

# --- request signing ---------------------------------------------------------------------------

AWS_KEY, AWS_SECRET = "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
AWS_NOW = datetime(2013, 5, 24, tzinfo=UTC)


@pytest.mark.parametrize(("url", "headers", "signature"), [
    # The worked examples in AWS's Signature Version 4 documentation for S3.
    ("https://examplebucket.s3.amazonaws.com/test.txt", {"Range": "bytes=0-9"},
     "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"),
    ("https://examplebucket.s3.amazonaws.com/?lifecycle", {},
     "fea454ca298b7da1c68078a5d1bdbfbbe0d65c699e0f91ac7a200a0136783543"),
    ("https://examplebucket.s3.amazonaws.com/?max-keys=2&prefix=J", {},
     "34b48302e7b5fa45bde8084f4b7868a86f0a534bc59db6670ed5711ef69dc6f7"),
])  # fmt: skip
def test_signature_matches_the_aws_worked_examples(url, headers, signature):
    out = sign_v4("GET", url, headers, EMPTY_SHA256, AWS_KEY, AWS_SECRET, "us-east-1", AWS_NOW)
    assert out["Authorization"].endswith(f"Signature={signature}")
    assert out["x-amz-date"] == "20130524T000000Z"


# --- S3 blob store against an in-memory bucket -------------------------------------------------


class FakeBucket:
    """Just enough of the S3 API: PUT, GET, DELETE, ListObjectsV2. Checks every request is signed."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.requests = 0

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests += 1
        assert req.headers["authorization"].startswith("AWS4-HMAC-SHA256 Credential=k/")
        assert req.headers["x-amz-content-sha256"] == hashlib.sha256(req.content).hexdigest()
        parts = urlsplit(str(req.url))
        assert parts.path.startswith("/bkt/")
        key = unquote(parts.path[len("/bkt/"):])
        if req.method == "PUT":
            self.objects[key] = req.content
            return httpx.Response(200)
        if req.method == "DELETE":
            self.objects.pop(key, None)
            return httpx.Response(204)
        if key:
            data = self.objects.get(key)
            return httpx.Response(200, content=data) if data is not None else httpx.Response(404)
        q = parse_qs(parts.query)
        keys = sorted(k for k in self.objects if k.startswith(q["prefix"][0]))[: int(q.get("max-keys", ["1000"])[0])]
        body = "".join(f"<Contents><Key>{k}</Key></Contents>" for k in keys)
        xml = f'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">{body}</ListBucketResult>'
        return httpx.Response(200, content=xml.encode())


@pytest.fixture()
def bucket(tmp_path):
    fake = FakeBucket()
    store = S3BlobStore("https://acct.r2.example", "bkt", "k", "s", prefix="prod",
                        cache_dir=tmp_path / "cache", transport=httpx.MockTransport(fake))  # fmt: skip
    return fake, store


def test_s3_store_round_trip_under_a_prefix(bucket):
    fake, store = bucket
    key, digest = store.put("ws7", b"model bytes")
    assert key == f"ws7/{digest}" and fake.objects == {f"prod/ws7/{digest}": b"model bytes"}
    assert store.get(key) == b"model bytes"
    p = store.path(key)
    assert p is not None and p.read_bytes() == b"model bytes"
    n = fake.requests
    assert store.path(key) == p and fake.requests == n  # served from the local cache
    assert store.has_namespace("ws7") and not store.has_namespace("ws8")
    store.delete(key)
    assert fake.objects == {} and store.path(key) is None and not p.exists()
    with pytest.raises(FileNotFoundError):
        store.get(key)


def test_s3_store_deletes_one_workspace_only(bucket):
    fake, store = bucket
    a, _ = store.put("ws1", b"a")
    store.put("ws1", b"b")
    c, _ = store.put("ws12", b"c")  # a prefix of ws1 must not be swept up
    store.delete_namespace("ws1")
    assert set(fake.objects) == {f"prod/{c}"}
    with pytest.raises(ValueError):
        store.get("../etc/passwd")
    with pytest.raises(ValueError):
        store.put("ws1/../ws2", b"x")


def test_blob_backend_is_chosen_from_the_environment(tmp_path, monkeypatch):
    assert isinstance(make_blob_store(tmp_path), LocalBlobStore)
    monkeypatch.setenv("GC_BLOB_BACKEND", "s3")
    with pytest.raises(RuntimeError, match="GC_S3_BUCKET"):
        make_blob_store(tmp_path)
    for k, v in {"GC_S3_ENDPOINT": "https://x.r2.example", "GC_S3_BUCKET": "b",
                 "GC_S3_ACCESS_KEY_ID": "k", "GC_S3_SECRET_ACCESS_KEY": "s"}.items():  # fmt: skip
        monkeypatch.setenv(k, v)
    store = make_blob_store(tmp_path)
    assert isinstance(store, S3BlobStore) and store.cache == tmp_path / "blob_cache"
    monkeypatch.setenv("GC_BLOB_BACKEND", "database")
    with pytest.raises(RuntimeError, match="database engine"):
        make_blob_store(tmp_path)
    monkeypatch.setenv("GC_BLOB_BACKEND", "ftp")
    with pytest.raises(RuntimeError, match="local, s3 or database"):
        make_blob_store(tmp_path)


# --- database blob store ------------------------------------------------------------------------


def test_database_store_round_trip_and_one_workspace_at_a_time(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'b.db'}", data_dir=str(tmp_path / "d"))
    with TestClient(app):  # start-up runs the migrations
        pass
    store = DatabaseBlobStore(app.state.engine, tmp_path / "cache")
    key, digest = store.put("ws1", b"model bytes")
    assert key == f"ws1/{digest}" and store.put("ws1", b"model bytes")[0] == key  # stored once
    assert store.get(key) == b"model bytes"
    p = store.path(key)
    assert p is not None and p.read_bytes() == b"model bytes"
    other, _ = store.put("ws12", b"other")  # a prefix of ws1 must not be swept up
    store.put("ws1", b"second")
    assert store.has_namespace("ws1") and not store.has_namespace("ws2")
    store.delete_namespace("ws1")
    assert not store.has_namespace("ws1") and not p.exists() and store.get(other) == b"other"
    with pytest.raises(FileNotFoundError):
        store.get(key)
    assert store.path(key) is None
    with pytest.raises(ValueError):
        store.get("../etc/passwd")
    with pytest.raises(ValueError):
        store.put("ws1/../ws2", b"x")


def test_uploads_survive_a_restart_with_files_in_the_database(tmp_path, monkeypatch):
    """Render's free plan has no disk: with GC_BLOB_BACKEND=database a fresh container, with an empty
    data folder, still serves the files uploaded before it started."""
    monkeypatch.setenv("GC_BLOB_BACKEND", "database")
    url = f"sqlite:///{tmp_path / 'r.db'}"
    with AuthedClient(create_app(url, data_dir=str(tmp_path / "first"))) as c:
        up = c.post(f"{P}/models/upload?filename=tiny.onnx", content=tiny_cnn_bytes(), headers=OCTET).json()
        email = c.get(f"{P}/auth/me").json()["user"]["email"]
    assert not any((tmp_path / "first").rglob("*.onnx"))
    with AuthedClient(create_app(url, data_dir=str(tmp_path / "second")), email=email) as c:
        r = c.get(f"{P}/artifacts/{up['artifact_id']}/download")
    assert r.status_code == 200 and r.content == tiny_cnn_bytes()


def test_ready_with_files_in_the_database(tmp_path, monkeypatch):
    monkeypatch.setenv("GC_BLOB_BACKEND", "database")
    with TestClient(create_app(f"sqlite:///{tmp_path / 'q.db'}", data_dir=str(tmp_path / "d"))) as c:
        r = c.get(f"{P}/ready")
    assert r.status_code == 200, r.text
    assert {x["check"] for x in r.json()["checks"]} == {"database", "schema", "file_storage"}


# --- hosted mode --------------------------------------------------------------------------------


def test_hosted_mode_refuses_to_start_without_its_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("GC_HOSTED", "1")
    monkeypatch.delenv("GC_SECRET_KEY", raising=False)
    monkeypatch.setenv("GC_AGENT_SIGNING_SECRET", "x" * 32)
    with pytest.raises(RuntimeError, match="GC_SECRET_KEY"):
        create_app(f"sqlite:///{tmp_path / 'h.db'}")


@pytest.fixture()
def hosted(tmp_path, monkeypatch):
    monkeypatch.setenv("GC_HOSTED", "1")
    monkeypatch.setenv("GC_SECRET_KEY", "s" * 32)
    monkeypatch.setenv("GC_AGENT_SIGNING_SECRET", "a" * 32)
    with AuthedClient(create_app(f"sqlite:///{tmp_path / 'h.db'}", data_dir=str(tmp_path / "d"))) as c:
        yield c
    clear_custom_devices()


def test_hosted_server_predicts_but_never_runs_models(hosted):
    c = hosted
    b = {x["id"]: x for x in c.get(f"{P}/execution/backends").json()}
    assert b["local-cpu"]["status"] == "disabled" and "Pair your own device" in b["local-cpu"]["detail"]
    assert b["remote-device"]["status"] == "available"
    up = c.post(f"{P}/models/upload?filename=net.onnx", content=tiny_cnn_bytes(random_weights=True), headers=OCTET)
    assert up.status_code == 201, up.text
    pid = c.post(f"{P}/projects", json={"name": "h", "model_id": up.json()["profile"]["id"],
                                        "device_id": "jetson-orin-nano"}).json()["id"]  # fmt: skip
    r = c.post(f"{P}/projects/{pid}/executions", json={"runs": 3, "warmup": 0, "batch": 1})
    assert r.status_code == 409 and "hosted service" in r.json()["detail"]
    assert c.post(f"{P}/projects/{pid}/optimise").status_code == 200  # predictions still work
    r = c.post(f"{P}/projects/{pid}/exports", json={"kind": "int8_model"})
    assert r.status_code == 403 and "INT8 conversion" in r.json()["detail"]
    assert c.get(f"{P}/health").json()["demo_mode"] is False


def test_hosted_uploads_are_capped(hosted, monkeypatch):
    monkeypatch.setenv("GC_MAX_UPLOAD_MB", "1")
    big = b"\0" * (1024 * 1024 + 1)
    r = hosted.post(f"{P}/intake/upload?filename=big.onnx", content=big, headers=OCTET)
    assert r.status_code == 413 and re.search(r"limit 1 MB", r.json()["detail"])
    r = hosted.post(f"{P}/files/inspect?filename=big.csv", content=big, headers=OCTET)
    assert r.status_code == 413


def test_hosted_database_urls_use_the_installed_driver():
    neon = "postgresql://u:p@ep-x.eu-central-1.aws.neon.tech/gc?sslmode=require"
    assert normalise_url(neon) == "postgresql+psycopg://u:p@ep-x.eu-central-1.aws.neon.tech/gc?sslmode=require"
    assert normalise_url("postgres://u@h/db") == "postgresql+psycopg://u@h/db"
    for kept in ("postgresql+psycopg://u@h/db", "sqlite:///x.db"):
        assert normalise_url(kept) == kept
