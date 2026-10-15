from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.metrics import Provenance


class PowerMode(BaseModel):
    id: str
    name: str
    cap_w: float
    freq_scale: float = Field(gt=0, le=1.0)
    mem_scale: float = Field(gt=0, le=1.0)


class CoolingOption(BaseModel):
    id: str
    name: str
    r_th_k_per_w: float = Field(gt=0)
    fan_w: float = 0.0
    # Lumped thermal capacitance, J/K (sets the warm-up time constant R*C).
    c_th_j_per_k: float = Field(100.0, gt=0)


class HardwareProfile(BaseModel):
    """Minimal Green Hardware Description for the L0 simulator."""

    id: str
    name: str
    vendor: str
    kind: Literal["edge_soc", "datacenter_gpu"]
    role: str = ""
    # Dense peak throughput per precision, TFLOPS/TOPS at full clocks.
    peak_tflops: dict[str, float]
    mem_bw_gbs: float
    mem_gb: float
    idle_w: float
    dyn_w_max: float
    mem_w_max: float
    leak_w_25c: float
    gamma: float = 2.5
    t_throttle_c: float
    t_shutdown_c: float
    power_modes: list[PowerMode]
    cooling_options: list[CoolingOption]
    default_cooling: str
    # Where each group of values comes from; surfaced in the UI.
    sources: dict[str, Provenance] = {}
    notes: str = ""
    verified: bool = False
    # Nebius Serverless Jobs GPU platform/preset for devices that exist there (CLI --platform / --preset).
    nebius_platform: str | None = None
    nebius_preset: str | None = None

    def mode(self, mode_id: str) -> PowerMode:
        for m in self.power_modes:
            if m.id == mode_id:
                return m
        raise ValueError(f"unknown power mode '{mode_id}' for {self.id}")

    def cooling(self, cooling_id: str) -> CoolingOption:
        for c in self.cooling_options:
            if c.id == cooling_id:
                return c
        raise ValueError(f"unknown cooling option '{cooling_id}' for {self.id}")
