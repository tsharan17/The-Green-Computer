"""Input ranges, sign-in, reset links, invitations, download names and huge ids."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth.passwords import password_problem
from app.main import create_app
from app.schemas.project import Constraints, Workload
from app.security import attachment
from app.services.evaluation_service import MAX_STORED_POINTS

P = "/api/v1"
CSRF = {"X-GC-CSRF": "1"}
PW = "a long enough passphrase"


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(db_url=f"sqlite:///{tmp_path / 't.db'}", data_dir=str(tmp_path / "d")))


def _signup(c: TestClient, email: str) -> dict:
    r = c.post(f"{P}/auth/signup", headers=CSRF, json={"email": email, "password": PW, "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    return r.json()


@pytest.mark.parametrize("bad", [{"ambient_c": 5000}, {"ambient_c": -300}, {"fps": 0}, {"fps": float("inf")}])
def test_workload_rejects_impossible_values(bad):
    with pytest.raises(ValidationError):
        Workload(**bad)


@pytest.mark.parametrize("bad", [{"max_power_w": 0}, {"max_power_w": float("nan")}, {"max_latency_ms": -1}])
def test_constraints_reject_impossible_values(bad):
    with pytest.raises(ValidationError):
        Constraints(**bad)


@pytest.mark.parametrize("pw", ["password123", "Welcome2026!", "qwerty123456", "thegreencomputer"])
def test_common_passwords_are_refused(pw):
    assert password_problem(pw) is not None


def test_a_real_passphrase_is_accepted():
    assert password_problem("violet stapler orbit 42") is None


def test_download_name_survives_any_characters():
    h = attachment('modèle "1"\r\n.onnx')
    h.encode("latin-1")  # must be sendable as a header
    assert "\r" not in h and "\n" not in h and "filename*=UTF-8''" in h


def test_huge_ids_are_not_found_rather_than_errors(tmp_path):
    with _client(tmp_path) as c:
        _signup(c, "big@x.io")
        assert c.get(f"{P}/projects/{10**40}").status_code == 404
        assert c.get(f"{P}/projects", headers={"X-GC-Workspace": str(10**40)}).status_code == 403


def test_invitation_needs_consent_and_reveals_nothing(tmp_path):
    with _client(tmp_path) as c:
        _signup(c, "guest@x.io")
        c.post(f"{P}/auth/signout", headers=CSRF)
        _signup(c, "boss@x.io")
        ws = c.post(f"{P}/workspaces", headers=CSRF, json={"name": "Team"}).json()["id"]
        h = {**CSRF, "X-GC-Workspace": str(ws)}
        known = c.post(f"{P}/workspaces/current/members", headers=h, json={"email": "guest@x.io", "role": "viewer"})
        unknown = c.post(f"{P}/workspaces/current/members", headers=h, json={"email": "nobody@x.io", "role": "viewer"})
        assert known.status_code == unknown.status_code == 201
        assert set(known.json()) == set(unknown.json())
        assert "user_id" not in known.json()
        assert len(c.get(f"{P}/workspaces/current/members", headers=h).json()) == 1  # nobody joined
        assert len(c.get(f"{P}/workspaces/current/invitations", headers=h).json()) == 2
        c.post(f"{P}/auth/signout", headers=CSRF)
        c.post(f"{P}/auth/signin", headers=CSRF, json={"email": "guest@x.io", "password": PW})
        inv = c.get(f"{P}/invitations", headers=CSRF).json()
        assert [i["workspace"] for i in inv] == ["Team"]
        assert c.post(f"{P}/invitations/{inv[0]['id']}/decline", headers=CSRF).json() == {"declined": True}
        assert c.get(f"{P}/invitations", headers=CSRF).json() == []
        assert c.get(f"{P}/projects", headers={"X-GC-Workspace": str(ws)}).status_code == 403


def test_someone_elses_invitation_cannot_be_accepted(tmp_path):
    with _client(tmp_path) as c:
        _signup(c, "boss2@x.io")
        ws = c.post(f"{P}/workspaces", headers=CSRF, json={"name": "T"}).json()["id"]
        h = {**CSRF, "X-GC-Workspace": str(ws)}
        iid = c.post(f"{P}/workspaces/current/members", headers=h, json={"email": "them@x.io"}).json()["id"]
        c.post(f"{P}/auth/signout", headers=CSRF)
        _signup(c, "thief@x.io")
        assert c.post(f"{P}/invitations/{iid}/accept", headers=CSRF).status_code == 404


def test_a_new_reset_link_replaces_the_old_one(tmp_path):
    with _client(tmp_path) as c:
        _signup(c, "reset@x.io")
        first = c.post(f"{P}/auth/password/forgot", headers=CSRF, json={"email": "reset@x.io"}).json()["dev_reset_url"]
        second = c.post(f"{P}/auth/password/forgot", headers=CSRF, json={"email": "reset@x.io"}).json()["dev_reset_url"]
        old, new = first.split("token=")[1], second.split("token=")[1]
        assert c.post(f"{P}/auth/password/reset", headers=CSRF, json={"token": old, "password": PW + "1"}).status_code == 400
        assert c.post(f"{P}/auth/password/reset", headers=CSRF, json={"token": new, "password": PW + "1"}).status_code == 200


def test_stored_runs_keep_the_front_and_stay_small(tmp_path):
    from app.schemas.results import OptimisationResult
    from app.services.evaluation_service import thin_points

    class R:
        points = [type("P", (), {"pareto": i % 500 == 0, "best": i == 7})() for i in range(5000)]
        points_thinned = False

    r = R()
    must = sum(1 for p in r.points if p.pareto or p.best)
    thin_points(r)  # type: ignore[arg-type]
    assert r.points_thinned and len(r.points) <= MAX_STORED_POINTS
    assert sum(1 for p in r.points if p.pareto or p.best) == must
    assert "points_thinned" in OptimisationResult.model_fields
