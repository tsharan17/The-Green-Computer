from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Workload(BaseModel):
    fps: float = Field(30.0, gt=0)
    ambient_c: float = 40.0
    hours_per_day: float = Field(24.0, ge=0, le=24)
    price_per_kwh: float = Field(0.15, ge=0)
    grid_gco2_per_kwh: float = Field(400.0, ge=0)


class Constraints(BaseModel):
    """Hard constraints. Only the user (project form) may change these."""

    max_power_w: float = 55.0
    min_accuracy: float = Field(0.90, gt=0, le=1.0)
    # relative: fraction of the model's baseline accuracy retained
    # absolute: value of the model's own accuracy metric (e.g. mAP)
    accuracy_mode: Literal["relative", "absolute"] = "relative"
    max_latency_ms: float | None = None
    max_memory_gb: float | None = None
    forbid_throttling: bool = True


class ProjectSpec(BaseModel):
    name: str
    model_id: str
    device_id: str
    cooling_id: str | None = None
    workload: Workload = Workload()
    constraints: Constraints = Constraints()


class ProjectOut(BaseModel):
    id: int
    spec: ProjectSpec
