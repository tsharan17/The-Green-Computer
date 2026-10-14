"""Evaluate one (model, hardware, config, workload) point and certify it.

Every metric's band comes from re-solving the coupled model at an optimistic and a pessimistic
corner (see solver.corners), so uncertainty is propagated through throttling and leakage rather
than attached afterwards.
"""

from __future__ import annotations

from collections.abc import Callable

from app.engine import assumptions as A
from app.engine.accuracy import accuracy_metric
from app.engine.constraints import certify, check
from app.engine.solver import Sim, corners, simulate
from app.engine.thermal import time_to_limit, warmup_trace
from app.schemas.hardware import HardwareProfile
from app.schemas.metrics import Feasibility, Metric, Provenance
from app.schemas.model import ModelProfile
from app.schemas.project import Constraints, Workload
from app.schemas.results import Config, ConstraintCheck, EvaluationResult, SolverInfo

AN = Provenance.ANALYTICAL


def _band(sims: list[Sim], unit: str, get: Callable[[Sim], float]) -> Metric:
    """sims = [optimistic, nominal, pessimistic]; band is the min/max over the corners."""
    vals = [get(s) for s in sims]
    return Metric(value=vals[1], unit=unit, low=min(vals), high=max(vals), provenance=AN)


def evaluate(
    model: ModelProfile,
    hw: HardwareProfile,
    config: Config,
    workload: Workload,
    constraints: Constraints,
    measured_retention: float | None = None,
) -> EvaluationResult:
    cooling = hw.cooling(config.cooling_id)
    sims = [simulate(model, hw, config, workload, c) for c in corners(model)]
    nom = sims[1]

    latency = _band(sims, "ms", lambda s: s.rf.t_batch_s * 1e3)
    capacity = _band(sims, "fps", lambda s: s.pw.capacity_fps)
    p_avg = _band(sims, "W", lambda s: s.pw.p_avg_w)
    p_peak = _band(sims, "W", lambda s: s.pw.p_active_w)
    energy = _band(sims, "mJ/inference", lambda s: s.pw.energy_per_inf_mj)
    mem = _band(sims, "GB", lambda s: s.rf.mem_gb)
    temp = _band(sims, "°C", lambda s: s.temp_c)
    temp_free = _band(sims, "°C", lambda s: s.temp_unthrottled_c)
    headroom = Metric(
        value=hw.t_throttle_c - temp_free.value,
        unit="°C",
        low=hw.t_throttle_c - temp_free.high,
        high=hw.t_throttle_c - temp_free.low,
        provenance=AN,
    )
    clock = _band(sims, "× clock", lambda s: s.clock_factor)
    kwh = [s.pw.p_avg_w * workload.hours_per_day / 1000.0 for s in sims]
    cost = Metric(
        value=kwh[1] * workload.price_per_kwh,
        unit="currency/day",
        low=min(kwh) * workload.price_per_kwh,
        high=max(kwh) * workload.price_per_kwh,
        provenance=AN,
    )
    gco2 = workload.grid_gco2_per_kwh / 1000.0
    carbon = Metric(
        value=kwh[1] * gco2,
        unit="kgCO2e/day",
        low=min(kwh) * gco2,
        high=max(kwh) * gco2,
        provenance=AN,
    )
    acc, acc_measured = accuracy_metric(
        model, config.precision, constraints, measured_retention, config.resolution_scale
    )

    if temp_free.low >= hw.t_throttle_c:
        throttle_risk = "high"
    elif temp_free.high >= hw.t_throttle_c:
        throttle_risk = "medium"
    else:
        throttle_risk = "low"

    bottleneck = nom.rf.bottleneck
    if nom.throttled and throttle_risk == "high":
        bottleneck = "heat"

    acc_note = (
        "relative to baseline"
        if constraints.accuracy_mode == "relative"
        else "absolute value of the model accuracy metric"
    )
    checks: list[tuple[ConstraintCheck, Provenance]] = [
        (check("power (average)", "<=", constraints.max_power_w, p_avg), AN),
        (check("accuracy", ">=", constraints.min_accuracy, acc, note=acc_note), acc.provenance),
        (check("throughput", ">=", workload.fps, capacity, note="after any throttling"), AN),
        (
            check(
                "memory fit",
                "<=",
                nom.rf.mem_usable_gb,
                mem,
                note="usable device memory",
            ),
            AN,
        ),
        (
            check("temperature held below throttle point", "<=", hw.t_throttle_c, temp), AN,
        ),
    ]  # fmt: skip
    if constraints.max_latency_ms is not None:
        checks.append((check("latency", "<=", constraints.max_latency_ms, latency), AN))
    if constraints.max_memory_gb is not None:
        checks.append((check("memory limit", "<=", constraints.max_memory_gb, mem), AN))
    if constraints.forbid_throttling:
        checks.append((check("no sustained throttling", "<=", hw.t_throttle_c, temp_free), AN))

    state = certify(checks)
    notes: list[str] = []
    capped = config.precision in A.UNMEASURED_CAPPED_PRECISIONS or config.resolution_scale < 1.0
    if state == Feasibility.PREDICTED_FEASIBLE and not acc_measured and capped:
        state = Feasibility.UNCERTAIN
        what = (
            f"{config.precision} accuracy"
            if config.precision in A.UNMEASURED_CAPPED_PRECISIONS
            else "the reduced-resolution accuracy"
        )
        notes.append(
            f"{what} is an unmeasured prior; measure it on your validation set before relying "
            "on this configuration."
        )
    if mem.value > nom.rf.mem_usable_gb:
        notes.append("Model does not fit in usable device memory.")
    if nom.throttled and not nom.overheated:
        notes.append(
            f"The thermal governor lowers the clock to {nom.clock_factor:.0%} to hold "
            f"{hw.t_throttle_c:.0f} °C, which cuts capacity to {nom.pw.capacity_fps:.1f} fps."
        )
    if nom.overheated:
        notes.append(
            "Even at the minimum clock this cooling cannot hold the throttle temperature "
            "(or leakage runs away): the configuration is not thermally sustainable."
        )
    if model.fidelity == "manual":
        notes.append("Manual model parameters: uncertainty bands are widened.")

    t_throttle = None
    trace: list[tuple[float, float]] = []
    r_th = cooling.r_th_k_per_w
    if nom.p_avg_unthrottled_w > 0:
        if nom.throttled:
            t_throttle = time_to_limit(
                nom.p_avg_unthrottled_w, r_th, cooling.c_th_j_per_k, workload.ambient_c,
                hw.t_throttle_c,
            )  # fmt: skip
        trace = warmup_trace(
            nom.p_avg_unthrottled_w, r_th, cooling.c_th_j_per_k, workload.ambient_c,
            hw.t_throttle_c if nom.throttled else None,
        )  # fmt: skip

    metrics = {
        "latency": latency,
        "capacity_fps": capacity,
        "power_avg": p_avg,
        "power_peak": p_peak,
        "energy_per_inference": energy,
        "memory": mem,
        "temperature": temp,
        "temperature_unthrottled": temp_free,
        "thermal_headroom": headroom,
        "clock_factor": clock,
        "accuracy": acc,
        "cost_per_day": cost,
        "carbon_per_day": carbon,
    }
    return EvaluationResult(
        config=config,
        metrics=metrics,
        bottleneck=bottleneck,  # type: ignore[arg-type]
        throttle_risk=throttle_risk,  # type: ignore[arg-type]
        feasibility=state,
        checks=[c for c, _ in checks],
        notes=notes,
        solver=SolverInfo(
            converged=nom.converged,
            iterations=nom.iterations,
            throttled=nom.throttled,
            clock_factor=nom.clock_factor,
        ),
        time_to_throttle_s=t_throttle,
        thermal_trace=trace,
        engine_version=A.ENGINE_VERSION,
    )
