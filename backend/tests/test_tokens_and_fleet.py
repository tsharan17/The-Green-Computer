"""Token scopes, the operator list, the fleet figures and the limit on analyses at once."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import app.engine.workload.onnx_parser as parser
from app.engine.coverage import operator_matrix
from app.main import create_app

P = "/api/v1"
CSRF = {"X-GC-CSRF": "1"}


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(db_url=f"sqlite:///{tmp_path / 't.db'}", data_dir=str(tmp_path / "d")))


def _signup(c: TestClient) -> None:
    assert c.post(f"{P}/auth/signup", headers=CSRF, json={
        "email": "t@x.io", "password": "a long passphrase here", "accept_terms": True}).status_code == 201  # fmt: skip


def test_read_token_cannot_change_anything_and_tokens_cannot_mint_tokens(tmp_path):
    with _client(tmp_path) as c:
        _signup(c)
        read = c.post(f"{P}/auth/tokens", headers=CSRF, json={"label": "ci", "scope": "read"}).json()["token"]
        full = c.post(f"{P}/auth/tokens", headers=CSRF, json={"label": "ci2"}).json()["token"]
        pid = c.get(f"{P}/projects").json()[0]["id"]
        c.post(f"{P}/auth/signout", headers=CSRF)
        for t, code in ((read, 403), (full, 200)):
            bearer = {"Authorization": f"Bearer {t}"}
            assert c.get(f"{P}/projects/{pid}", headers=bearer).status_code == 200
            assert c.post(f"{P}/projects/{pid}/optimise", headers=bearer).status_code == code
            assert c.post(f"{P}/auth/tokens", headers=bearer, json={"label": "again"}).status_code == 403


def test_every_listed_operator_is_really_in_the_parser():
    source = Path(parser.__file__).read_text(encoding="utf-8")
    loop = source[source.index("for idx, node in enumerate(g.node)"):]
    for op in operator_matrix()["own_cost_model"]:
        assert f'"{op}"' in loop, op


def test_fleet_scales_the_prediction_and_keeps_its_label(tmp_path):
    with _client(tmp_path) as c:
        _signup(c)
        pid = c.get(f"{P}/projects").json()[0]["id"]
        assert c.post(f"{P}/projects/{pid}/fleet", headers=CSRF, json={}).status_code == 409
        run = c.post(f"{P}/projects/{pid}/optimise", headers=CSRF).json()
        out = c.post(f"{P}/projects/{pid}/fleet", headers=CSRF, json={"units": 10, "years": 2}).json()
        m = run["baseline"]["metrics"]["cost_per_day"]
        assert abs(out["today"]["cost"]["value"] - m["value"] * 365 * 2 * 10) < 1e-6
        assert out["today"]["cost"]["provenance"] == m["provenance"]
        assert out["today"]["cost"]["low"] < out["today"]["cost"]["high"]
