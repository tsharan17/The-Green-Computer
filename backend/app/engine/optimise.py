"""Day-1 optimiser: enumerate configs, evaluate, rank by certified feasibility then energy."""

from __future__ import annotations

import math
from itertools import product

from app.engine.evaluator import evaluate
from app.engine.roofline import supports
from app.schemas.hardware import HardwareProfile
from app.schemas.metrics import Feasibility
from app.schemas.model import ModelProfile
from app.schemas.project import Constraints, ProjectSpec, Workload
from app.schemas.results import Config, EvaluationResult, OptimisationResult, Recommendation

_TIE_LOG = math.log(1.03)  # energies within ~3% share a ranking bucket

PRECISIONS = ("fp32", "fp16", "int8")
BATCHES = (1, 2, 4, 8)

_STATE_RANK = {
    Feasibility.VERIFIED_FEASIBLE: 0,
    Feasibility.PREDICTED_FEASIBLE: 0,
    Feasibility.UNCERTAIN: 1,
    Feasibility.INFEASIBLE: 2,
    Feasibility.VERIFIED_INFEASIBLE: 2,
}


def baseline_config(hw: HardwareProfile, cooling_id: str | None) -> Config:
    """Reference point: fp32, batch 1, highest-power mode, the project's cooling."""
    top_mode = max(hw.power_modes, key=lambda m: m.cap_w)
    return Config(
        precision="fp32" if supports(hw, "fp32") else "fp16",
        batch=1,
        power_mode_id=top_mode.id,
        cooling_id=cooling_id or hw.default_cooling,
    )


def _failed(r: EvaluationResult) -> int:
    return sum(1 for c in r.checks if c.status == "fail")


def _changes(base: Config, cand: Config) -> list[str]:
    out = []
    if cand.precision != base.precision:
        out.append(f"precision {base.precision.upper()} → {cand.precision.upper()}")
    if cand.batch != base.batch:
        out.append(f"batch {base.batch} → {cand.batch}")
    if cand.power_mode_id != base.power_mode_id:
        out.append(f"power mode {base.power_mode_id} → {cand.power_mode_id}")
    if cand.cooling_id != base.cooling_id:
        out.append(f"cooling {base.cooling_id} → {cand.cooling_id}")
    return out


def _recommendation(
    base: EvaluationResult, best: EvaluationResult
) -> Recommendation:
    changes = _changes(base.config, best.config) or ["keep the baseline configuration"]
    bm, nm = base.metrics, best.metrics
    summary = (
        f"Average power {bm['power_avg'].value:.1f} W → {nm['power_avg'].value:.1f} W, "
        f"energy {bm['energy_per_inference'].value:.1f} → "
        f"{nm['energy_per_inference'].value:.1f} mJ/inference, "
        f"steady temperature {bm['temperature'].value:.0f} → {nm['temperature'].value:.0f} °C."
    )
    caveats = list(best.notes)
    caveats.append("All values are L0 analytical predictions with stated bands, not measurements.")
    return Recommendation(
        title="Lowest-energy configuration that meets your hard constraints",
        changes=changes,
        summary=summary,
        state=best.feasibility,
        caveats=caveats,
    )


def optimise(
    spec: ProjectSpec,
    model: ModelProfile,
    hw: HardwareProfile,
    measured: dict[str, float] | None = None,
    top_n: int = 10,
) -> OptimisationResult:
    measured = measured or {}
    wl: Workload = spec.workload
    cons: Constraints = spec.constraints
    base_cfg = baseline_config(hw, spec.cooling_id)

    def ev(cfg: Config) -> EvaluationResult:
        return evaluate(model, hw, cfg, wl, cons, measured.get(cfg.precision))

    baseline = ev(base_cfg)
    results: list[EvaluationResult] = []
    for prec, b, mode, cool in product(
        [p for p in PRECISIONS if supports(hw, p)],
        BATCHES,
        [m.id for m in hw.power_modes],
        [c.id for c in hw.cooling_options],
    ):
        results.append(ev(Config(precision=prec, batch=b, power_mode_id=mode, cooling_id=cool)))

    counts: dict[str, int] = {}
    for r in results:
        counts[r.feasibility.value] = counts.get(r.feasibility.value, 0) + 1

    ok = [r for r in results if _STATE_RANK[r.feasibility] <= 1]
    # Energy differences inside the band's noise are ties: break them by lower latency, so the
    # recommendation does not trade a 4x slower response for a sub-percent energy saving.
    ok.sort(
        key=lambda r: (
            _STATE_RANK[r.feasibility],
            math.floor(math.log(r.metrics["energy_per_inference"].value) / _TIE_LOG),
            r.metrics["latency"].value,
            r.metrics["energy_per_inference"].value,
        )
    )
    if ok:
        best = ok[0]
        return OptimisationResult(
            baseline=baseline,
            best=best,
            top=ok[:top_n],
            recommendation=_recommendation(baseline, best),
            evaluated=len(results),
            counts=counts,
        )

    closest = sorted(results, key=lambda r: (_failed(r), r.metrics["energy_per_inference"].value))
    return OptimisationResult(
        baseline=baseline,
        best=None,
        top=closest[:top_n],
        recommendation=None,
        evaluated=len(results),
        counts=counts,
        message=(
            "No configuration in the searched space satisfies every hard constraint. "
            "Constraints were not relaxed. Showing the closest candidates by number of failed checks."
        ),
    )
