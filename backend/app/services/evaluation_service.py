from __future__ import annotations

from sqlalchemy.orm import Session

from app.data_loader import get_device, get_model, load_models
from app.db import repository as repo
from app.engine.evaluator import evaluate
from app.engine.optimise import baseline_config, optimise
from app.schemas.model import ModelProfile
from app.schemas.project import ProjectSpec
from app.schemas.results import Config, EvaluationResult, OptimisationResult


def resolve_model(db: Session, model_id: str) -> ModelProfile:
    custom = repo.get_custom_model(db, model_id)
    if custom is not None:
        return custom
    if model_id in load_models():
        return get_model(model_id)
    raise KeyError(f"unknown model '{model_id}'")


def evaluate_project(
    db: Session, project_id: int, spec: ProjectSpec, config: Config | None
) -> EvaluationResult:
    model, hw = resolve_model(db, spec.model_id), get_device(spec.device_id)
    cfg = config or baseline_config(hw, spec.cooling_id)
    result = evaluate(model, hw, cfg, spec.workload, spec.constraints)
    repo.save_run(db, project_id, "evaluate", result.engine_version, result.model_dump(mode="json"))
    return result


def optimise_project(db: Session, project_id: int, spec: ProjectSpec) -> OptimisationResult:
    model, hw = resolve_model(db, spec.model_id), get_device(spec.device_id)
    result = optimise(spec, model, hw)
    repo.save_run(
        db, project_id, "optimise", result.baseline.engine_version, result.model_dump(mode="json")
    )
    return result
