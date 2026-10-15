"""L0 latency and memory: per-layer roofline with imperfect overlap.

Per layer i:  t_i = max(t_c,i, t_m,i) + KAPPA * min(t_c,i, t_m,i)
Total:        t   = sum_i t_i + n_layers * tau_launch

Models without a parsed graph are treated as one aggregate layer.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.engine import assumptions as A
from app.schemas.hardware import HardwareProfile, PowerMode
from app.schemas.model import ModelProfile


@dataclass(frozen=True)
class RooflineResult:
    t_batch_s: float
    t_compute_s: float
    t_memory_s: float
    t_overhead_s: float
    util_compute: float
    util_memory: float
    bottleneck: str
    compute_bound_fraction: float
    mem_gb: float
    mem_usable_gb: float


_ARRAYS: dict[tuple, tuple[np.ndarray, np.ndarray, np.ndarray, int]] = {}


def _arrays(model: ModelProfile) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """(flops, weight elements, activation elements, n_layers) per sample, cached per model."""
    key = (model.id, model.params_m, model.gflops, model.n_layers, len(model.layers or ()))
    hit = _ARRAYS.get(key)
    if hit is not None:
        return hit
    if model.layers:
        flops = np.array([layer.flops for layer in model.layers], dtype=float)
        params = np.array([layer.params for layer in model.layers], dtype=float)
        acts = np.array([layer.act_elems for layer in model.layers], dtype=float)
        n = model.n_layers
    else:
        flops = np.array([model.gflops * 1e9])
        params = np.array([model.params_m * 1e6])
        acts = np.array([model.act_mb_fp32 * 1e6 / 4.0])
        n = model.n_layers
    _ARRAYS[key] = (flops, params, acts, n)
    return _ARRAYS[key]


def supports(hw: HardwareProfile, precision: str) -> bool:
    return hw.peak_tflops.get(precision, 0.0) > 0.0


def roofline_at(
    model: ModelProfile,
    hw: HardwareProfile,
    freq_scale: float,
    mem_scale: float,
    precision: str,
    batch: int,
    resolution_scale: float = 1.0,
    eta_scale: float = 1.0,
    sparsity: float = 0.0,
) -> RooflineResult:
    if batch < 1:
        raise ValueError("batch must be >= 1")
    if not supports(hw, precision):
        raise ValueError(f"{hw.id} has no {precision} support")
    if resolution_scale != 1.0 and not model.resolution_scalable:
        raise ValueError(f"{model.id} does not support input-resolution scaling")

    flops, params, acts, n_layers = _arrays(model)
    if sparsity > 0.0:
        # Structured pruning removes channels: compute and weights shrink with the kept
        # fraction; activations shrink about half as fast (inputs and some paths are unpruned).
        flops = flops * (1.0 - sparsity)
        params = params * (1.0 - sparsity)
        acts = acts * (1.0 - 0.5 * sparsity)
    bpe = A.BYTES_PER_ELEM[precision]
    s2 = resolution_scale**2

    # No upper cap: a calibrated scale above 1 legitimately says the profile's peak numbers are
    # conservative for this device (e.g. caches lift effective bandwidth above the DRAM roof).
    eta_c = A.ETA_COMPUTE[precision] * eta_scale
    eta_m = A.ETA_MEMORY * eta_scale
    peak = hw.peak_tflops[precision] * 1e12 * freq_scale
    bw = hw.mem_bw_gbs * 1e9 * mem_scale

    t_c = batch * s2 * flops / (peak * eta_c)
    bytes_ = params * bpe + batch * s2 * acts * bpe
    t_m = bytes_ / (bw * eta_m)
    hi = np.maximum(t_c, t_m)
    lo = np.minimum(t_c, t_m)
    t_layers = hi + A.KAPPA * lo
    t_o = n_layers * A.LAUNCH_OVERHEAD_S
    t = float(t_layers.sum()) + t_o

    sum_c, sum_m = float(t_c.sum()), float(t_m.sum())
    cb_time = float(t_layers[t_c >= t_m].sum())
    cb_frac = cb_time / max(float(t_layers.sum()), 1e-30)
    if t_o > float(t_layers.sum()):
        bottleneck = "overhead"
    elif cb_frac >= 0.5:
        bottleneck = "compute"
    else:
        bottleneck = "memory"

    weight_bytes = float(params.sum()) * bpe
    act_bytes = batch * s2 * float(acts.sum()) * bpe
    mem_gb = (weight_bytes + A.LIVE_ACT_FRACTION * act_bytes) / 1e9 + A.RUNTIME_OVERHEAD_GB

    return RooflineResult(
        t_batch_s=t,
        t_compute_s=sum_c,
        t_memory_s=sum_m,
        t_overhead_s=t_o,
        util_compute=min(1.0, sum_c / t),
        util_memory=min(1.0, sum_m / t),
        bottleneck=bottleneck,
        compute_bound_fraction=cb_frac,
        mem_gb=mem_gb,
        mem_usable_gb=hw.mem_gb * A.USABLE_MEM_FRACTION,
    )


def roofline(
    model: ModelProfile,
    hw: HardwareProfile,
    mode: PowerMode,
    precision: str,
    batch: int,
) -> RooflineResult:
    """Convenience wrapper: roofline at a power mode's nominal clocks."""
    return roofline_at(model, hw, mode.freq_scale, mode.mem_scale, precision, batch)
