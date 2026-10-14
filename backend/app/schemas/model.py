from __future__ import annotations

from pydantic import BaseModel

from app.schemas.metrics import Provenance


class ModelProfile(BaseModel):
    """Library entry for an AI model (Day 1: summary numbers; Day 2: per-layer graph)."""

    id: str
    name: str
    task: str
    input_desc: str
    params_m: float
    gflops: float  # per sample, FLOPs (2 x MACs)
    n_layers: int
    act_mb_fp32: float  # activation traffic per sample at fp32
    baseline_accuracy: float  # fraction 0..1
    accuracy_metric: str
    sources: dict[str, Provenance] = {}
    notes: str = ""
