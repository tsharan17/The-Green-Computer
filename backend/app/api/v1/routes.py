from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.data_loader import load_devices, load_models
from app.db import repository as repo
from app.schemas.hardware import HardwareProfile
from app.schemas.model import ModelProfile
from app.schemas.project import ProjectOut, ProjectSpec
from app.schemas.results import Config, EvaluationResult, OptimisationResult
from app.services import evaluation_service as svc

router = APIRouter()


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def _validate_refs(spec: ProjectSpec) -> None:
    devices, models = load_devices(), load_models()
    if spec.model_id not in models:
        raise HTTPException(422, f"unknown model '{spec.model_id}'")
    if spec.device_id not in devices:
        raise HTTPException(422, f"unknown device '{spec.device_id}'")
    hw = devices[spec.device_id]
    if spec.cooling_id and spec.cooling_id not in {c.id for c in hw.cooling_options}:
        raise HTTPException(422, f"unknown cooling '{spec.cooling_id}' for {hw.id}")


def _project(db: Session, project_id: int) -> ProjectOut:
    p = repo.get_project(db, project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    return p


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "agent": "disabled (Day 4)", "jobs": "disabled (Day 3)"}


@router.get("/models/library", response_model=list[ModelProfile])
def model_library() -> list[ModelProfile]:
    return list(load_models().values())


@router.get("/hardware/library", response_model=list[HardwareProfile])
def hardware_library() -> list[HardwareProfile]:
    return list(load_devices().values())


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectOut]:
    return repo.list_projects(db)


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(spec: ProjectSpec, db: Session = Depends(get_db)) -> ProjectOut:
    _validate_refs(spec)
    return repo.create_project(db, spec)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)) -> ProjectOut:
    return _project(db, project_id)


@router.put("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, spec: ProjectSpec, db: Session = Depends(get_db)) -> ProjectOut:
    _validate_refs(spec)
    out = repo.update_project(db, project_id, spec)
    if out is None:
        raise HTTPException(404, "project not found")
    return out


@router.post("/projects/{project_id}/evaluate", response_model=EvaluationResult)
def evaluate_project(
    project_id: int, config: Config | None = None, db: Session = Depends(get_db)
) -> EvaluationResult:
    p = _project(db, project_id)
    try:
        return svc.evaluate_project(db, p.id, p.spec, config)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/projects/{project_id}/optimise", response_model=OptimisationResult)
def optimise_project(project_id: int, db: Session = Depends(get_db)) -> OptimisationResult:
    p = _project(db, project_id)
    return svc.optimise_project(db, p.id, p.spec)
