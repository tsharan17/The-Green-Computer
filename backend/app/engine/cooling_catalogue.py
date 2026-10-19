"""Cooling options from the catalogue, evaluated for one project, ranked by stated criteria.

"Lower impact" is never asserted without numbers. The criteria, in order:
  1. Requirements: the option must keep the project's thermal requirement (no sustained throttling
     when that is required) and every other requirement the evaluation checks.
  2. Lifetime emissions per year = electricity of device + fan/pump at the project's duty and grid
     intensity, plus the cooling hardware's embodied carbon spread over its service life.
  3. Tie-breakers shown, not scored: maintainability (moving parts), recyclability, noise, cost.
An option is labelled "lower impact" only if it meets requirement 1 and is within 10% of the lowest
lifetime emissions among options that do. Embodied figures are low-confidence estimates and are
labelled so.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from app.schemas.hardware import CoolingOption, HardwareProfile
from app.schemas.metrics import Feasibility
from app.schemas.project import Workload
from app.schemas.results import Config, EvaluationResult

CRITERIA = [
    "Meets your requirements with this cooling (no sustained throttling if you require that).",
    "Lowest lifetime emissions per year: device and fan/pump electricity at your hours and grid "
    "intensity, plus the cooling hardware's embodied carbon over its service life.",
    "Shown for judgement, not scored: maintainability, recyclability, noise, cost.",
]
LOWER_IMPACT_MARGIN = 0.10


class Range(BaseModel):
    low: float
    typical: float
    high: float


class CostRange(BaseModel):
    low: float
    high: float


class CoolingEntry(BaseModel):
    id: str
    name: str
    type: str
    applies_to: list[str]
    r_th_k_per_w: Range | None = None
    r_th_factor: Range | None = None
    active_w: float
    c_th_j_per_k: float
    cost_usd: CostRange
    noise_dba: float
    materials: str
    embodied_kgco2e: float
    recyclability: str
    maintainability: str
    lifetime_years: float
    confidence: str
    source: str


def applicable(entries: list[CoolingEntry], hw: HardwareProfile) -> list[CoolingEntry]:
    return [e for e in entries if hw.kind in e.applies_to]


def to_option(entry: CoolingEntry, current: CoolingOption) -> CoolingOption:
    """A device cooling option for this entry. Modifiers scale the cooling already fitted."""
    if entry.r_th_factor is not None:
        r = current.r_th_k_per_w * entry.r_th_factor.typical
        return CoolingOption(id=f"cat-{entry.id}", name=f"{current.name} + {entry.name.lower()}",
                             r_th_k_per_w=r, fan_w=current.fan_w + entry.active_w,
                             c_th_j_per_k=current.c_th_j_per_k)  # fmt: skip
    assert entry.r_th_k_per_w is not None
    return CoolingOption(id=f"cat-{entry.id}", name=entry.name, r_th_k_per_w=entry.r_th_k_per_w.typical,
                         fan_w=entry.active_w, c_th_j_per_k=max(entry.c_th_j_per_k, 1.0))  # fmt: skip


def with_option(hw: HardwareProfile, opt: CoolingOption) -> HardwareProfile:
    return hw.model_copy(update={"cooling_options": [*[c for c in hw.cooling_options if c.id != opt.id], opt]})


def analyse(
    entries: list[CoolingEntry],
    hw: HardwareProfile,
    cfg: Config,
    workload: Workload,
    forbid_throttling: bool,
    evaluate_with: Callable[[HardwareProfile, Config], EvaluationResult],
) -> dict[str, Any]:
    current = hw.cooling(cfg.cooling_id)
    base = evaluate_with(hw, cfg)
    kwh_per_w_year = workload.hours_per_day * 365 / 1000.0
    grid = workload.grid_gco2_per_kwh / 1000.0
    rows: list[dict[str, Any]] = []

    def row(name: str, entry: CoolingEntry | None, opt: CoolingOption, r: EvaluationResult) -> dict[str, Any]:
        p = r.metrics["power_avg"].value  # includes fan/pump power (power model floor)
        op_kg = p * kwh_per_w_year * grid
        emb = (entry.embodied_kgco2e / max(entry.lifetime_years, 0.5)) if entry else 0.0
        meets = r.feasibility in (Feasibility.PREDICTED_FEASIBLE, Feasibility.VERIFIED_FEASIBLE,
                                  Feasibility.UNCERTAIN)  # fmt: skip
        thermal_ok = not (forbid_throttling and r.solver.throttled)
        return {
            "id": entry.id if entry else "current",
            "change_id": f"cooling:{entry.id}" if entry else None,
            "name": name,
            "type": entry.type if entry else "fitted",
            "r_th_k_per_w": opt.r_th_k_per_w,
            "active_w": opt.fan_w,
            "temperature_c": r.metrics["temperature"].value,
            "unthrottled_c": r.metrics["temperature_unthrottled"].value,
            "throttled": r.solver.throttled,
            "clock_factor": r.solver.clock_factor,
            "power_w": p,
            "energy_mj": r.metrics["energy_per_inference"].value,
            "feasibility": r.feasibility.value,
            "meets_requirements": meets and thermal_ok,
            "operational_kgco2e_per_year": op_kg,
            "embodied_kgco2e_per_year": emb,
            "lifetime_kgco2e_per_year": op_kg + emb,
            "electricity_kwh_per_year": p * kwh_per_w_year,
            "cost_usd": entry.cost_usd.model_dump() if entry else None,
            "noise_dba": entry.noise_dba if entry else None,
            "materials": entry.materials if entry else "",
            "recyclability": entry.recyclability if entry else None,
            "maintainability": entry.maintainability if entry else "",
            "lifetime_years": entry.lifetime_years if entry else None,
            "confidence": entry.confidence if entry else "device profile",
            "source": entry.source if entry else "the device profile's cooling option",
            "r_th_range": (entry.r_th_k_per_w or entry.r_th_factor).model_dump() if entry else None,  # type: ignore[union-attr]
            "modifier": bool(entry and entry.r_th_factor is not None),
        }

    rows.append(row(f"Fitted today: {current.name}", None, current, base))
    for e in applicable(entries, hw):
        opt = to_option(e, current)
        hw2 = with_option(hw, opt)
        try:
            r = evaluate_with(hw2, cfg.model_copy(update={"cooling_id": opt.id}))
        except ValueError:
            continue
        rows.append(row(e.name, e, opt, r))

    ok = [r for r in rows if r["meets_requirements"]]
    best = min((r["lifetime_kgco2e_per_year"] for r in ok), default=None)
    for row_ in rows:
        if not row_["meets_requirements"]:
            row_["rating"] = "does not meet requirements"
            row_["explanation"] = ("Throttles under sustained load." if row_["throttled"] and forbid_throttling
                                else f"Fails a requirement ({row_['feasibility'].replace('_', ' ')}).")  # fmt: skip
        elif best is not None and row_["lifetime_kgco2e_per_year"] <= best * (1 + LOWER_IMPACT_MARGIN):
            row_["rating"] = "lower impact"
            row_["explanation"] = (f"Meets your requirements and is within {LOWER_IMPACT_MARGIN:.0%} of the lowest "
                                f"lifetime emissions ({row_['lifetime_kgco2e_per_year']:.2f} kgCO2e/year: "
                                f"{row_['operational_kgco2e_per_year']:.2f} electricity + "
                                f"{row_['embodied_kgco2e_per_year']:.2f} embodied).")  # fmt: skip
        else:
            row_["rating"] = "meets requirements"
            row_["explanation"] = (f"Meets your requirements; {row_['lifetime_kgco2e_per_year']:.2f} kgCO2e/year, "
                                f"{(row_['lifetime_kgco2e_per_year'] / best - 1) * 100:.0f}% above the lowest.")  # fmt: skip
    rows.sort(key=lambda r: (not r["meets_requirements"], r["lifetime_kgco2e_per_year"]))
    return {
        "criteria": CRITERIA,
        "rows": rows,
        "assumptions": [
            f"{workload.hours_per_day:g} h/day at {workload.grid_gco2_per_kwh:g} gCO2e/kWh (your project settings).",
            "Thermal resistances are the typical value of each class; the range is shown. Confirm with the "
            "chosen part's datasheet and a temperature log under sustained load.",
            "Embodied carbon is a rough materials estimate (low confidence); it rarely changes the ranking "
            "unless the device runs few hours per day. The cooling already fitted adds no new embodied carbon.",
        ],
    }
