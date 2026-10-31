"""Try it without an account: the built-in example cases, analysed by the engine, read only.

Public and rate limited. Only built-in models and devices are used and nothing is read from or
written to the database, so no visitor can see another's data or leave anything behind. The
results are the same predicted analysis a signed-in user gets for the same setup.
"""

from __future__ import annotations

from functools import cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.data_loader import get_model, load_devices
from app.engine.optimise import optimise
from app.security import limit_analyse
from app.services import guide_service as guide
from app.services.advisor_service import BUILTIN_ONLY, enrich_builtin

router = APIRouter(tags=["try"])
CASES = {c["id"]: c for c in guide.USE_CASES}


@router.get("/try/examples")
def examples() -> list[dict[str, Any]]:
    return [{k: c[k] for k in ("id", "title", "blurb", "category")} for c in guide.USE_CASES]


@cache
def _analysis(case_id: str) -> dict[str, Any]:
    case = CASES[case_id]
    hw = load_devices(BUILTIN_ONLY)[case["device_id"]]
    model = get_model(case["model_id"])
    spec = guide.spec_for(case, hw=hw)
    res = enrich_builtin(spec, model, hw, optimise(spec, model, hw))
    return {
        "case": {k: case[k] for k in ("id", "title", "blurb", "category")},
        "spec": spec.model_dump(mode="json"),
        "model": {"id": model.id, "name": model.name},
        "device": {"id": hw.id, "name": hw.name},
        # The search's scatter of every point tried is large and only drawn in the full app.
        "result": res.model_dump(mode="json", exclude={"points", "top"}),
        "note": "Predicted by the analytical engine for the example setup. No measurements are used.",
    }


@router.get("/try/examples/{case_id}", dependencies=[Depends(limit_analyse)])
def example(case_id: str) -> dict[str, Any]:
    if case_id not in CASES:
        raise HTTPException(404, "unknown example")
    return _analysis(case_id)
