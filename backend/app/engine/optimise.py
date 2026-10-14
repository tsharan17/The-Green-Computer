"""Design-space search: sweep, rank, Pareto frontier and software/hardware co-design comparison.

Knobs and their tiers:
  software            precision, batch, input resolution
  hardware configure  power mode, clock trim
  hardware select     cooling solution
Everything is evaluated through the coupled solver, so thermal throttling is inside the search,
not a post-check.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable
from itertools import product

import numpy as np

from app.engine.evaluator import evaluate, matches
from app.engine.roofline import supports
from app.schemas.hardware import HardwareProfile
from app.schemas.measurement import Calibration, MeasurementIn
from app.schemas.metrics import Feasibility
from app.schemas.model import ModelProfile
from app.schemas.project import Constraints, ProjectSpec, Workload
from app.schemas.results import (
    CoDesign,
    Config,
    EvaluationResult,
    OptimisationResult,
    Point,
    Recommendation,
)

_TIE_LOG = math.log(1.03)  # energies within ~3% share a ranking bucket

PRECISIONS = ("fp32", "fp16", "int8")
BATCHES = (1, 2, 4, 8, 16)
RESOLUTIONS = (1.0, 0.75, 0.5)
CLOCK_TRIMS = (1.0, 0.85, 0.7)

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


def search_space(model: ModelProfile, hw: HardwareProfile) -> Iterable[Config]:
    for prec, b, mode, cool, res, trim in product(
        [p for p in PRECISIONS if supports(hw, p)],
        BATCHES,
        [m.id for m in hw.power_modes],
        [c.id for c in hw.cooling_options],
        RESOLUTIONS if model.resolution_scalable else (1.0,),
        CLOCK_TRIMS,
    ):
        yield Config(
            precision=prec, batch=b, power_mode_id=mode, cooling_id=cool,
            resolution_scale=res, clock_trim=trim,
        )  # fmt: skip


def _failed(r: EvaluationResult) -> int:
    return sum(1 for c in r.checks if c.status == "fail")


def _eligible(r: EvaluationResult) -> bool:
    return _STATE_RANK[r.feasibility] <= 1


def _rank_key(r: EvaluationResult) -> tuple:
    # Energy differences inside the band's noise are ties: break them by lower latency, so the
    # recommendation does not trade a 4x slower response for a sub-percent energy saving.
    e = r.metrics["energy_per_inference"].value
    return (
        _STATE_RANK[r.feasibility],
        math.floor(math.log(e) / _TIE_LOG),
        r.metrics["latency"].value,
        e,
    )


def _pick(results: Iterable[EvaluationResult]) -> EvaluationResult | None:
    ok = [r for r in results if _eligible(r)]
    return min(ok, key=_rank_key) if ok else None


def _fmt_changes(base: Config, cand: Config) -> list[str]:
    out = []
    if cand.precision != base.precision:
        out.append(f"Software: precision {base.precision.upper()} → {cand.precision.upper()}")
    if cand.batch != base.batch:
        out.append(f"Software: batch {base.batch} → {cand.batch}")
    if cand.resolution_scale != base.resolution_scale:
        out.append(
            f"Software: input resolution {base.resolution_scale:.0%} → {cand.resolution_scale:.0%}"
        )
    if cand.power_mode_id != base.power_mode_id:
        out.append(f"Hardware (configure): power mode {base.power_mode_id} → {cand.power_mode_id}")
    if cand.clock_trim != base.clock_trim:
        out.append(f"Hardware (configure): clock {base.clock_trim:.0%} → {cand.clock_trim:.0%}")
    if cand.cooling_id != base.cooling_id:
        out.append(f"Hardware (select): cooling {base.cooling_id} → {cand.cooling_id}")
    return out


def _recommendation(
    base: EvaluationResult, best: EvaluationResult, spec: ProjectSpec
) -> Recommendation:
    changes = _fmt_changes(base.config, best.config) or ["Keep the baseline configuration"]
    bm, nm = base.metrics, best.metrics
    summary = (
        f"Average power {bm['power_avg'].value:.1f} W → {nm['power_avg'].value:.1f} W, "
        f"energy {bm['energy_per_inference'].value:.1f} → "
        f"{nm['energy_per_inference'].value:.1f} mJ/inference, "
        f"steady temperature {bm['temperature'].value:.0f} → {nm['temperature'].value:.0f} °C, "
        f"capacity {bm['capacity_fps'].value:.0f} → {nm['capacity_fps'].value:.0f} fps."
    )
    caveats = list(best.notes)
    lat = nm["latency"].value
    frame_ms = 1e3 / spec.workload.fps
    if spec.constraints.max_latency_ms is None and lat > 2 * frame_ms:
        caveats.append(
            f"No latency limit is set, and this configuration has a worst-case frame latency of "
            f"{lat:.0f} ms ({lat / frame_ms:.1f} frame periods). Set a latency limit if the "
            "application is real-time."
        )
    caveats.append("All values are analytical predictions with stated bands, not measurements.")
    return Recommendation(
        title="Lowest-energy configuration that meets your hard constraints",
        changes=changes,
        summary=summary,
        state=best.feasibility,
        caveats=caveats,
    )


def pareto_mask(objectives: np.ndarray) -> np.ndarray:
    """Boolean mask of non-dominated rows; every column is minimised."""
    n = objectives.shape[0]
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        if not keep[i]:
            continue
        le = np.all(objectives <= objectives[i], axis=1)
        lt = np.any(objectives < objectives[i], axis=1)
        dominators = le & lt
        if dominators.any():
            keep[i] = False
    return keep


def _codesign(
    base: EvaluationResult,
    results: list[EvaluationResult],
    base_cfg: Config,
) -> CoDesign:
    def hw_same(c: Config) -> bool:
        return (
            c.power_mode_id == base_cfg.power_mode_id
            and c.cooling_id == base_cfg.cooling_id
            and c.clock_trim == base_cfg.clock_trim
        )

    def sw_same(c: Config) -> bool:
        return (
            c.precision == base_cfg.precision
            and c.batch == base_cfg.batch
            and c.resolution_scale == base_cfg.resolution_scale
        )

    sw = _pick(r for r in results if hw_same(r.config))
    hw = _pick(r for r in results if sw_same(r.config))
    comb = _pick(results)

    def energy(r: EvaluationResult) -> float:
        return r.metrics["energy_per_inference"].value

    factor = None
    interp = (
        "A combined interaction factor needs a feasible software-only, hardware-only and "
        "combined configuration; at least one of them does not exist for this baseline."
    )
    if sw and hw and comb:
        factor = energy(comb) * energy(base) / (energy(sw) * energy(hw))
        if factor < 0.95:
            interp = (
                f"Interaction factor {factor:.2f} (< 1): software and hardware changes "
                "reinforce each other; the combined saving beats the product of the two alone."
            )
        elif factor <= 1.05:
            interp = (
                f"Interaction factor {factor:.2f} (≈ 1): the gains are roughly independent "
                "and multiply."
            )
        else:
            interp = (
                f"Interaction factor {factor:.2f} (> 1): the gains overlap; combining them "
                "saves less than the product of the individual savings."
            )
    return CoDesign(
        baseline=base,
        software_only=sw,
        hardware_only=hw,
        combined=comb,
        interaction_factor=factor,
        interpretation=interp,
    )


def optimise(
    spec: ProjectSpec,
    model: ModelProfile,
    hw: HardwareProfile,
    measured: dict[str, float] | None = None,
    top_n: int = 10,
    calibrations: dict[str, Calibration] | None = None,
    measurements: list[MeasurementIn] | None = None,
    configs: Iterable[Config] | None = None,
    on_result: Callable[[EvaluationResult], None] | None = None,
) -> OptimisationResult:
    t0 = time.perf_counter()
    measured = measured or {}
    wl: Workload = spec.workload
    cons: Constraints = spec.constraints
    base_cfg = spec.baseline or baseline_config(hw, spec.cooling_id)

    calibrations = calibrations or {}
    measurements = measurements or []

    def ev(cfg: Config) -> EvaluationResult:
        exact = next((m for m in measurements if matches(m, hw, model.id, cfg)), None)
        return evaluate(
            model, hw, cfg, wl, cons, measured.get(cfg.precision),
            calibration=calibrations.get(cfg.precision), measured=exact,
        )  # fmt: skip

    baseline = ev(base_cfg)
    results = [ev(c) for c in (configs if configs is not None else search_space(model, hw))]
    if on_result:
        for r in results:
            on_result(r)

    counts: dict[str, int] = {}
    for r in results:
        counts[r.feasibility.value] = counts.get(r.feasibility.value, 0) + 1

    eligible = sorted((r for r in results if _eligible(r)), key=_rank_key)
    best = eligible[0] if eligible else None

    # Pareto set over eligible candidates: energy and latency down, accuracy up. Memory is a
    # hard constraint, not a trade-off axis, so it is not an objective here.
    pareto_ids: set[int] = set()
    if eligible:
        obj = np.array(
            [
                [
                    r.metrics["energy_per_inference"].value,
                    r.metrics["latency"].value,
                    -r.metrics["accuracy"].value,
                ]
                for r in eligible
            ]
        )
        mask = pareto_mask(obj)
        pareto_ids = {id(eligible[i]) for i in np.flatnonzero(mask)}

    points = [
        Point(
            config=r.config,
            state=r.feasibility,
            energy_mj=r.metrics["energy_per_inference"].value,
            latency_ms=r.metrics["latency"].value,
            accuracy=r.metrics["accuracy"].value,
            power_w=r.metrics["power_avg"].value,
            memory_gb=r.metrics["memory"].value,
            temperature_c=r.metrics["temperature"].value,
            pareto=id(r) in pareto_ids,
            best=r is best,
        )
        for r in results
    ]

    codesign = _codesign(baseline, results, base_cfg)
    elapsed = time.perf_counter() - t0

    if best is not None:
        return OptimisationResult(
            baseline=baseline,
            best=best,
            top=eligible[:top_n],
            recommendation=_recommendation(baseline, best, spec),
            codesign=codesign,
            points=points,
            evaluated=len(results),
            counts=counts,
            search_seconds=elapsed,
        )

    closest = sorted(results, key=lambda r: (_failed(r), r.metrics["energy_per_inference"].value))
    return OptimisationResult(
        baseline=baseline,
        best=None,
        top=closest[:top_n],
        recommendation=None,
        codesign=codesign,
        points=points,
        evaluated=len(results),
        counts=counts,
        search_seconds=elapsed,
        message=(
            "No configuration in the searched space satisfies every hard constraint. "
            "Constraints were not relaxed. Showing the closest candidates by number of "
            "failed checks."
        ),
    )
