"""How much of a model the engine could actually cost.

An operator with no cost model counts as zero compute, so a graph made mostly of such operators looks
impossibly cheap. Every result therefore says how many layers were modelled, and a model with gaps can
never be reported as predicted feasible. Works from the stored layers, so models uploaded before this
check existed are caught too.
"""

from __future__ import annotations

from collections import Counter

from app.schemas.model import ModelProfile

# Layers that really do cost no arithmetic, only data movement.
DATA_MOVEMENT_OPS = {
    "Transpose", "Concat", "Slice", "Split", "Gather", "Resize", "Pad", "Expand", "Tile", "Upsample",
    "ScatterND", "GatherND", "QLinearConcat",
}  # fmt: skip


def operator_matrix() -> dict[str, list[str]]:
    """Which ONNX operators the parser counts, and how. Anything else is reported as a gap."""
    from app.engine.workload.onnx_parser import COMPUTE_OPS, FUSED_ELEMENTWISE, VIEW_OPS

    return {"own_cost_model": sorted(COMPUTE_OPS), "per_element": sorted(FUSED_ELEMENTWISE),
            "data_movement": sorted(DATA_MOVEMENT_OPS), "no_cost": sorted(VIEW_OPS)}  # fmt: skip


def unmodelled_ops(model: ModelProfile) -> dict[str, int]:
    """Operator name -> how many layers of it were counted as zero compute."""
    if not model.layers:
        return {}
    return dict(Counter(x.op for x in model.layers if x.flops <= 0 and x.op not in DATA_MOVEMENT_OPS))


def coverage(model: ModelProfile) -> float:
    """Share of the model's layers with a cost model, 0..1 (1.0 for library and manual models)."""
    if not model.layers:
        return 1.0
    return 1.0 - sum(unmodelled_ops(model).values()) / len(model.layers)


def coverage_note(model: ModelProfile) -> str | None:
    ops = unmodelled_ops(model)
    if not ops:
        return None
    names = ", ".join(sorted(ops))
    return (f"Only {coverage(model):.0%} of this model's layers could be costed: {names} counted as zero "
            "compute, so real speed, power and heat will be worse than shown. Measure it on a device "
            "before relying on this result.")  # fmt: skip
