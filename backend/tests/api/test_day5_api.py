"""Day 5 API: report/recipe export and hardware drafts with mandatory confirmation."""

import io
import zipfile

import pytest

from app.engine.datasheet_profile import clean_extraction, extraction_from_scan
from app.main import create_app
from tests.helpers import AuthedClient

P = "/api/v1"


@pytest.fixture()
def client(tmp_path):
    with AuthedClient(create_app(f"sqlite:///{tmp_path / 'd.db'}")) as c:
        yield c


def pid(c):
    return c.get(f"{P}/projects").json()[0]["id"]


# --- export ----------------------------------------------------------------------------------


def test_export_needs_an_analysis_first_then_serves_report_and_recipe(client):
    p = pid(client)
    assert client.get(f"{P}/projects/{p}/report").status_code == 404
    assert client.get(f"{P}/projects/{p}/recipe").status_code == 404
    assert client.post(f"{P}/projects/{p}/optimise").status_code == 200

    md = client.get(f"{P}/projects/{p}/report")
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    assert "## 2. The verdict" in md.text
    html = client.get(f"{P}/projects/{p}/report?format=html")
    assert html.headers["content-type"].startswith("text/html") and "<table>" in html.text
    assert client.get(f"{P}/projects/{p}/report?format=pdf").status_code == 422

    rec = client.get(f"{P}/projects/{p}/recipe").json()
    assert "optimise_model.py" in rec["files"] and rec["warnings"]
    z = client.get(f"{P}/projects/{p}/recipe.zip")
    assert z.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert "README.md" in names and "runtime_config.json" in names


def test_optimise_payload_has_the_new_advice_fields(client):
    b = client.post(f"{P}/projects/{pid(client)}/optimise").json()
    assert b["verdict"]["summary"] and b["repair"]["needed"] is True
    assert {a["tier"] for a in b["advice"]} >= {"model", "configure", "design"}
    assert b["alternatives"] and b["whatifs"] and b["limiting_factor"]
    assert all("sparsity" in p["config"] for p in b["points"][:3])


# --- hardware drafts -------------------------------------------------------------------------

DEVICE = {
    "name": "Acme Edge AI X1", "vendor": "Acme", "kind": "edge_soc",
    "peak_tflops": {"fp32": 2.0, "fp16": 8.0, "int8": 16.0},
    "mem_bw_gbs": 120.0, "mem_gb": 8.0,
    "power_modes": [{"name": "10W", "cap_w": 10}, {"name": "20W", "cap_w": 20}],
    "t_throttle_c": 95.0,
}  # fmt: skip


def test_a_draft_is_not_usable_until_confirmed(client):
    c = client
    d = c.post(f"{P}/hardware/manual", json=DEVICE).json()
    assert d["status"] == "draft" and d["needs_confirmation"] is True and d["missing"] == []
    cand = d["candidate"]
    assert cand["mem_bw_gbs"] == 120.0 and cand["peak_tflops"]["int8"] == 16.0

    # Not usable yet: absent from the library, rejected by projects.
    assert all(not x["id"].startswith("custom-hw") for x in c.get(f"{P}/hardware/library").json())
    bad = {"name": "p", "model_id": "yolov8s", "device_id": "custom-hw-acme-edge-ai-x1"}
    assert c.post(f"{P}/projects", json=bad).status_code == 422

    prof = c.post(f"{P}/hardware/drafts/{d['id']}/confirm", json={}).json()
    assert prof["id"] == "custom-hw-acme-edge-ai-x1" and prof["verified"] is False
    assert prof["sources"]["mem_bw_gbs"] == "extracted_unverified"
    assert prof["sources"]["power_model"] == "assumed" and prof["sources"]["thermal"] == "assumed"
    assert any(x["id"] == prof["id"] for x in c.get(f"{P}/hardware/library").json())

    p = c.post(f"{P}/projects", json={**bad, "device_id": prof["id"]}).json()
    out = c.post(f"{P}/projects/{p['id']}/optimise")
    assert out.status_code == 200 and out.json()["verdict"]["summary"]
    assert c.post(f"{P}/hardware/drafts/{d['id']}/confirm", json={}).status_code == 422  # only once


def test_implausible_values_are_dropped_and_missing_ones_must_be_supplied(client):
    c = client
    d = c.post(f"{P}/hardware/manual", json={**DEVICE, "mem_bw_gbs": 99999999.0}).json()
    assert d["dropped_implausible"] == ["mem_bw_gbs"] and d["missing"] == ["mem_bw_gbs"]
    r = c.post(f"{P}/hardware/drafts/{d['id']}/confirm", json={})
    assert r.status_code == 422 and "mem_bw_gbs" in r.json()["detail"]  # never guessed
    ok = c.post(f"{P}/hardware/drafts/{d['id']}/confirm", json={"overrides": {"mem_bw_gbs": 100}})
    assert ok.status_code == 200 and ok.json()["mem_bw_gbs"] == 100


