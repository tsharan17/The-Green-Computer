"""A first estimate for language models: tokens per second, time to first token, memory, energy.

One token passes through every weight once, so a token costs about two FLOPs per parameter and
one full read of the weights from memory. On most boards that memory read is the limit. KV-cache
size comes from a usual layer count and width. Attention cost that grows with context, runtime
differences and caches are not modelled, and none of this has been checked against a real run.
"""

from __future__ import annotations

import math
from typing import Any

from app.engine import assumptions as A
from app.schemas.hardware import HardwareProfile
from app.schemas.metrics import Metric, Provenance

SPEED_BAND = 0.5  # wide on purpose until real runs narrow it
MEMORY_BAND = 0.2
PROMPT_BATCH = 64  # tokens processed together while reading the prompt
LAYERS_DEFAULT = 32


def estimate_llm(
    hw: HardwareProfile, params_m: float, precision: str, prompt_tokens: int, context_tokens: int,
    layers: int = LAYERS_DEFAULT,
) -> dict[str, Any]:  # fmt: skip
    if hw.peak_tflops.get(precision, 0.0) <= 0:
        raise ValueError(f"{hw.name} has no {precision} figure. It lists: {', '.join(sorted(hw.peak_tflops))}.")
    params = params_m * 1e6
    bpe = A.BYTES_PER_ELEM[precision]
    mode = max(hw.power_modes, key=lambda m: m.cap_w)
    eta_c = hw.eta_compute.get(precision, A.ETA_COMPUTE[precision])
    eta_m = hw.eta_memory if hw.eta_memory is not None else A.ETA_MEMORY
    t_c = 2.0 * params / (hw.peak_tflops[precision] * 1e12 * mode.freq_scale * eta_c)
    t_m = params * bpe / (hw.mem_bw_gbs * 1e9 * mode.mem_scale * eta_m)
    t_token = max(t_c, t_m) + A.KAPPA * min(t_c, t_m)
    power = min(mode.cap_w, hw.idle_w + hw.dyn_w_max * t_c / t_token + hw.mem_w_max * t_m / t_token)
    first = prompt_tokens * t_c + math.ceil(prompt_tokens / PROMPT_BATCH) * t_m

    # Usual transformer shape: params ~= 12 * layers * width^2, cache = 2 * layers * width per token.
    width = math.sqrt(params / (12.0 * layers))
    cache_gb = 2.0 * layers * width * context_tokens * bpe / 1e9
    weights_gb = params * bpe / 1e9
    overhead = hw.runtime_overhead_gb if hw.runtime_overhead_gb is not None else A.RUNTIME_OVERHEAD_GB
    usable = hw.mem_gb * (hw.usable_mem_fraction if hw.usable_mem_fraction is not None else A.USABLE_MEM_FRACTION)
    needed = weights_gb + cache_gb + overhead
    p = Provenance.ANALYTICAL
    return {
        "device_id": hw.id, "device": hw.name, "precision": precision, "power_mode": mode.name,
        "tokens_per_s": Metric.rel(1.0 / t_token, "tokens/s", p, SPEED_BAND).model_dump(mode="json"),
        "first_token_s": Metric.rel(first, "s", p, SPEED_BAND).model_dump(mode="json"),
        "memory_gb": Metric.rel(needed, "GB", p, MEMORY_BAND).model_dump(mode="json"),
        "weights_gb": round(weights_gb, 3), "cache_gb": round(cache_gb, 3), "usable_memory_gb": round(usable, 3),
        "power_w": Metric.rel(power, "W", p, SPEED_BAND).model_dump(mode="json"),
        "energy_per_token_j": Metric.rel(power * t_token, "J", p, SPEED_BAND).model_dump(mode="json"),
        "limit": "memory bandwidth" if t_m >= t_c else "compute",
        "fits_memory": needed <= usable,
        "validated": False,
        "notes": [
            "Predicted from physics, and not yet checked against a real language-model run on any board.",
            "Not modelled: attention cost that grows with context, runtime differences, CPU and GPU caches, and heat.",
        ],
    }  # fmt: skip
