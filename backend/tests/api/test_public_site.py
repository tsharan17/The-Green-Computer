"""The public site: worked examples without an account, and the operator's contact in legal pages."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.api.v1.try_example import _analysis
from app.data_loader import clear_custom_devices
from app.main import create_app
from app.services import guide_service as guide
from tests.helpers import AuthedClient

P = "/api/v1"


@pytest.fixture()
def app(tmp_path):
    a = create_app(f"sqlite:///{tmp_path / 'pub.db'}", data_dir=str(tmp_path / "d"))
    yield a
    clear_custom_devices()


def _rows(app) -> dict[str, int]:
    with app.state.engine.connect() as c:
        names = sa.inspect(c).get_table_names()
        return {t: c.execute(sa.text(f'SELECT COUNT(*) FROM "{t}"')).scalar_one() for t in names}


def test_every_example_is_analysed_without_an_account_and_leaves_nothing_behind(app):
    with TestClient(app) as c:
        before = _rows(app)
        listed = c.get(f"{P}/try/examples").json()
        assert [x["id"] for x in listed] == [u["id"] for u in guide.USE_CASES]
        for x in listed:
            r = c.get(f"{P}/try/examples/{x['id']}")
            assert r.status_code == 200, x["id"]
            res = r.json()["result"]
            assert res["verdict"]["summary"] and res["advice"] and res["alternatives"]
            assert "points" not in res and "top" not in res
            # predictions only: no measurement or calibration can reach a public example
            assert {m["provenance"] for m in res["baseline"]["metrics"].values()} <= {"analytical", "assumed", "vendor_spec"}
        assert c.get(f"{P}/try/examples/nope").status_code == 404
        assert _rows(app) == before  # nothing read into or written to any table's rows


def test_examples_ignore_a_users_own_hardware_and_measurements(app):
    _analysis.cache_clear()  # computed after the private data exists, not served from an earlier test
    with AuthedClient(app) as c:
        c.post(f"{P}/hardware/custom", json={"name": "Private Board", "style": "generic", "peak_tops": {"fp16": 2.0},
                                             "mem_bw_gbs": 20, "mem_gb": 2, "tdp_w": 8})  # fmt: skip
        c.post(f"{P}/measurements", json={"device_id": "jetson-orin-nano", "model_id": "yolov8n", "precision": "fp16",
                                          "latency_ms_mean": 1.0, "external_id": "m1"})  # fmt: skip
        r = c.get(f"{P}/try/examples/edge-camera").json()
    assert "Private Board" not in str(r)
    assert all(m["provenance"] != "calibrated" for m in r["result"]["baseline"]["metrics"].values())


def test_examples_are_rate_limited(app, monkeypatch):
    monkeypatch.setenv("GC_ANALYSE_RATE_PER_MIN", "2")
    with TestClient(app) as c:
        codes = [c.get(f"{P}/try/examples/mcu-voice").status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_legal_pages_name_the_operator_and_the_configured_contact(app, monkeypatch):
    with TestClient(app) as c:
        terms = c.get(f"{P}/auth/legal/terms").json()["markdown"]
        assert "T Sharan" in terms and "{{contact}}" not in terms and "not yet set" in terms
        assert c.get(f"{P}/auth/config").json()["contact_email"] is None
        monkeypatch.setenv("GC_CONTACT_EMAIL", "hello@example.org")
        for doc in ("terms", "privacy", "acceptable-use", "data"):
            assert "{{contact}}" not in c.get(f"{P}/auth/legal/{doc}").json()["markdown"]
        assert "hello@example.org" in c.get(f"{P}/auth/legal/privacy").json()["markdown"]
        cfg = c.get(f"{P}/auth/config").json()
        assert cfg["contact_email"] == "hello@example.org" and cfg["operator"] == "T Sharan"
