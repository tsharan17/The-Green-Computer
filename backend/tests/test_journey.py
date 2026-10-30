"""The complete user journey in one test, end to end through the real HTTP API."""

import io
import zipfile

import pytest

from app.main import create_app
from tests.helpers import AuthedClient

P = "/api/v1"

DEVICE = {
    "name": "Acme Edge X1", "vendor": "Acme", "kind": "edge_soc",
    "peak_tflops": {"fp32": 2.0, "fp16": 9.0, "int8": 18.0}, "mem_bw_gbs": 120.0, "mem_gb": 8.0,
    "power_modes": [{"name": "10W", "cap_w": 10}, {"name": "20W", "cap_w": 20}],
    "t_throttle_c": 95.0,
}  # fmt: skip


@pytest.fixture()
def app(tmp_path):
    with AuthedClient(create_app(f"sqlite:///{tmp_path / 'journey.db'}")) as c:
        yield c


def test_the_whole_journey(app):
    c = app

    # 1. The app is healthy.
    assert c.get(f"{P}/health").json()["status"] == "ok"

    # 2. A visitor describes a setup (the robot example) and analyses it.
    tpl = c.get(f"{P}/projects").json()[0]["spec"]
    mine = c.post(f"{P}/projects", json={**tpl, "name": "My analysis"}).json()
    pid = mine["id"]
    res = c.post(f"{P}/projects/{pid}/optimise").json()
    v = res["verdict"]
    assert not v["baseline"]["ok"] and v["improved"]["ok"] and v["savings"]["power_percent"] > 40
    assert "overheats" in v["baseline"]["headline"].lower()

    # 3. The result says what to change at every level, with the cheapest fix first.
    assert res["repair"]["needed"] and res["repair"]["plans"][0]["changes"]
    assert {a["tier"] for a in res["advice"]} >= {"model", "configure", "design"}
    assert all(a["why"] and a["confidence"] for a in res["advice"])
    assert res["whatifs"] and res["limiting_factor"] and res["alternatives"]

    # 4. The requirements were never relaxed to get there.
    cons = c.get(f"{P}/projects/{pid}").json()["spec"]["constraints"]
    assert cons["max_power_w"] == 55 and cons["min_accuracy"] == 0.9

    # 5. An unknown board is described by hand, but is unusable until a person confirms.
    d = c.post(f"{P}/hardware/manual", json=DEVICE).json()
    assert d["needs_confirmation"]
    nope = {**tpl, "name": "x", "device_id": "custom-hw-acme-edge-x1"}
    assert c.post(f"{P}/projects", json=nope).status_code == 422
    dev = c.post(f"{P}/hardware/drafts/{d['id']}/confirm", json={}).json()
    p2 = c.post(f"{P}/projects", json={**tpl, "name": "Acme", "device_id": dev["id"],
                                        "cooling_id": dev["default_cooling"]}).json()  # fmt: skip
    r2 = c.post(f"{P}/projects/{p2['id']}/optimise")
    assert r2.status_code == 200 and r2.json()["verdict"]["summary"]

    # 6. Real measurements are added; calibration is only applied if it earns its place.
    for model, ms in (("yolov8n", 3.1), ("yolov8s", 9.4), ("resnet-50", 3.9), ("yolov8m", 21.5)):
        assert c.post(f"{P}/measurements", json={"device_id": "jetson-orin-nx", "model_id": model,
                      "precision": "fp16", "batch": 1, "power_mode_id": "MAXN",
                      "latency_ms_mean": ms}).status_code == 201  # fmt: skip
    ver = c.get(f"{P}/verify?device_id=jetson-orin-nx").json()
    assert ver["summaries"] and ver["summaries"][0]["n"] == 4
    again = c.post(f"{P}/projects/{pid}/optimise").json()  # re-analysis uses the new evidence
    assert again["verdict"]["summary"]

    # 7. The report and the recipe come out of the stored analysis.
    md = c.get(f"{P}/projects/{pid}/report").text
    assert "## 2. The verdict" in md and "## 4. Recommendations" in md
    z = zipfile.ZipFile(io.BytesIO(c.get(f"{P}/projects/{pid}/recipe.zip").content))
    assert {"README.md", "optimise_model.py", "runtime_config.json"} <= set(z.namelist())

    # 8. Everything survives a restart of the server (same database).
    url = str(c.app.state.session_factory.kw["bind"].url)
    with AuthedClient(create_app(url)) as c2:
        assert c2.get(f"{P}/projects/{pid}").status_code == 200
        assert any(x["id"] == dev["id"] for x in c2.get(f"{P}/hardware/library").json())
        assert c2.get(f"{P}/projects/{pid}/report").status_code == 200
