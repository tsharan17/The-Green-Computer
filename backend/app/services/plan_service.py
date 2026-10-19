"""Design plans for a project: options, analysis (baseline / each change / combined), versions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data_loader import get_device, load_cooling_catalogue
from app.db import repository as repo
from app.db.models import DesignPlanRow
from app.engine.cooling_catalogue import analyse as analyse_cooling
from app.engine.cooling_catalogue import applicable
from app.engine.evaluator import evaluate, matches
from app.engine.optimise import baseline_config
from app.engine.plan import (
    PlanChange,
    accuracy_statement,
    apply_changes,
    changes_from_result,
    diff_rows,
    scenario_view,
)
from app.schemas.hardware import HardwareProfile
from app.schemas.model import ModelProfile
from app.schemas.project import ProjectOut, ProjectSpec
from app.schemas.results import Config, EvaluationResult, OptimisationResult
from app.services import measurement_service as ms
from app.services.model_lookup import resolve_model


class PlanError(ValueError):
    pass


def _latest(db: Session, project_id: int) -> tuple[OptimisationResult, int]:
    row = repo.latest_run_row(db, project_id, "optimise")
    if row is None:
        raise PlanError("Run the analysis first: plans are built from its recommendations.")
    return OptimisationResult.model_validate(row.result), row.id


def evaluator(db: Session, spec: ProjectSpec, ws: int | None):
    """Evaluate (model, hw, cfg) with the workspace's calibration and measurements only when the
    model and hardware are the project's own, unmodified; otherwise purely analytical."""
    base_hw = get_device(spec.device_id, ws)

    def ev(model: ModelProfile, hw: HardwareProfile, cfg: Config) -> EvaluationResult:
        # Design what-ifs rename the device ("<id>+<scenario>") and catalogue cooling uses "cat-" ids,
        # so an unmodified project device is exactly: same id, a cooling option it really has.
        if hw.id == base_hw.id and not cfg.cooling_id.startswith("cat-"):
            cal = ms.active_calibrations(db, hw.id, ws).get(cfg.precision)
            meas = next((m for m in ms.measurements_for(db, hw.id, model.id, ws) if matches(m, hw, model.id, cfg)), None)
            ret = ms.measured_retention(db, model.id, ws).get(cfg.precision)
            return evaluate(model, hw, cfg, spec.workload, spec.constraints, ret, calibration=cal, measured=meas)
        return evaluate(model, hw, cfg, spec.workload, spec.constraints,
                        ms.measured_retention(db, model.id, ws).get(cfg.precision))  # fmt: skip

    return ev


def options(db: Session, project: ProjectOut, ws: int | None) -> dict[str, Any]:
    res, run_id = _latest(db, project.id)
    hw = get_device(project.spec.device_id, ws)
    from app.engine.cooling_catalogue import blockers

    usable = [e for e in applicable(load_cooling_catalogue(), hw) if not blockers(e, project.spec.environment, None)]
    changes = changes_from_result(res, usable)
    return {"source_run_id": run_id, "recommended": [a.id for a in res.advice if a.in_recommended],
            "changes": [c.model_dump() for c in changes]}  # fmt: skip


def _find(changes: list[PlanChange], ids: list[str]) -> list[PlanChange]:
    by = {c.id: c for c in changes}
    missing = [i for i in ids if i not in by]
    if missing:
        raise PlanError(f"unknown change(s): {', '.join(missing)} (run the analysis again?)")
    return [by[i] for i in dict.fromkeys(ids)]


def analyse(db: Session, project: ProjectOut, ids: list[str], ws: int | None) -> dict[str, Any]:
    if not ids:
        raise PlanError("Select at least one change.")
    spec = project.spec
    res, run_id = _latest(db, project.id)
    model = resolve_model(db, spec.model_id, ws)
    hw = get_device(spec.device_id, ws)
    cat = {e.id: e for e in load_cooling_catalogue()}
    all_changes = changes_from_result(res, applicable(list(cat.values()), hw))
    chosen = _find(all_changes, ids)
    base_cfg = spec.baseline or baseline_config(hw, spec.cooling_id)
    ev = evaluator(db, spec, ws)

    def run(sel: list[PlanChange]) -> tuple[dict[str, Any], EvaluationResult, Any]:
        m, h, applied = apply_changes(model, hw, base_cfg, sel, lambda i: resolve_model(db, i, ws),
                                      lambda i: get_device(i, ws), cat)  # fmt: skip
        r = ev(m, h, applied.config)
        return scenario_view("", m, h, r), r, applied

    try:
        base_view = scenario_view("Baseline (today)", model, hw, ev(model, hw, base_cfg))
        singles = []
        for c in chosen:
            v, r, a = run([c])
            v["label"] = c.title
            singles.append({"change": c.model_dump(), "view": v, "notes": a.notes,
                            "diff": diff_rows(base_view, v)})  # fmt: skip
        plan_view, plan_r, applied = run(chosen)
    except (ValueError, KeyError) as e:
        raise PlanError(str(e).strip("'")) from e
    plan_view["label"] = "Combined plan"
    directional = [c.title for c in chosen if c.directional]
    risks = [{"change": c.title, "risk": c.risk, "confidence": c.confidence} for c in chosen if c.risk]
    return {
        "source_run_id": run_id,
        "project_version": project.version,
        "changes": [c.model_dump() for c in chosen],
        "baseline": base_view,
        "singles": singles,
        "plan": plan_view,
        "diff": diff_rows(base_view, plan_view),
        "applied": applied.model_dump(),
        "accuracy": accuracy_statement(plan_r),
        "risks": risks,
        "directional": directional,
        "summary": _summary(base_view, plan_view),
    }


