"""L0 thermal: steady-state lumped model, T = T_amb + P_avg * R_th.

Single pass in L0 (no throttling feedback). The coupled power-temperature-throttle
fixed point replaces this on Day 2.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.hardware import CoolingOption, HardwareProfile


@dataclass(frozen=True)
class ThermalResult:
    t_ss_c: float
    rise_c: float
    headroom_c: float


def steady_state(
    hw: HardwareProfile, cooling: CoolingOption, p_avg_w: float, ambient_c: float
) -> ThermalResult:
    rise = p_avg_w * cooling.r_th_k_per_w
    t = ambient_c + rise
    return ThermalResult(t_ss_c=t, rise_c=rise, headroom_c=hw.t_throttle_c - t)