def test_user_can_reject_a_draft(client):
    c = client
    d = c.post(f"{P}/hardware/manual", json=DEVICE).json()
    assert c.post(f"{P}/hardware/drafts/{d['id']}/reject").json()["status"] == "rejected"
    assert c.post(f"{P}/hardware/drafts/{d['id']}/confirm", json={}).status_code == 422
    m = c.post(f"{P}/hardware/manual", json={"name": "My Board", "peak_tflops": {"fp16": 3.0},
                                             "mem_bw_gbs": 50, "mem_gb": 4, "tdp_w": 12}).json()
    assert m["status"] == "draft" and m["needs_confirmation"]
    assert c.post(f"{P}/hardware/drafts/{m['id']}/confirm", json={}).status_code == 200
    assert len(c.get(f"{P}/hardware/drafts").json()) == 2


def test_confirmed_devices_survive_a_restart(tmp_path):
    url = f"sqlite:///{tmp_path / 'r.db'}"
    with AuthedClient(create_app(url)) as c:
        d = c.post(f"{P}/hardware/manual", json={"name": "Keep Me", "peak_tflops": {"fp16": 3.0},
                                                 "mem_bw_gbs": 50, "mem_gb": 4, "tdp_w": 12}).json()
        c.post(f"{P}/hardware/drafts/{d['id']}/confirm", json={})
    with AuthedClient(create_app(url)) as c2:
        assert any(x["id"] == "custom-hw-keep-me" for x in c2.get(f"{P}/hardware/library").json())
    with AuthedClient(create_app(f"sqlite:///{tmp_path / 'other.db'}")) as c3:  # another db: no leak
        assert all(not x["id"].startswith("custom-hw") for x in c3.get(f"{P}/hardware/library").json())


def test_clean_extraction_only_accepts_plausible_values():
    ex = clean_extraction({**DEVICE, "t_throttle_c": 400, "kind": "toaster"}, set())
    assert "t_throttle_c" not in ex.candidate and "kind" not in ex.candidate
    assert ex.dropped == ["t_throttle_c"]


def test_scan_candidates_become_a_draft_with_page_and_line():
    line = "AI performance: 40 TOPS INT8"
    cands = [
        {"field": "peak_compute", "value": 40.0, "unit": "TOPS", "qualifier": "int8", "page": 1, "line": line},
        {"field": "peak_compute", "value": 5.0, "unit": "TFLOPS", "qualifier": None, "page": 1, "line": "5 TFLOPS"},
        {"field": "peak_compute", "value": 80.0, "unit": "TOPS", "qualifier": "int4", "page": 1, "line": "80 TOPS INT4"},
        {"field": "memory", "value": 64.0, "unit": "GB eMMC", "qualifier": None, "page": 2, "line": "64 GB eMMC"},
        {"field": "memory", "value": 8.0, "unit": "GB LPDDR5", "qualifier": None, "page": 2, "line": "8 GB LPDDR5"},
        {"field": "mem_bw_gbs", "value": 0.2, "unit": "TB/s", "qualifier": None, "page": 2, "line": "0.2 TB/s"},
        {"field": "power_w", "value": 15000.0, "unit": "mW", "qualifier": "typical", "page": 3, "line": "15000 mW"},
        {"field": "temperature_c", "value": -40.0, "unit": "C", "qualifier": "operating", "page": 3, "line": "x"},
        {"field": "temperature_c", "value": 105.0, "unit": "C", "qualifier": "junction", "page": 3, "line": "Tj 105 C"},
    ]  # fmt: skip
    ex = extraction_from_scan("Orinoco", cands, "orinoco.pdf")
    c = ex.candidate
    assert c["peak_tflops"] == {"int8": 40.0, "fp32": 5.0}  # INT4 is not taken as INT8
    assert c["mem_gb"] == 8.0 and c["mem_bw_gbs"] == 200.0 and c["tdp_w"] == 15.0 and c["t_throttle_c"] == 105.0
    assert ex.missing == []
    ev = {e["field"]: e for e in ex.evidence}
    assert ev["peak_tflops"]["source"] == "orinoco.pdf, page 1" and ev["peak_tflops"]["line"] == line
    assert ev["mem_gb"]["source"] == "orinoco.pdf, page 2"
