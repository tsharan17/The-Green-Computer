"""Workflow stages: verification, pipeline staleness, structured recommendations, AI candidates
(mocked provider), cooling sweep figures, terms consent, and isolation of every new endpoint."""

from __future__ import annotations

import pytest

from app.data_loader import clear_custom_devices, load_devices, load_models
from app.engine.verification import verify
from app.main import create_app
from app.schemas.project import ProjectSpec
from tests.helpers import TEST_PASSWORD, AuthedClient

P = "/api/v1"
OCTET = {"Content-Type": "application/octet-stream"}
PNG = b"\x89PNG"


@pytest.fixture()
def app(tmp_path):
    a = create_app(f"sqlite:///{tmp_path / 'w.db'}", data_dir=str(tmp_path / "d"))
    yield a
    clear_custom_devices()


@pytest.fixture()
def c(app):
    with AuthedClient(app) as cl:
        cl.pid = cl.get(f"{P}/projects").json()[0]["id"]  # the robot example: overheats today
        yield cl


def _stage(c, sid):
    return next(s for s in c.get(f"{P}/projects/{c.pid}/pipeline").json()["stages"] if s["id"] == sid)


# --- verification ----------------------------------------------------------------------------------


def test_verification_reports_checks_and_unsupported_files(c):
    v = c.get(f"{P}/projects/{c.pid}/verification").json()
    assert v["schema"] == "green-computer.verification/1" and v["ready_for_analysis"]
    ids = {x["id"] for x in v["checks"]}
    assert {"model.present", "hardware.present", "hardware.cooling", "fit.memory", "model.accuracy"} <= ids
    assert "not establish" in v["note"]
    c.post(f"{P}/intake/upload?filename=core.vhd&project_id={c.pid}", content=b"entity x is end;", headers=OCTET)
    v = c.get(f"{P}/projects/{c.pid}/verification").json()
    f = next(x for x in v["checks"] if x["area"] == "files")
    assert f["status"] == "info" and "not parsed" in f["message"] and f["fix"]


def test_verification_engine_fails_honestly_on_inconsistent_inputs():
    hw = load_devices(None)["jetson-orin-nx"]
    model = load_models()["yolov8s"]
    spec = ProjectSpec(name="x", model_id="yolov8s", device_id=hw.id, cooling_id="no-such-cooling")
    spec.constraints.max_power_w = 0.5
    v = verify(spec, model, hw)
    bad = {x["id"] for x in v["checks"] if x["status"] == "fail"}
    assert {"hardware.cooling", "fit.power"} <= bad and not v["ready_for_analysis"] and v["missing"]
    assert verify(spec, None, None)["counts"]["fail"] >= 2


# --- pipeline and data flow ------------------------------------------------------------------------


def test_pipeline_marks_only_dependent_records_stale_and_never_deletes(c):
    assert _stage(c, "analysis")["state"] == "ready"
    assert _stage(c, "recommendations")["state"] == "blocked"
    assert c.post(f"{P}/projects/{c.pid}/optimise").status_code == 200
    a = _stage(c, "analysis")
    assert a["state"] == "done" and a["record"]["run_id"]
    run_id = a["record"]["run_id"]

    spec = c.get(f"{P}/projects/{c.pid}").json()["spec"]
    renamed = {**spec, "name": "Renamed project"}
    assert c.put(f"{P}/projects/{c.pid}", json=renamed).status_code == 200
    assert _stage(c, "analysis")["state"] == "done"  # a rename does not change any number

    changed = {**renamed, "workload": {**spec["workload"], "ambient_c": 25}}
    assert c.put(f"{P}/projects/{c.pid}", json=changed).status_code == 200
    a = _stage(c, "analysis")
    assert a["state"] == "stale" and a["record"]["run_id"] == run_id  # kept, not discarded
    assert _stage(c, "recommendations")["state"] == "stale"
    assert c.get(f"{P}/projects/{c.pid}/runs/{run_id}").status_code == 200


# --- recommendations -------------------------------------------------------------------------------


