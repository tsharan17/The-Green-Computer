"""Default constants for the L0 simulator.

Every value here is an ASSUMPTION until calibrated against measurements (Day 3).
They are documented in docs/assumptions.md and surfaced with provenance "assumed".
"""

ENGINE_VERSION = "0.1.0-l0"

BYTES_PER_ELEM = {"fp32": 4.0, "fp16": 2.0, "int8": 1.0}

# Fraction of peak compute actually achieved, per precision.
ETA_COMPUTE = {"fp32": 0.45, "fp16": 0.35, "int8": 0.25}
# Fraction of peak memory bandwidth achieved.
ETA_MEMORY = 0.70
# Imperfect overlap of compute and memory: t = max + KAPPA*min + launch overhead.
KAPPA = 0.15
LAUNCH_OVERHEAD_S = 10e-6  # per layer

# Live activation fraction of total activation traffic and fixed runtime footprint.
LIVE_ACT_FRACTION = 0.30
RUNTIME_OVERHEAD_GB = 0.35
USABLE_MEM_FRACTION = 0.85

# Relative uncertainty (half-width of the band) for analytical predictions.
REL_UNCERTAINTY = {
    "latency": 0.30,
    "throughput": 0.30,
    "power": 0.20,
    "energy": 0.35,
    "temp_rise": 0.25,
    "memory": 0.15,
}

# Accuracy retained vs the fp32 baseline: (value, low, high). Priors, not measurements.
ACCURACY_RETENTION_PRIOR = {
    "fp32": (1.000, 1.000, 1.000),
    "fp16": (0.998, 0.990, 1.000),
    "int8": (0.985, 0.930, 1.000),
}
# Precisions whose accuracy effect must be measured before they can be called feasible.
UNMEASURED_CAPPED_PRECISIONS = {"int8"}
