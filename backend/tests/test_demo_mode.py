"""Public-demo safeguards: rate limits, caps, privacy and security headers."""

import pytest

import app.security as sec
from app.main import create_app
from tests.helpers import AuthedClient

P = "/api/v1"


@pytest.fixture(autouse=True)
def fresh_limiter():
    sec.LIMITER.reset()
    yield
    sec.LIMITER.reset()


@pytest.fixture()
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv("GC_PUBLIC_DEMO", "1")
    with AuthedClient(create_app(f"sqlite:///{tmp_path / 'demo.db'}")) as c:
        yield c


@pytest.fixture()
def local(tmp_path):
    with AuthedClient(create_app(f"sqlite:///{tmp_path / 'local.db'}")) as c:
        yield c


def test_sliding_window_limiter(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(sec.time, "monotonic", lambda: now[0])
    rl = sec.RateLimiter()
    assert [rl.check("a", 2, 60) for _ in range(2)] == [None, None]
    wait = rl.check("a", 2, 60)
    assert wait is not None and 0 < wait <= 60
    assert rl.check("b", 2, 60) is None  # another caller is unaffected
    now[0] += 61
    assert rl.check("a", 2, 60) is None  # the window slid past the old calls
    assert rl.check("a", 0, 60) is None  # 0 disables the limit


def test_visitors_never_see_each_others_projects_in_demo(demo):
    other = demo.post(f"{P}/projects", json={"name": "Alice private", "model_id": "yolov8s",
                                             "device_id": "jetson-orin-nx"}).json()  # fmt: skip
    with AuthedClient(demo.app, email="bob@example.com") as bob:
        names = [p["spec"]["name"] for p in bob.get(f"{P}/projects").json()]
        assert names and "Alice private" not in names
        assert bob.get(f"{P}/projects/{other['id']}").status_code == 404
    assert demo.get(f"{P}/projects/{other['id']}").status_code == 200
    assert demo.get(f"{P}/health").json()["demo_mode"] is True


def test_analysis_is_rate_limited_in_demo(demo, monkeypatch):
    monkeypatch.setenv("GC_ANALYSE_RATE_PER_MIN", "1")
    pid = demo.get(f"{P}/projects").json()[0]["id"]
    assert demo.post(f"{P}/projects/{pid}/optimise").status_code == 200
    assert demo.post(f"{P}/projects/{pid}/optimise").status_code == 429


def test_analysis_is_not_limited_locally(local):
    pid = local.get(f"{P}/projects").json()[0]["id"]
    assert [local.post(f"{P}/projects/{pid}/optimise").status_code for _ in range(2)] == [200, 200]


def test_proxy_header_is_trusted_only_when_configured(monkeypatch):
    class Req:
        headers = {"x-forwarded-for": "203.0.113.9, 10.0.0.1"}
        client = type("C", (), {"host": "10.0.0.1"})()

    assert sec.client_ip(Req()) == "10.0.0.1"  # spoofable header ignored by default
    monkeypatch.setenv("GC_TRUST_PROXY", "1")
    assert sec.client_ip(Req()) == "203.0.113.9"


def test_caps_on_projects_uploads_and_custom_items(demo, monkeypatch):
    monkeypatch.setenv("GC_MAX_PROJECTS", "2")  # the seeded example already counts as one
    spec = {"name": "p", "model_id": "yolov8s", "device_id": "jetson-orin-nx"}
    assert demo.post(f"{P}/projects", json=spec).status_code == 201
    assert demo.post(f"{P}/projects", json=spec).status_code == 503

    big = b"x" * (11 * 1024 * 1024)
    r = demo.post(f"{P}/models/upload", content=big, headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 413 and "10 MB" in r.json()["detail"]

    monkeypatch.setenv("GC_MAX_CUSTOM_ITEMS", "1")
    m = {"name": "m", "params_m": 1, "gflops": 1}
    assert demo.post(f"{P}/models/manual", json=m).status_code == 201
    assert demo.post(f"{P}/models/manual", json=m).status_code == 503


def test_security_headers(local):
    for path in ("/", f"{P}/health"):
        r = local.get(path)
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY" and r.headers["referrer-policy"] == "no-referrer"
        assert "default-src 'self'" in r.headers["content-security-policy"]
        assert "script-src 'self'" in r.headers["content-security-policy"]
    assert "content-security-policy" not in local.get("/docs").headers  # Swagger needs its CDN
