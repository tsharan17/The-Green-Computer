from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.schemas.metrics import Feasibility, Metric


class Config(BaseModel):
    """One point in the design space: software knobs plus configurable hardware knobs."""

    precision: Literal["fp32", "fp16", "int8"]
    batch: int
    power_mode_id: str
    cooling_id: str


class ConstraintCheck(BaseModel):
    name: str
    sense: Literal["<=", ">="]
    limit: float
    unit: str
    pessimistic: float
    optimistic: float
    status: Literal["pass", "fail", "uncertain"]
    note: str = ""


class EvaluationResult(BaseModel):
    config: Config
    metrics: dict[str, Metric]
    bottleneck: Literal["compute", "memory", "overhead", "heat"]
    throttle_risk: Literal["low", "medium", "high"]
    feasibility: Feasibility
    checks: list[ConstraintCheck]
    notes: list[str] = []
    engine_version: str


class Recommendation(BaseModel):
    title: str
    changes: list[str]
    summary: str
    state: Feasibility
    caveats: list[str]


class OptimisationResult(BaseModel):
    baseline: EvaluationResult
    best: EvaluationResult | None
    top: list[EvaluationResult]
    recommendation: Recommendation | None
    evaluated: int
    counts: dict[str, int]
    message: str = ""
