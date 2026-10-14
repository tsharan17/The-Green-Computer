from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CustomModelRow, ProjectRow, RunRow
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
