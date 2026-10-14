from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CalibrationRow, CustomModelRow, MeasurementRow, ProjectRow, RunRow
from app.schemas.measurement import (
    Calibration,
    CalibrationReport,
    MeasurementIn,
    MeasurementOut,
)
from app.schemas.model import ModelProfile
from app.schemas.project import ProjectOut, ProjectSpec


def _out(row: ProjectRow) -> ProjectOut:
    return ProjectOut(id=row.id, spec=ProjectSpec.model_validate(row.spec))


def create_project(db: Session, spec: ProjectSpec) -> ProjectOut:
    row = ProjectRow(name=spec.name, spec=spec.model_dump(mode="json"))
    db.add(row)
    db.commit()
    return _out(row)


def list_projects(db: Session) -> list[ProjectOut]:
    return [_out(r) for r in db.scalars(select(ProjectRow).order_by(ProjectRow.id))]


def get_project(db: Session, project_id: int) -> ProjectOut | None:
    row = db.get(ProjectRow, project_id)
    return _out(row) if row else None


def update_project(db: Session, project_id: int, spec: ProjectSpec) -> ProjectOut | None:
    row = db.get(ProjectRow, project_id)
    if row is None:
        return None
    row.name = spec.name
    row.spec = spec.model_dump(mode="json")
    db.commit()
    return _out(row)


def save_run(db: Session, project_id: int, kind: str, engine_version: str, result: dict) -> int:
    row = RunRow(project_id=project_id, kind=kind, engine_version=engine_version, result=result)
    db.add(row)
    db.commit()
    return row.id


def latest_run(db: Session, project_id: int, kind: str) -> dict | None:
    row = db.scalars(
        select(RunRow)
        .where(RunRow.project_id == project_id, RunRow.kind == kind)
        .order_by(RunRow.id.desc())
        .limit(1)
    ).first()
    return row.result if row else None


CUSTOM_PREFIX = "custom-"


def create_custom_model(db: Session, profile: ModelProfile) -> ModelProfile:
    row = CustomModelRow(name=profile.name, profile={})
    db.add(row)
    db.flush()  # assigns the integer id
    stored = profile.model_copy(update={"id": f"{CUSTOM_PREFIX}{row.id}"})
    row.profile = stored.model_dump(mode="json")
    db.commit()
    return stored


def list_custom_models(db: Session) -> list[ModelProfile]:
    rows = db.scalars(select(CustomModelRow).order_by(CustomModelRow.id))
    return [ModelProfile.model_validate(r.profile) for r in rows]


def get_custom_model(db: Session, model_id: str) -> ModelProfile | None:
    if not model_id.startswith(CUSTOM_PREFIX):
        return None
    try:
        row = db.get(CustomModelRow, int(model_id[len(CUSTOM_PREFIX) :]))
    except ValueError:
        return None
    return ModelProfile.model_validate(row.profile) if row else None


def _m_out(row: MeasurementRow) -> MeasurementOut:
    return MeasurementOut(id=row.id, created_at=row.created_at, **row.record)


def add_measurement(db: Session, m: MeasurementIn) -> tuple[MeasurementOut, bool]:
    """Insert a measurement; an already-imported external_id is returned, not duplicated."""
    if m.external_id:
        existing = db.scalars(
            select(MeasurementRow).where(MeasurementRow.external_id == m.external_id)
        ).first()
        if existing is not None:
            return _m_out(existing), False
    row = MeasurementRow(
        device_id=m.device_id,
        model_id=m.model_id,
        precision=m.precision,
        batch=m.batch,
        external_id=m.external_id,
        record=m.model_dump(mode="json"),
    )
    db.add(row)
    db.commit()
    return _m_out(row), True


def list_measurements(
    db: Session,
    device_id: str | None = None,
    model_id: str | None = None,
    precision: str | None = None,
) -> list[MeasurementOut]:
    q = select(MeasurementRow).order_by(MeasurementRow.id)
    if device_id:
        q = q.where(MeasurementRow.device_id == device_id)
    if model_id:
        q = q.where(MeasurementRow.model_id == model_id)
    if precision:
        q = q.where(MeasurementRow.precision == precision)
    return [_m_out(r) for r in db.scalars(q)]


def delete_measurement(db: Session, measurement_id: int) -> MeasurementOut | None:
    row = db.get(MeasurementRow, measurement_id)
    if row is None:
        return None
    out = _m_out(row)
    db.delete(row)
    db.commit()
    return out


def next_calibration_version(db: Session, device_id: str, precision: str) -> int:
    rows = db.scalars(
        select(CalibrationRow.version)
        .where(CalibrationRow.device_id == device_id, CalibrationRow.precision == precision)
        .order_by(CalibrationRow.version.desc())
        .limit(1)
    ).first()
    return (rows or 0) + 1


def save_calibration(db: Session, report: CalibrationReport) -> None:
    cal = report.calibration
    db.add(
        CalibrationRow(
            device_id=report.device_id,
            precision=report.precision,
            version=report.version,
            accepted=cal.latency_calibrated or cal.power_calibrated,
            calibration=cal.model_dump(mode="json"),
            report=report.model_dump(mode="json"),
        )
    )
    db.commit()


def active_calibration(db: Session, device_id: str, precision: str) -> Calibration | None:
    row = db.scalars(
        select(CalibrationRow)
        .where(
            CalibrationRow.device_id == device_id,
            CalibrationRow.precision == precision,
            CalibrationRow.accepted.is_(True),
        )
        .order_by(CalibrationRow.version.desc())
        .limit(1)
    ).first()
    return Calibration.model_validate(row.calibration) if row else None


def calibration_history(db: Session, device_id: str | None = None) -> list[dict]:
    q = select(CalibrationRow).order_by(CalibrationRow.id.desc())
    if device_id:
        q = q.where(CalibrationRow.device_id == device_id)
    return [
        {
            "device_id": r.device_id,
            "precision": r.precision,
            "version": r.version,
            "accepted": r.accepted,
            "created_at": r.created_at.isoformat(),
            "calibration": r.calibration,
            "latency": r.report["latency"],
            "power": r.report["power"],
        }
        for r in db.scalars(q)
    ]
