"""Every route that takes an id, read from the OpenAPI schema, is tried across two workspaces.

Bob tries each one with Alice's ids, and again inside his own project with Alice's child ids (in the
path and in the body). None may succeed or echo Alice's data. A route added later is swept too; one
that needs a new id makes the test fail until it is added to ``IDS`` below.
"""

from __future__ import annotations

import re
import time

import pytest

from app.data_loader import clear_custom_devices
from app.main import create_app
from tests.helpers import AuthedClient, tiny_cnn_bytes

P = "/api/v1"
OCTET = {"Content-Type": "application/octet-stream"}
SECRET = "Alice-secret-7f3a"
PUBLIC = {"/auth/legal/{doc}"}
DEVICE_TOKEN_ONLY = ("/device-agent/",)  # signed with a device token: a session gets 401


@pytest.fixture()
def app(tmp_path):
    a = create_app(f"sqlite:///{tmp_path / 's.db'}", data_dir=str(tmp_path / "d"))
    yield a
    clear_custom_devices()


def _wait(c, pid, job_id):
    t0 = time.time()
    while time.time() - t0 < 120:
        if c.get(f"{P}/projects/{pid}/executions/{job_id}").json()["status"] in ("succeeded", "failed"):
            return
        time.sleep(0.3)
    raise AssertionError("run did not finish")


def _alice(c) -> dict:
    """Create one of everything Alice can own, named so a leak is easy to spot."""
    up = c.post(f"{P}/models/upload?filename={SECRET}.onnx", content=tiny_cnn_bytes(random_weights=True),
                headers=OCTET).json()  # fmt: skip
    pid = c.post(f"{P}/projects", json={"name": SECRET, "model_id": up["profile"]["id"],
                                        "device_id": "jetson-orin-nano"}).json()["id"]  # fmt: skip
    assert c.post(f"{P}/projects/{pid}/optimise").status_code == 200
    opts = c.get(f"{P}/projects/{pid}/plan-options").json()
    plan = c.post(f"{P}/projects/{pid}/plans", json={"change_ids": opts["recommended"], "name": SECRET}).json()
    trace = c.post(f"{P}/projects/{pid}/traces?which=baseline").json()
    export = c.post(f"{P}/projects/{pid}/exports", json={"kind": "plan_json", "plan_id": plan["id"]}).json()
    job = c.post(f"{P}/projects/{pid}/executions", json={"runs": 3, "warmup": 0}).json()
    _wait(c, pid, job["id"])
    graph = c.get(f"{P}/projects/{pid}/system-graph").json()
    assert c.post(f"{P}/projects/{pid}/system-graph", json={"graph": graph["graph"], "note": SECRET}).status_code < 300
    draft = c.post(f"{P}/hardware/manual", json={"name": SECRET, "peak_tflops": {"fp16": 2.0},
                                                 "mem_bw_gbs": 20, "mem_gb": 2}).json()  # fmt: skip
    custom = c.post(f"{P}/hardware/custom", json={"name": SECRET, "style": "generic", "peak_tops": {"fp16": 2.0},
                                                  "mem_bw_gbs": 20, "mem_gb": 2, "tdp_w": 8}).json()  # fmt: skip
    meas = c.post(f"{P}/measurements", json={"device_id": "jetson-orin-nx", "model_id": "yolov8s",
                                             "precision": "fp16", "latency_ms_mean": 12.0,
                                             "external_id": SECRET}).json()["measurements"][0]  # fmt: skip
    remote = c.post(f"{P}/remote-devices", json={"name": SECRET, "device_id": "jetson-orin-nano"}).json()
    return {
        "project_id": pid, "artifact_id": up["artifact_id"], "plan_id": plan["id"], "trace_id": trace["id"],
        "export_id": export["id"], "job_id": job["id"], "run_id": c.get(f"{P}/projects/{pid}/runs").json()[0]["id"],
        "draft_id": draft["draft_id"] if "draft_id" in draft else draft["id"], "measurement_id": meas["id"],
        "device_id": custom["id"], "remote_device_id": remote["id"],
        "session_id": c.get(f"{P}/auth/sessions").json()[0]["id"], "user_id": c.get(f"{P}/auth/me").json()["user"]["id"],
        "version": 1, "name": "cooling-headroom",
    }  # fmt: skip


