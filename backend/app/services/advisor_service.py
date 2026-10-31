"""Adds plain-language advice (all four levels), alternatives, what-ifs and the limiting factor
to an optimisation result, using the same calibration/measurement context as the search."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.data_loader import load_devices, load_models
from app.db import repository as repo
from app.engine.advisor import build_advice
from app.engine.alternatives import device_alternatives, model_alternatives
from app.engine.evaluator import evaluate
from app.engine.optimise import make_evaluator
from app.engine.whatif import limiting_factor, make_whatifs
from app.schemas.hardware import HardwareProfile
from app.schemas.measurement import Calibration
from app.schemas.model import ModelProfile
from app.schemas.project import ProjectSpec
from app.schemas.results import Config, EvaluationResult, OptimisationResult
from app.services import measurement_service as ms

# No workspace owns this id, so only built-in devices are listed (None would add owner-less ones).
BUILTIN_ONLY = -1


def enrich(
    db: Session,
    spec: ProjectSpec,
    model: ModelProfile,
    hw: HardwareProfile,
    res: OptimisationResult,
    workspace_id: int | None = None,
) -> OptimisationResult:
    ws = workspace_id
    ev = make_evaluator(
        model, hw, spec.workload, spec.constraints,
        measured=ms.measured_retention(db, model.id, ws),
        calibrations=ms.active_calibrations(db, hw.id, ws),
        measurements=ms.measurements_for(db, hw.id, model.id, ws),
    )  # fmt: skip
    models = [*load_models().values(), *repo.list_custom_models(db, ws)]
    return enrich_with(spec, model, hw, res, ev, models, list(load_devices(ws).values()),
                       ms.active_calibrations(db, hw.id, ws), lambda d: ms.active_calibrations(db, d, ws))  # fmt: skip


def enrich_builtin(spec: ProjectSpec, model: ModelProfile, hw: HardwareProfile,
                   res: OptimisationResult) -> OptimisationResult:  # fmt: skip
    """The same advice from built-in models and devices only, with no measurements. Reads no database."""
    ev = make_evaluator(model, hw, spec.workload, spec.constraints)
    return enrich_with(spec, model, hw, res, ev, list(load_models().values()),
                       list(load_devices(BUILTIN_ONLY).values()), {}, lambda _d: {})  # fmt: skip


def enrich_with(
    spec: ProjectSpec,
    model: ModelProfile,
    hw: HardwareProfile,
    res: OptimisationResult,
    ev: Callable[[Config], EvaluationResult],
    models: list[ModelProfile],
    devices: list[HardwareProfile],
    cals: dict[str, Calibration],
    cals_for: Callable[[str], dict[str, Calibration]],
) -> OptimisationResult:
    def ev_hw(hw2: HardwareProfile, cfg: Config) -> EvaluationResult:
        # What-ifs compare analytical to analytical: a calibration would not apply to a changed chip.
        return evaluate(model, hw2, cfg, spec.workload, spec.constraints)

    base_cfg = res.baseline.config
    best_cfg = res.best.config if res.best else base_cfg
    res.whatifs = make_whatifs(ev_hw, hw, best_cfg, base_cfg)
    res.limiting_factor = limiting_factor(ev_hw, hw, base_cfg)
    res.alternatives = [
        *model_alternatives(spec, model, hw, models, res.baseline, cals, res.best),
        *device_alternatives(spec, model, hw, devices, res.baseline, cals_for, res.best),
    ]
    res.advice = build_advice(
        ev, hw, res.baseline, res.best, res.alternatives, res.whatifs, res.limiting_factor
    )
    return res
