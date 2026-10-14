"""L0 latency and memory: roofline with imperfect overlap.

t = max(t_c, t_m) + KAPPA * min(t_c, t_m) + n_layers * tau_launch
"""

from __future__ import annotations

from dataclasses import dataclass

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
    mem_gb: float
    mem_usable_gb: float


def supports(hw: HardwareProfile, precision: str) -> bool:
    return hw.peak_tflops.get(precision, 0.0) > 0.0


def roofline(
    model: ModelProfile,
    hw: HardwareProfile,
    mode: PowerMode,
    precision: str,
    batch: int,
) -> RooflineResult:
    if batch < 1:
        raise ValueError("batch must be >= 1")
    if not supports(hw, precision):
        raise ValueError(f"{hw.id} has no {precision} support")

    bpe = A.BYTES_PER_ELEM[precision]
    flops = batch * model.gflops * 1e9
    weight_bytes = model.params_m * 1e6 * bpe
    act_bytes = batch * model.act_mb_fp32 * 1e6 * (bpe / 4.0)
    total_bytes = weight_bytes + act_bytes

    peak = hw.peak_tflops[precision] * 1e12 * mode.freq_scale
    bw = hw.mem_bw_gbs * 1e9 * mode.mem_scale

    t_c = flops / (peak * A.ETA_COMPUTE[precision])
    t_m = total_bytes / (bw * A.ETA_MEMORY)
    t_o = model.n_layers * A.LAUNCH_OVERHEAD_S
    t = max(t_c, t_m) + A.KAPPA * min(t_c, t_m) + t_o

    if t_o > max(t_c, t_m):
        bottleneck = "overhead"
    elif t_c >= t_m:
        bottleneck = "compute"
    else:
        bottleneck = "memory"

    mem_gb = (
        weight_bytes + A.LIVE_ACT_FRACTION * act_bytes
    ) / 1e9 + A.RUNTIME_OVERHEAD_GB

    return RooflineResult(
        t_batch_s=t,
        t_compute_s=t_c,
        t_memory_s=t_m,
        t_overhead_s=t_o,
        util_compute=min(1.0, t_c / t),
        util_memory=min(1.0, t_m / t),
        bottleneck=bottleneck,
        mem_gb=mem_gb,
        mem_usable_gb=hw.mem_gb * A.USABLE_MEM_FRACTION,
    )
