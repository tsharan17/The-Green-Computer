"""Evaluate one (model, hardware, config, workload) point and certify it."""

from __future__ import annotations

from app.engine import assumptions as A
from app.engine.accuracy import accuracy_metric
from app.engine.constraints import certify, check
from app.engine.power import power
from app.engine.roofline import roofline
from app.engine.thermal import steady_state
from app.schemas.hardware import HardwareProfile
from app.schemas.metrics import Feasibility, Metric, Provenance
from app.schemas.model import ModelProfile
from app.schemas.project import Constraints, Workload
from app.schemas.results import Config, ConstraintCheck, EvaluationResult

AN = Provenance.ANALYTICAL


def evaluate(
    model: ModelProfile,
    hw: HardwareProfile,
    config: Config,
    workload: Workload,
    constraints: Constraints,
    measured_retention: float | None = None,
) -> EvaluationResult:
    mode = hw.mode(config.power_mode_id)
    cooling = hw.cooling(config.cooling_id)
    rf = roofline(model, hw, mode, config.precision, config.batch)
    pw = power(
        hw, mode, cooling, rf.t_batch_s, config.batch, rf.util_compute, rf.util_memory,
        workload.fps,
    )
    th = steady_state(hw, cooling, pw.p_avg_w, workload.ambient_c)
    R = A.REL_UNCERTAINTY

    latency = Metric.rel(rf.t_batch_s * 1e3, "ms", AN, R["latency"])
    capacity = Metric.rel(pw.capacity_fps, "fps", AN, R["throughput"])
    p_avg = Metric.rel(pw.p_avg_w, "W", AN, R["power"])
    p_peak = Metric.rel(pw.p_active_w, "W", AN, R["power"])
    energy = Metric.rel(pw.energy_per_inf_mj, "mJ/inference", AN, R["energy"])
    mem = Metric.rel(rf.mem_gb, "GB", AN, R["memory"])
    # Temperature uncertainty applies to the rise above ambient, not to ambient itself.
    temp = Metric(
        value=th.t_ss_c,
        unit="°C",
        low=workload.ambient_c + th.rise_c * (1 - R["temp_rise"]),
        high=workload.ambient_c + th.rise_c * (1 + R["temp_rise"]),
        provenance=AN,
    )
    headroom = Metric(
        value=th.headroom_c,
        unit="°C",
        low=hw.t_throttle_c - temp.high,
        high=hw.t_throttle_c - temp.low,
        provenance=AN,
    )
    acc, acc_measured = accuracy_metric(model, config.precision, constraints, measured_retention)

    kwh_day = pw.p_avg_w * workload.hours_per_day / 1000.0
    cost = Metric.rel(kwh_day * workload.price_per_kwh, "currency/day", AN, R["power"])
    carbon = Metric.rel(kwh_day * workload.grid_gco2_per_kwh / 1000.0, "kgCO2e/day", AN, R["power"])

    # Throttle risk from the temperature band.
    if temp.low >= hw.t_throttle_c:
        throttle_risk = "high"
    elif temp.high >= hw.t_throttle_c:
        throttle_risk = "medium"
    else:
        throttle_risk = "low"

    bottleneck = rf.bottleneck
    if throttle_risk == "high":
        bottleneck = "heat"

    checks: list[tuple[ConstraintCheck, Provenance]] = [
        (check("power (average)", "<=", constraints.max_power_w, p_avg), p_avg.provenance),
        (
            check(
                "accuracy",
                ">=",
                constraints.min_accuracy,
                acc,
                note=(
                    "relative to baseline"
                    if constraints.accuracy_mode == "relative"
                    else "absolute value of the model accuracy metric"
                ),
            ),
            acc.provenance,
        ),
        (check("throughput", ">=", workload.fps, capacity), capacity.provenance),
        (
            check("memory fit", "<=", rf.mem_usable_gb, mem, note="usable device memory"),
            mem.provenance,
        ),
    ]
    if constraints.max_latency_ms is not None:
        checks.append(
            (check("latency", "<=", constraints.max_latency_ms, latency), latency.provenance)
        )
    if constraints.max_memory_gb is not None:
        checks.append((check("memory limit", "<=", constraints.max_memory_gb, mem), mem.provenance))
    if constraints.forbid_throttling:
        checks.append(
            (
                check("no sustained throttling", "<=", hw.t_throttle_c, temp),
                temp.provenance,
            )
        )

    state = certify(checks)
    notes: list[str] = []
    if (
        state == Feasibility.PREDICTED_FEASIBLE
        and not acc_measured
        and config.precision in A.UNMEASURED_CAPPED_PRECISIONS
    ):
        state = Feasibility.UNCERTAIN
        notes.append(
            f"{config.precision} accuracy is an unmeasured prior; measure it on your validation "
            "set before relying on this configuration."
        )
    if rf.mem_gb > rf.mem_usable_gb:
        notes.append("Model does not fit in usable device memory.")

    metrics = {
        "latency": latency,
        "capacity_fps": capacity,
        "power_avg": p_avg,
        "power_peak": p_peak,
        "energy_per_inference": energy,
        "memory": mem,
        "temperature": temp,
        "thermal_headroom": headroom,
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
        engine_version=A.ENGINE_VERSION,
    )

