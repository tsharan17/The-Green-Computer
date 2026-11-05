from __future__ import annotations

from sqlalchemy.orm import Session

from app.data_loader import get_device
from app.db import repository as repo
from app.engine.evaluator import evaluate, matches
from app.engine.optimise import baseline_config, optimise
from app.schemas.project import ProjectSpec
from app.schemas.results import Config, EvaluationResult, OptimisationResult
from app.services import advisor_service
from app.services import measurement_service as ms
from app.services.model_lookup import resolve_model


def evaluate_project(
    db: Session, project_id: int, spec: ProjectSpec, config: Config | None,
    workspace_id: int | None = None, user_id: int | None = None,
) -> EvaluationResult:  # fmt: skip
    ws = workspace_id
    model, hw = resolve_model(db, spec.model_id, ws), get_device(spec.device_id, ws)
    cfg = config or spec.baseline or baseline_config(hw, spec.cooling_id)
    cals = ms.active_calibrations(db, hw.id, ws)
    meas = ms.measurements_for(db, hw.id, model.id, ws)
    ret = ms.measured_retention(db, model.id, ws)
    result = evaluate(
        model, hw, cfg, spec.workload, spec.constraints, ret.get(cfg.precision),
        calibration=cals.get(cfg.precision),
        measured=next((m for m in meas if matches(m, hw, model.id, cfg)), None),
    )  # fmt: skip
    if spec.runtime:
        result.notes.append(RUNTIME_NOTE.format(spec.runtime))
    repo.save_run(db, project_id, "evaluate", result.engine_version, result.model_dump(mode="json"),
                  user_id)  # fmt: skip
    return result


RUNTIME_NOTE = "Runtime recorded as {}. Runtime overhead is not modelled yet, so this choice changes no number here."
MAX_STORED_POINTS = 800  # a chart cannot show more, and a stored run should stay small


def thin_points(result: OptimisationResult) -> None:
    """Keep the Pareto front and the best plan, and an even sample of the rest. Results are unaffected:
    `evaluated` and `counts` still describe the whole search."""
    points = result.points
    if len(points) <= MAX_STORED_POINTS:
        return
    must = [p for p in points if p.pareto or p.best]
    rest = [p for p in points if not (p.pareto or p.best)]
    room = max(0, MAX_STORED_POINTS - len(must))
    result.points = must + (rest[:: max(1, len(rest) // room)][:room] if room else [])
    result.points_thinned = True


def optimise_project(
    db: Session, project_id: int, spec: ProjectSpec, workspace_id: int | None = None,
    user_id: int | None = None,
) -> OptimisationResult:  # fmt: skip
    ws = workspace_id
    model, hw = resolve_model(db, spec.model_id, ws), get_device(spec.device_id, ws)
    result = optimise(
        spec, model, hw,
        measured=ms.measured_retention(db, model.id, ws),
        calibrations=ms.active_calibrations(db, hw.id, ws),
        measurements=ms.measurements_for(db, hw.id, model.id, ws),
    )  # fmt: skip
    advisor_service.enrich(db, spec, model, hw, result, ws)
    thin_points(result)
    if spec.runtime:
        result.baseline.notes.append(RUNTIME_NOTE.format(spec.runtime))
    repo.save_run(
        db, project_id, "optimise", result.baseline.engine_version, result.model_dump(mode="json"),
        user_id,
    )
    return result
