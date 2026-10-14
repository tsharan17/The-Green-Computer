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
    resolution_scale: float = 1.0,
) -> tuple[Metric, bool]:
    """Return (metric in the constraint's units, is_measured).

    A measurement covers one precision at native resolution. If the resolution is reduced, the
    resolution prior is applied on top and the result is no longer "measured".
    """
    if measured_retention is not None:
        v = lo = hi = measured_retention
        prov = Provenance.MEASURED
    else:
        v, lo, hi = A.ACCURACY_RETENTION_PRIOR[precision]
        prov = Provenance.ASSUMED

    if resolution_scale < 1.0:
        d = 1.0 - resolution_scale
        v *= 1.0 - A.RES_RETENTION_SLOPE * d
        lo *= 1.0 - A.RES_RETENTION_SLOPE_LOW * d
        prov = Provenance.ASSUMED

    measured = prov == Provenance.MEASURED
    if constraints.accuracy_mode == "relative":
        return (
            Metric(value=v, low=lo, high=hi, unit="fraction of baseline", provenance=prov),
            measured,
        )

    b = model.baseline_accuracy
    return (
        Metric(
            value=v * b, low=lo * b, high=hi * b, unit=model.accuracy_metric, provenance=prov
        ),
        measured,
    )
