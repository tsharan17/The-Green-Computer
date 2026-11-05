"""Estimates and public facts that need no project: language models, accuracy so far, sign-up funnel."""

from __future__ import annotations

import hmac
import os
import statistics
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.api.v1.auth import _csrf
from app.api.v1.routes import project_for
from app.auth.deps import Ctx, get_db, optional_ctx, require_ctx
from app.data_loader import get_device, load_devices
from app.db import repository as repo
from app.db.models import (
    CustomModelRow,
    DesignPlanRow,
    ExportRow,
    MeasurementRow,
    ProjectRow,
    RunRow,
    UserRow,
)
from app.engine.coverage import operator_matrix
from app.engine.llm import LAYERS_DEFAULT, estimate_llm
from app.security import limit_analyse
from app.services import measurement_service as ms

router = APIRouter(tags=["estimates"])


class LlmIn(BaseModel):
    device_id: str = Field(max_length=120)
    params_m: float = Field(gt=0, le=5_000_000, allow_inf_nan=False)
    precision: Literal["fp32", "fp16", "int8"] = "int8"
    prompt_tokens: int = Field(256, ge=1, le=1_000_000)
    context_tokens: int = Field(2048, ge=1, le=2_000_000)
    layers: int = Field(LAYERS_DEFAULT, ge=1, le=500)


@router.get("/estimate/llm/devices")
def llm_devices(ctx: Ctx | None = Depends(optional_ctx)) -> list[dict[str, Any]]:
    ws = ctx.workspace_id if ctx else None
    return [{"id": d.id, "name": d.name, "precisions": sorted(p for p, v in d.peak_tflops.items() if v > 0)}
            for d in sorted(load_devices(ws).values(), key=lambda d: d.name)]  # fmt: skip


@router.post("/estimate/llm", dependencies=[Depends(_csrf), Depends(limit_analyse)])
def llm_estimate(body: LlmIn, ctx: Ctx | None = Depends(optional_ctx)) -> dict[str, Any]:
    """Tokens per second and memory for a language model. Labelled predicted, and not yet validated."""
    try:
        hw = get_device(body.device_id, ctx.workspace_id if ctx else None)
    except KeyError:
        raise HTTPException(404, "unknown device") from None
    try:
        return estimate_llm(hw, body.params_m, body.precision, body.prompt_tokens, body.context_tokens, body.layers)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/operators")
def operators() -> dict[str, list[str]]:
    """The ONNX operators the parser counts. Any other operator is named as a gap in the results."""
    return operator_matrix()


class FleetIn(BaseModel):
    units: int = Field(1000, ge=1, le=100_000_000)
    years: float = Field(3.0, gt=0, le=30, allow_inf_nan=False)


@router.post("/projects/{project_id}/fleet")
def fleet(project_id: int, body: FleetIn, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Running cost and carbon for many units over years, today and with the best setup, from the
    latest analysis. Each figure keeps the range and label of the prediction it scales."""
    p = project_for(db, ctx, project_id)
    run = repo.latest_run(db, p.id, "optimise")
    if run is None:
        raise HTTPException(409, "Run the analysis first.")
    days = 365.0 * body.years * body.units

    def scaled(res: dict[str, Any] | None) -> dict[str, Any] | None:
        if res is None:
            return None
        out = {}
        for key, name in (("cost_per_day", "cost"), ("carbon_per_day", "carbon")):
            m = res["metrics"][key]
            out[name] = {"value": m["value"] * days, "low": m["low"] * days, "high": m["high"] * days,
                         "provenance": m["provenance"], "unit_per_day": m["unit"]}  # fmt: skip
        return out

    return {"units": body.units, "years": body.years, "today": scaled(run["baseline"]), "best": scaled(run.get("best")),
            "excludes": "Hardware purchase, cooling infrastructure and networks are not included."}  # fmt: skip


@router.get("/accuracy")
def accuracy(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Predictions against the real runs that ship with the product. Nothing from any user's workspace."""
    out = ms.verify(db, None, None)
    rows = [{
        "device_id": r.measurement.device_id, "model_id": r.measurement.model_id, "precision": r.measurement.precision,
        "batch": r.measurement.batch,
        "predicted_ms": round(r.predicted_ms, 3), "measured_ms": round(r.predicted_ms / (1 + r.error_before), 3),
        "error_percent": round(100 * r.error_before, 1),
    } for r in out.rows if r.error_before is not None]  # fmt: skip
    errors = [abs(float(r["error_percent"])) for r in rows]  # type: ignore[arg-type]
    return {
        "rows": rows, "runs": len(rows), "devices": len({r["device_id"] for r in rows}),
        "median_abs_error_percent": round(statistics.median(errors), 1) if errors else None,
        "power_runs": sum(1 for r in out.rows if r.measured_power_w is not None),
        "note": "Latency before any correction, against runs on one development computer. These runs say little "
                "about other hardware. Power and heat have not been checked against real measurements.",
    }  # fmt: skip


@router.get("/ops/funnel", include_in_schema=False)
def funnel(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    """How far accounts get, as totals from existing tables. For the operator (GC_METRICS_TOKEN)."""
    token = os.environ.get("GC_METRICS_TOKEN", "")
    given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(404, "off (set GC_METRICS_TOKEN)")
    if not hmac.compare_digest(given, token):
        raise HTTPException(401, "unauthorised")

    def count(q: Any) -> int:
        return int(db.scalar(q) or 0)

    since = datetime.now(UTC) - timedelta(days=30)
    return {
        "accounts": count(select(func.count()).select_from(UserRow)),
        "accounts_last_30_days": count(select(func.count()).select_from(UserRow).where(UserRow.created_at >= since)),
        "email_confirmed": count(select(func.count()).select_from(UserRow).where(UserRow.email_verified_at.is_not(None))),
        "ran_an_analysis": count(select(func.count(distinct(RunRow.user_id))).where(RunRow.user_id.is_not(None))),
        "projects": count(select(func.count()).select_from(ProjectRow)),
        "workspaces_with_own_model": count(select(func.count(distinct(CustomModelRow.workspace_id)))),
        "workspaces_with_a_plan": count(select(func.count(distinct(DesignPlanRow.workspace_id)))),
        "workspaces_with_an_export": count(select(func.count(distinct(ExportRow.workspace_id)))),
        "workspaces_with_a_measurement": count(select(func.count(distinct(MeasurementRow.workspace_id))).where(
            MeasurementRow.workspace_id.is_not(None))),
    }  # fmt: skip