def _summary(base: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    def v(view: dict[str, Any], k: str) -> float | None:
        m = view["metrics"].get(k)
        return m["value"] if m else None

    out: dict[str, Any] = {"baseline_feasibility": base["feasibility"], "plan_feasibility": plan["feasibility"]}
    for k in ("energy_per_inference", "power_avg", "latency", "temperature", "carbon_per_day", "cost_per_day"):
        b, p = v(base, k), v(plan, k)
        if b is not None and p is not None:
            out[k] = {"baseline": b, "plan": p, "change_percent": (p / b - 1) * 100 if b else None}
    return out


def save(db: Session, project: ProjectOut, ws: int, user_id: int | None, name: str, note: str,
         ids: list[str]) -> DesignPlanRow:  # fmt: skip
    a = analyse(db, project, ids, ws)
    name = name.strip()[:200] or "Design plan"
    last = db.scalar(select(func.max(DesignPlanRow.version)).where(
        DesignPlanRow.project_id == project.id, DesignPlanRow.name == name))  # fmt: skip
    v = repo.current_version_row(db, project.id)
    row = DesignPlanRow(workspace_id=ws, project_id=project.id, project_version_id=v.id if v else None,
                        source_run_id=a["source_run_id"], name=name, version=(last or 0) + 1, note=note[:1000],
                        changes=a["changes"], analysis=a, created_by=user_id)  # fmt: skip
    db.add(row)
    db.commit()
    return row


def plan_view(row: DesignPlanRow, full: bool = False) -> dict[str, Any]:
    out = {"id": row.id, "name": row.name, "version": row.version, "note": row.note,
           "changes": [{"id": c["id"], "title": c["title"], "kind": c["kind"]} for c in row.changes],
           "summary": row.analysis.get("summary", {}), "project_version": row.analysis.get("project_version"),
           "created_by": row.created_by, "created_at": row.created_at.isoformat()}  # fmt: skip
    if full:
        out["analysis"] = row.analysis
    return out


def list_plans(db: Session, ws: int, project_id: int) -> list[dict[str, Any]]:
    rows = db.scalars(select(DesignPlanRow).where(DesignPlanRow.workspace_id == ws,
                                                  DesignPlanRow.project_id == project_id)
                      .order_by(DesignPlanRow.id.desc()))  # fmt: skip
    return [plan_view(r) for r in rows]


def get_plan(db: Session, ws: int, project_id: int, plan_id: int) -> DesignPlanRow | None:
    row = db.get(DesignPlanRow, plan_id)
    if row is None or row.workspace_id != ws or row.project_id != project_id:
        return None
    return row


def cooling_report(db: Session, project: ProjectOut, ws: int | None, which: str = "baseline") -> dict[str, Any]:
    spec = project.spec
    model = resolve_model(db, spec.model_id, ws)
    hw = get_device(spec.device_id, ws)
    cfg = spec.baseline or baseline_config(hw, spec.cooling_id)
    if which == "best":
        res, _ = _latest(db, project.id)
        if res.best is not None:
            cfg = res.best.config
    ev = evaluator(db, spec, ws)
    out = analyse_cooling(load_cooling_catalogue(), hw, cfg, spec.workload, spec.constraints.forbid_throttling,
                          lambda h, c: ev(model, h, c), spec.environment, _heat_sources(db, spec, cfg, ws))  # fmt: skip
    out["config"] = cfg.model_dump()
    out["which"] = which
    return out


def _heat_sources(db: Session, spec: ProjectSpec, cfg: Config, ws: int | None) -> dict[str, float] | None:
    """Heat per source (die, memory, regulators) from the multi-node attribution, or None."""
    from app.engine.thermal_nodes import thermal_view
    from app.services.twin_service import TraceError, compute_trace

    try:
        t = compute_trace(db, spec, cfg, ws)
    except TraceError:
        return None
    if t.thermal is None:
        return None
    hw = get_device(spec.device_id, ws)
    v = thermal_view(hw, [c.model_dump() for c in t.components], t.thermal.ambient_c, t.thermal.steady_c,
                     t.thermal.r_th_k_per_w)  # fmt: skip
    return {n["id"]: n["heat_w"] for n in v["nodes"] if n["id"] in ("compute", "memory", "power")}
