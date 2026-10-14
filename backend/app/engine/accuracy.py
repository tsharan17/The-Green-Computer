"""Accuracy priors. These are stated assumptions, never measurements."""

from __future__ import annotations

from app.engine import assumptions as A
from app.schemas.metrics import Metric, Provenance
from app.schemas.model import ModelProfile
from app.schemas.project import Constraints


def accuracy_metric(
    model: ModelProfile,
    precision: str,
    constraints: Constraints,
    measured_retention: float | None = None,
) -> tuple[Metric, bool]:
    """Return (metric in the constraint's units, is_measured)."""
    if measured_retention is not None:
        ret = Metric.exact(measured_retention, "fraction of baseline", Provenance.MEASURED)
        measured = True
    else:
        v, lo, hi = A.ACCURACY_RETENTION_PRIOR[precision]
        ret = Metric(
            value=v, low=lo, high=hi, unit="fraction of baseline", provenance=Provenance.ASSUMED
        )
        measured = False

    if constraints.accuracy_mode == "relative":
        return ret, measured

    b = model.baseline_accuracy
    return (
        Metric(
            value=ret.value * b,
            low=ret.low * b,
            high=ret.high * b,
            unit=model.accuracy_metric,
            provenance=ret.provenance,
        ),
        measured,
    )
