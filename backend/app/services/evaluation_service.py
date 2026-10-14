from __future__ import annotations

from sqlalchemy.orm import Session

from app.data_loader import get_device, get_model
from app.db import repository as repo
from app.engine.evaluator import evaluate
from app.engine.optimise import baseline_config, optimise
from app.schemas.project import ProjectSpec
from app.schemas.results import Config, EvaluationResult, OptimisationResult


def _resolve(spec: ProjectSpec):
    return get_model(spec.model_id), get_device(spec.device_id)


def evaluate_project(
    db: Session, project_id: int, spec: ProjectSpec, config: Config | None
) -> EvaluationResult:
    model, hw = _resolve(spec)
    cfg = config or baseline_config(hw, spec.cooling_id)
    result = evaluate(model, hw, cfg, spec.workload, spec.constraints)
    repo.save_run(db, project_id, "evaluate", result.engine_version, result.model_dump(mode="json"))
    return result


def optimise_project(db: Session, project_id: int, spec: ProjectSpec) -> OptimisationResult:
    model, hw = _resolve(spec)
    result = optimise(spec, model, hw)
    repo.save_run(
        db, project_id, "optimise", result.baseline.engine_version, result.model_dump(mode="json")
    )
    return result
