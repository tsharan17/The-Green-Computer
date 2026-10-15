from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_llm_settings
from app.data_loader import load_devices, load_models
from app.db import repository as repo
from app.engine.workload.onnx_parser import ModelParseError, manual_profile, parse_onnx
from app.schemas.hardware import HardwareProfile
from app.schemas.model import ModelProfile
from app.schemas.project import ProjectOut, ProjectSpec
from app.schemas.results import Config, EvaluationResult, OptimisationResult
from app.services import evaluation_service as svc
from app.services.project_service import SpecError, validate_refs

router = APIRouter()

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
REFUSED_EXTENSIONS = (".pt", ".pth", ".pkl", ".pickle", ".bin", ".ckpt", ".joblib")


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def _validate_refs(db: Session, spec: ProjectSpec) -> None:
    try:
        validate_refs(db, spec)
    except SpecError as e:
        raise HTTPException(422, str(e)) from e


def _project(db: Session, project_id: int) -> ProjectOut:
    p = repo.get_project(db, project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    return p


@router.get("/health")
def health() -> dict:
    from app.integrations.jobs import status as jobs_status

    jobs = jobs_status()
    return {
        "status": "ok",
        "agent": {"configured": get_llm_settings().configured},
        "jobs": {"configured": jobs.configured, "detail": jobs.reason},
    }


@router.get(
    "/models/library",
    response_model=list[ModelProfile],
    response_model_exclude={"__all__": {"layers"}},
)
def model_library(db: Session = Depends(get_db)) -> list[ModelProfile]:
    return [*load_models().values(), *repo.list_custom_models(db)]


class UploadOut(BaseModel):
    profile: ModelProfile
    warnings: list[str]


@router.post(
    "/models/upload",
    response_model=UploadOut,
    response_model_exclude={"profile": {"layers"}},
    status_code=201,
)
async def upload_model(
    request: Request,
    filename: str = "model.onnx",
    name: str | None = None,
    dynamic_dim_default: int | None = Query(None, ge=1),
    baseline_accuracy: float = 1.0,
    accuracy_metric: str = "not provided (relative accuracy only)",
    db: Session = Depends(get_db),
) -> UploadOut:
    """Raw ONNX bytes in the request body (Content-Type: application/octet-stream)."""
    if filename.lower().endswith(REFUSED_EXTENSIONS):
        raise HTTPException(415, "pickle-based and torch checkpoint files are refused; use ONNX")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file too large (limit 100 MB)")
    data = await request.body()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file too large (limit 100 MB)")
    if not 0 < baseline_accuracy <= 1:
        raise HTTPException(422, "baseline_accuracy must be in (0, 1]")
    try:
        parsed = parse_onnx(data, name or filename.rsplit(".", 1)[0], dynamic_dim_default)
    except ModelParseError as e:
        raise HTTPException(422, str(e)) from e
    profile = parsed.profile.model_copy(
        update={"baseline_accuracy": baseline_accuracy, "accuracy_metric": accuracy_metric}
    )
    return UploadOut(profile=repo.create_custom_model(db, profile), warnings=parsed.warnings)


class ManualModelIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    params_m: float = Field(gt=0)
    gflops: float = Field(gt=0)
    n_layers: int = Field(50, ge=1)
    act_mb_fp32: float | None = Field(None, gt=0)
    baseline_accuracy: float = Field(1.0, gt=0, le=1.0)
    accuracy_metric: str = "not provided (relative accuracy only)"


@router.post(
    "/models/manual",
    response_model=ModelProfile,
    response_model_exclude={"layers"},
    status_code=201,
)
def add_manual_model(body: ManualModelIn, db: Session = Depends(get_db)) -> ModelProfile:
    profile = manual_profile(
        body.name, body.params_m, body.gflops, body.n_layers, body.act_mb_fp32,
        body.baseline_accuracy, body.accuracy_metric,
    )  # fmt: skip
    return repo.create_custom_model(db, profile)


@router.get("/hardware/library", response_model=list[HardwareProfile])
def hardware_library() -> list[HardwareProfile]:
    return list(load_devices().values())


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectOut]:
    return repo.list_projects(db)


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(spec: ProjectSpec, db: Session = Depends(get_db)) -> ProjectOut:
    _validate_refs(db, spec)
    return repo.create_project(db, spec)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)) -> ProjectOut:
    return _project(db, project_id)


@router.put("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, spec: ProjectSpec, db: Session = Depends(get_db)) -> ProjectOut:
    _validate_refs(db, spec)
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
