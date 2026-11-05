"""Measurements, calibration and verification."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import Ctx, get_db, require_ctx, require_writer
from app.data_loader import load_devices
from app.db import repository as repo
from app.engine.measure_parsers import (
    MeasurementParseError,
    parse_bench_json,
    parse_measurement_csv,
    parse_nvidia_smi_csv,
    parse_tegrastats,
)
from app.schemas.measurement import MeasurementIn, MeasurementOut, VerifyOut
from app.security import raw_body
from app.services import audit
from app.services import measurement_service as ms

router = APIRouter()


class IngestOut(BaseModel):
    created: int
    skipped_duplicates: int
    measurements: list[MeasurementOut]
    calibrations: list[dict]


def _ingest_response(db: Session, records: list[MeasurementIn], ctx: Ctx) -> IngestOut:
    try:
        stored, created, reports = ms.ingest(db, records, ctx.workspace_id)
    except ms.MeasurementError as e:
        raise HTTPException(422, str(e)) from e
    audit.audit(db, "measurements.imported", workspace_id=ctx.workspace_id, user_id=ctx.user_id,
                target_type="measurement", detail={"created": created, "submitted": len(records),
                "devices": sorted({r.device_id for r in records})}, ip=ctx.ip)  # fmt: skip
    return IngestOut(
        created=created,
        skipped_duplicates=len(records) - created,
        measurements=stored,
        calibrations=[
            {
                "device_id": r.device_id,
                "precision": r.precision,
                "version": r.version,
                "latency": r.latency.model_dump(),
                "power": r.power.model_dump(),
                "calibration": r.calibration.model_dump(),
            }
            for r in reports
        ],
    )


@router.post("/measurements", response_model=IngestOut, status_code=201)
def add_measurements(
    body: MeasurementIn | list[MeasurementIn], db: Session = Depends(get_db),
    ctx: Ctx = Depends(require_writer),
) -> IngestOut:  # fmt: skip
    return _ingest_response(db, body if isinstance(body, list) else [body], ctx)


@router.get("/measurements", response_model=list[MeasurementOut])
def list_measurements(
    device_id: str | None = None,
    model_id: str | None = None,
    precision: str | None = None,
    db: Session = Depends(get_db),
    ctx: Ctx = Depends(require_ctx),
) -> list[MeasurementOut]:
    return repo.list_measurements(db, device_id, model_id, precision, ctx.workspace_id)


@router.delete("/measurements/{measurement_id}", response_model=MeasurementOut)
def delete_measurement(
    measurement_id: int, db: Session = Depends(get_db), ctx: Ctx = Depends(require_writer)
) -> MeasurementOut:
    """Delete one of your own measurements (library measurements are read-only)."""
    out = repo.delete_measurement(db, measurement_id, ctx.workspace_id)
    if out is None:
        raise HTTPException(404, "measurement not found (library measurements cannot be deleted)")
    ms.refit(db, out.device_id, out.precision, ctx.workspace_id)
    audit.audit(db, "measurement.deleted", workspace_id=ctx.workspace_id, user_id=ctx.user_id,
                target_type="measurement", target_id=measurement_id, ip=ctx.ip)  # fmt: skip
    return out


@router.post("/measurements/import", response_model=IngestOut, status_code=201)
def import_measurements(
    format: str = Query(..., pattern="^(bench_json|json|csv|nvidia_smi_csv|tegrastats)$"),
    device_id: str | None = None,
    model_id: str | None = None,
    precision: str = "fp32",
    batch: int = 1,
    latency_ms_mean: float | None = None,
    ambient_c: float | None = None,
    db: Session = Depends(get_db),
    ctx: Ctx = Depends(require_writer),
    data: bytes = Depends(raw_body),
) -> IngestOut:
    """Body is the raw text. `bench_json` carries everything; the power-trace formats need the
    device/model/precision/batch (and optionally the latency) passed as query parameters."""
    text = data.decode("utf-8", errors="replace")
    try:
        if format in ("bench_json", "json"):
            records = parse_bench_json(text)
        elif format == "csv":
            records = parse_measurement_csv(text)
        else:
            if not device_id or not model_id:
                raise HTTPException(422, "device_id and model_id are required for trace imports")
            smi = format == "nvidia_smi_csv"
            trace = parse_nvidia_smi_csv(text) if smi else parse_tegrastats(text)
            records = [
                MeasurementIn(
                    device_id=device_id,
                    model_id=model_id,
                    precision=precision,  # type: ignore[arg-type]
                    batch=batch,
                    source="nvidia_smi" if smi else "tegrastats",
                    power_w_avg=trace.power_w_avg,
                    power_w_peak=trace.power_w_peak,
                    power_boundary="gpu_board" if smi else "module",
                    temperature_c_max=trace.temperature_c_max,
                    latency_ms_mean=latency_ms_mean,
                    ambient_c=ambient_c,
                    n_runs=trace.samples,
                    notes=f"{trace.samples} samples",
                )
            ]
    except MeasurementParseError as e:
        raise HTTPException(422, str(e)) from e
    return _ingest_response(db, records, ctx)


@router.post("/measurements/replay")
def replay_measurements(db: Session = Depends(get_db), _ctx: Ctx = Depends(require_writer)) -> dict:
    """Re-import the library measurements committed with the app (shared, idempotent)."""
    created, skipped = ms.replay_committed(db)
    return {"created": created, "skipped_duplicates": skipped}


@router.get("/calibration")
def calibration_state(
    device_id: str | None = None, db: Session = Depends(get_db), ctx: Ctx = Depends(require_ctx)
) -> dict:
    ws = ctx.workspace_id
    active = {}
    for dev in [device_id] if device_id else list(load_devices(ws)):
        for prec, c in ms.active_calibrations(db, dev, ws).items():
            active[f"{dev}/{prec}"] = c.model_dump()
    return {"active": active, "history": repo.calibration_history(db, device_id, ws)}


class RefitIn(BaseModel):
    device_id: str
    precision: str = "fp32"


@router.post("/calibration/refit")
def refit_calibration(
    body: RefitIn, db: Session = Depends(get_db), ctx: Ctx = Depends(require_writer)
) -> dict:
    if body.device_id not in load_devices(ctx.workspace_id):
        raise HTTPException(422, f"unknown device '{body.device_id}'")
    return ms.refit(db, body.device_id, body.precision, ctx.workspace_id).model_dump()


@router.get("/verify", response_model=VerifyOut)
def verify(
    device_id: str | None = None, db: Session = Depends(get_db), ctx: Ctx = Depends(require_ctx)
) -> VerifyOut:
    return ms.verify(db, device_id, ctx.workspace_id)
