"""The language-model estimate, the accuracy table and the funnel totals."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.data_loader import get_device
from app.engine.llm import estimate_llm
from app.main import create_app

P = "/api/v1"
CSRF = {"X-GC-CSRF": "1"}


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(db_url=f"sqlite:///{tmp_path / 't.db'}", data_dir=str(tmp_path / "d")))


def test_llm_estimate_is_labelled_and_memory_bound():
    hw = get_device("jetson-orin-nx")
    out = estimate_llm(hw, 7000, "int8", 256, 2048)
    speed = out["tokens_per_s"]
    assert out["validated"] is False and speed["provenance"] == "analytical"
    assert speed["low"] < speed["value"] < speed["high"]
    assert 0.5 < speed["value"] < 100  # a 7B model on a 100 GB/s-class board is single to double digits
    assert out["limit"] == "memory bandwidth"
    # Twice the weights, about half the speed when memory is the limit.
    double = estimate_llm(hw, 14000, "int8", 256, 2048)["tokens_per_s"]["value"]
    assert 0.4 * speed["value"] < double < 0.6 * speed["value"]


def test_llm_too_big_says_it_does_not_fit():
    assert estimate_llm(get_device("jetson-orin-nano"), 70000, "fp16", 16, 2048)["fits_memory"] is False


def test_llm_api_public_and_refuses_unknown_device(tmp_path):
    with _client(tmp_path) as c:
        devs = c.get(f"{P}/estimate/llm/devices").json()
        assert any(d["id"] == "jetson-orin-nx" for d in devs)
        ok = c.post(f"{P}/estimate/llm", headers=CSRF, json={"device_id": "jetson-orin-nx", "params_m": 7000})
        assert ok.status_code == 200
        assert c.post(f"{P}/estimate/llm", headers=CSRF, json={"device_id": "nope", "params_m": 7}).status_code == 404
        assert c.post(f"{P}/estimate/llm", headers=CSRF, json={"device_id": "jetson-orin-nx", "params_m": -1}).status_code == 422


def test_accuracy_reports_only_shipped_runs(tmp_path):
    with _client(tmp_path) as c:
        before = c.get(f"{P}/accuracy").json()
        assert before["runs"] >= 1 and before["devices"] == 1
        assert before["power_runs"] == 0
        c.post(f"{P}/auth/signup", headers=CSRF, json={"email": "a@x.io", "password": "a long passphrase here", "accept_terms": True})
        r = c.post(f"{P}/measurements", headers=CSRF, json={
            "device_id": "jetson-orin-nx", "model_id": "yolov8s", "precision": "fp16", "latency_ms_mean": 12.0})  # fmt: skip
        assert r.status_code < 300, r.text
        assert c.get(f"{P}/accuracy").json()["runs"] == before["runs"]  # a user's run stays private


def test_funnel_needs_the_operator_token(tmp_path, monkeypatch):
    monkeypatch.delenv("GC_METRICS_TOKEN", raising=False)
    with _client(tmp_path) as c:
        assert c.get(f"{P}/ops/funnel").status_code == 404
        monkeypatch.setenv("GC_METRICS_TOKEN", "t0ken")
        assert c.get(f"{P}/ops/funnel").status_code == 401
        c.post(f"{P}/auth/signup", headers=CSRF, json={"email": "b@x.io", "password": "a long passphrase here", "accept_terms": True})
        got = c.get(f"{P}/ops/funnel", headers={"Authorization": "Bearer t0ken"}).json()
        assert got["accounts"] == 1 and "b@x.io" not in str(got)