def test_recommendations_are_structured_split_and_ranked(c):
    r = c.get(f"{P}/projects/{c.pid}/recommendations").json()
    assert r["analysed"] is False and "analysis first" in r["message"]
    c.post(f"{P}/projects/{c.pid}/optimise")
    r = c.get(f"{P}/projects/{c.pid}/recommendations").json()
    assert r["schema"] == "green-computer.recommendations/1" and r["software"] and r["hardware"]
    keys = {"problem", "change", "why", "affects", "expected", "tradeoffs", "requires", "status", "evidence", "validation"}
    for x in r["software"] + r["hardware"]:
        assert keys <= set(x) and x["status"] in ("recommended", "option", "directional", "guidance", "needs_input")
        assert x["category"] == ("software" if x["area"] in ("code", "model", "runtime", "execution") else "hardware")
        if x["status"] in ("option", "guidance", "needs_input"):
            assert not x["expected"]  # no number where the engine computed none
    assert all(x["category"] == "software" for x in r["software"])
    statuses = [x["status"] for x in r["software"] + r["hardware"]]
    assert "needs_input" in statuses  # no board or RTL file on this project: says so instead of guessing
    ranks = [x["rank"] for x in r["hardware"]]
    assert ranks == sorted(ranks)
    first = r["software"][0]
    assert first["status"] == "recommended" and first["plan_change_id"]


def test_saved_plan_turns_a_recommendation_into_an_evaluated_one(c):
    c.post(f"{P}/projects/{c.pid}/optimise")
    r = c.get(f"{P}/projects/{c.pid}/recommendations").json()
    pick = next(x for x in r["software"] if x["plan_change_id"])
    assert pick["validation"]["state"] == "not_evaluated"
    assert c.post(f"{P}/projects/{c.pid}/plans", json={"change_ids": [pick["plan_change_id"]], "name": "t"}).status_code == 201
    r = c.get(f"{P}/projects/{c.pid}/recommendations").json()
    got = next(x for x in r["software"] if x["id"] == pick["id"])
    assert got["validation"]["state"] in ("evaluated", "rejected")
    assert "not measured" in got["validation"]["method"] and got["validation"]["plan_id"]
    assert _stage(c, "validation")["state"] == "done"


# --- cooling sweep and figures ---------------------------------------------------------------------


def test_cooling_sweep_is_engine_evaluated_and_drawn(c):
    s = c.get(f"{P}/projects/{c.pid}/cooling-sweep").json()
    assert s["schema"] == "green-computer.cooling-sweep/1" and s["provenance"] == "analytical"
    o = s["options"][0]
    assert len(o["temperature_c"]) == len(s["ambient_c"]) and len(o["temperature_c"][0]) == len(s["load_fraction"])
    assert any(any(row) for row in o["throttled"])  # the example overheats at its fitted cooling
    assert "not a CFD" in s["note"]
    for name in ("cooling-headroom", "cooling-heatmap", "mode-cooling-heatmap", "cooling-surfaces"):
        r = c.get(f"{P}/projects/{c.pid}/figures/{name}")
        assert r.status_code == 200 and r.content[:4] == PNG and r.headers["content-type"] == "image/png"
    assert c.get(f"{P}/projects/{c.pid}/figures/nope").status_code == 404


# --- terms and consent -----------------------------------------------------------------------------


def test_signup_requires_explicit_consent_and_records_the_version(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as t:
        h = {"X-GC-CSRF": "1"}
        docs = t.get(f"{P}/auth/legal").json()
        assert {d["id"] for d in docs} == {"terms", "privacy", "acceptable-use", "data"}
        assert "professional legal review" in t.get(f"{P}/auth/legal/terms").json()["markdown"]
        assert t.get(f"{P}/auth/legal/nope").status_code == 404
        r = t.post(f"{P}/auth/signup", headers=h, json={"email": "t@x.io", "password": TEST_PASSWORD})
        assert r.status_code == 422 and "accept" in r.json()["detail"]
        r = t.post(f"{P}/auth/signup", headers=h, json={"email": "t@x.io", "password": TEST_PASSWORD, "accept_terms": True})
        assert r.status_code == 201
        terms = r.json()["terms"]
        assert terms["outstanding"] == [] and {a["document"] for a in terms["accepted"]} == {"terms", "privacy"}
        assert all(a["version"] and a["accepted_at"] for a in terms["accepted"])
        assert t.post(f"{P}/auth/terms/accept", headers=h).json()["outstanding"] == []
        assert len(t.get(f"{P}/auth/me").json()["terms"]["accepted"]) == 2  # idempotent


# --- isolation -------------------------------------------------------------------------------------


def test_new_endpoints_do_not_leak_across_workspaces(app, c):
    with AuthedClient(app, email="other@example.com") as o:
        for path in ("verification", "pipeline", "recommendations", "cooling-sweep", "figures/cooling-heatmap"):
            assert o.get(f"{P}/projects/{c.pid}/{path}").status_code == 404, path
    from fastapi.testclient import TestClient

    with TestClient(app) as anon:
        assert anon.get(f"{P}/projects/{c.pid}/pipeline").status_code == 401