def _body(path: str, method: str, ids: dict, own: dict) -> dict | None:
    """A valid body, so a refusal comes from the access check and not from validation."""
    if method not in ("post", "put") or path.endswith(("/evaluate", "/layers", "/traces")):
        return None  # these take an optional configuration; none means the project's own
    if path.endswith("/plans") or "/plans/" in path:
        return {"change_ids": own["changes"]}
    if path.endswith("/exports"):
        return {"kind": "plan_json", "plan_id": ids["plan_id"]}
    if path.endswith("/executions"):
        return {"runs": 3, "warmup": 0}
    if path.endswith("/system-graph"):
        return {"graph": own["graph"]}
    if path.endswith("/from-files"):
        return {"artifact_ids": [ids["artifact_id"]]}
    if path.endswith("/archive"):
        return {"archived": True}
    if path.endswith("/jobs") and "remote-devices" in path:
        return {"project_id": ids["project_id"], "artifact_id": ids["artifact_id"]}
    if path == "/projects/{project_id}" and method == "put":
        return {"name": "x", "model_id": "yolov8s", "device_id": "jetson-orin-nx"}
    return {}


def _mentions(body: dict | None, a: dict) -> bool:
    """Does the body carry one of Alice's object ids?"""
    theirs = {a["project_id"], a["plan_id"], a["artifact_id"]}
    vals = [v for x in (body or {}).values() for v in (x if isinstance(x, list) else [x])]
    return any(v in theirs for v in vals if isinstance(v, (int, str)) and not isinstance(v, bool))


def _fill(path: str, ids: dict) -> str:
    def one(m: re.Match) -> str:
        key = m.group(1)
        if key == "device_id":
            key = "remote_device_id" if path.startswith("/remote-devices") else "device_id"
        if key == "name" and "/traces/" in path:
            return "thermal-board"
        assert key in ids, f"new path parameter {key!r} in {path}: add it to the sweep"
        return str(ids[key])

    return re.sub(r"\{(\w+)\}", one, path)


def test_no_route_lets_one_workspace_reach_another(app):
    with AuthedClient(app, email="alice@x.io") as alice:
        a = _alice(alice)

    routes = [(p[len(P):], m) for p, ops in app.openapi()["paths"].items() if "{" in p
              for m in ops if p[len(P):] not in PUBLIC]  # fmt: skip
    assert len(routes) > 50

    with AuthedClient(app, email="bob@x.io") as bob:
        bpid = bob.get(f"{P}/projects").json()[0]["id"]
        assert bob.post(f"{P}/projects/{bpid}/optimise").status_code == 200
        own = {"changes": bob.get(f"{P}/projects/{bpid}/plan-options").json()["recommended"],
               "graph": bob.get(f"{P}/projects/{bpid}/system-graph").json()["graph"]}  # fmt: skip
        bob_dev = bob.post(f"{P}/remote-devices", json={"name": "b", "device_id": "jetson-orin-nano"}).json()["id"]

        tried, leaks = 0, []
        for path, method in routes:
            variants = [a]  # Alice's ids everywhere
            if "{project_id}" in path:  # Bob's own project, Alice's child ids in the path and body
                variants.append({**a, "project_id": bpid})
            if path.startswith("/remote-devices/{device_id}/jobs"):  # Bob's device, Alice's project and file
                variants.append({**a, "remote_device_id": bob_dev})
            for ids in variants:
                # version numbers and figure names are not owned ids: with Bob's project they are his own
                own_only = ids is not a and set(re.findall(r"\{(\w+)\}", path)) - {"version", "name"} == {"project_id"}
                body = _body(path, method, a if ids is not a else ids, own)
                if own_only and not _mentions(body, a):
                    continue  # nothing of Alice's in this request: Bob's own data, not a cross-tenant try
                kw = {"params": {"from": 1, "to": 1}} if path.endswith("/diff") else {}
                r = getattr(bob, method)(f"{P}{_fill(path, ids)}", **({"json": body} if body is not None else {}), **kw)
                tried += 1
                expected = 401 if path.startswith(DEVICE_TOKEN_ONLY) else 404
                if r.status_code < 400 or SECRET in r.text or r.status_code not in (expected, 422 if body else -1):
                    leaks.append((method.upper(), path, ids is a, r.status_code, r.text[:160]))
        assert not leaks, "\n".join(map(str, leaks))
        assert tried > 60
        assert SECRET not in str(bob.get(f"{P}/audit").json()) + str(bob.get(f"{P}/projects").json())
