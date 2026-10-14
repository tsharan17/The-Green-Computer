# Assumptions (L0 simulator, engine 0.2.0)

Every constant below is an assumption until calibrated against measurements (Day 3). The UI labels these values "assumed" or "analytical"; none is shown as measured. Constants live in `backend/app/engine/assumptions.py`.

## Latency and memory (`engine/roofline.py`)

Per layer: `t_i = max(t_c,i, t_m,i) + KAPPA * min(t_c,i, t_m,i)`; total `t = sum(t_i) + n_layers * tau`. Models without a parsed graph are one aggregate layer.

| Constant | Value | Meaning |
|---|---|---|
| `ETA_COMPUTE` | fp32 0.45, fp16 0.35, int8 0.25 | Fraction of peak throughput achieved |
| `ETA_MEMORY` | 0.70 | Fraction of peak bandwidth achieved |
| `KAPPA` | 0.15 | Imperfect compute/memory overlap |
| `LAUNCH_OVERHEAD_S` | 10 µs per layer | Kernel launch overhead |
| `LIVE_ACT_FRACTION` | 0.30 | Share of activation traffic resident at once |
| `RUNTIME_OVERHEAD_GB` | 0.35 | Fixed runtime footprint |
| `USABLE_MEM_FRACTION` | 0.85 | Device memory available to the model |

Input resolution scales FLOPs and activation traffic by `scale²` (vision models only).

## ONNX parsing (`engine/workload/onnx_parser.py`)

- Graphs are analysed at batch 1. Dynamic dimensions require an explicit default (the batch axis defaults to 1).
- Conv / ConvTranspose / Gemm / MatMul MACs come from inferred tensor shapes; pooling, softmax and normalisation use rough per-element FLOP factors; data-movement ops have zero FLOPs.
- **Elementwise ops (activations, Add/Mul, BatchNorm) are assumed fused** into their producer: their FLOPs are added to the previous layer, with no extra activation traffic or kernel launch. View ops (Reshape, Flatten, ...) cost nothing.
- Every other op reads its activation inputs and writes its outputs once (no cross-layer fusion), which can overstate memory traffic for fused runtimes such as TensorRT.
- Only the ONNX protobuf format is accepted. Pickle/torch archives, files with external data and files over 100 MB are refused. LLM prefill/decode and safetensors/Hugging Face config input are not implemented yet.
- Custom models have no published accuracy; accuracy is relative-only unless the user supplies a baseline.

## Power and thermal (`engine/power.py`, `thermal.py`, `solver.py`)

- Power constants (`idle_w`, `dyn_w_max`, `mem_w_max`, `leak_w_25c`, `gamma = 2.5`) are tuned per device so full-load power at 25 °C is within 10% of the nominal power-mode cap (enforced by a test). They are not datasheet values.
- Leakage grows with temperature: `P_leak(T) = P_leak(25 °C) · exp(0.015 · (T − 25))`.
- **Coupled solve:** for each clock multiplier θ the temperature is the damped fixed point of `T = T_amb + P_avg(T) · R_th`. If the unconstrained state exceeds the throttle point, or leakage runs away, the governor bisects θ in [0.1, 1] for the highest clock that holds the throttle temperature. If even θ = 0.1 cannot, the configuration is flagged not thermally sustainable.
- Throttle at 90 °C on Jetson, 85 °C on the reference GPUs. Thermal resistances and capacitances per cooling option are assumptions.
- The warm-up curve uses the lumped RC model at the unthrottled steady power; leakage feedback during the transient is ignored.
- Unthrottled temperatures are displayed clamped at 200 °C.

## Uncertainty

Bands are **corner envelopes, not statistical intervals**. The whole coupled model is re-solved at an optimistic and a pessimistic corner and each metric's band is the min/max over {optimistic, nominal, pessimistic}:

| Parameter | Corner width |
|---|---|
| Achieved efficiency (compute and memory) | ±25% |
| Every power term | ±15% |
| Thermal resistance | ±20% |

Manual-parameter models widen these by 1.5×. Whether the envelope actually covers measured values is validated on Day 3; until then it is a stated prior.

## Accuracy

- `min_accuracy` defaults to 0.90 and is interpreted as **retention relative to the model's own baseline** (`accuracy_mode: relative`). The plan's "≥ 90% mAP" cannot be met in absolute terms by any published YOLOv8 variant (mAP50-95 is 0.37–0.50), so an `absolute` mode is also supported and correctly rejects those models. Which interpretation is the product default is the owner's decision.
- Retention priors (value, low, high): fp32 1.000; fp16 0.998 (0.990–1.000); int8 0.985 (0.930–1.000).
- Resolution prior: retention × `1 − 0.30·(1 − s)` (low bound slope 0.60).
- An unmeasured int8 or reduced-resolution configuration is capped at **uncertain** even if its band clears the limit. It becomes feasible only when a measured retention is supplied (at native resolution).

## Search and ranking (`engine/optimise.py`)

- Knobs: precision (3) × batch {1,2,4,8,16} × power mode × cooling × resolution {100,75,50%} × clock trim {100,85,70%}, about 1,000–1,600 candidates per device.
- Ranking: certified feasible before uncertain, then lowest energy per inference. Energies within about 3% are treated as ties and broken by lower latency.
- Pareto set: non-dominated over energy, latency, memory (minimised) and accuracy (maximised), among feasible and uncertain candidates only.
- Co-design comparison holds the other side at the baseline. Interaction factor `I = E_comb · E_base / (E_sw · E_hw)`; below 1 the gains reinforce, above 1 they overlap.

## Device and model library

- Model params, FLOPs and baseline accuracy are published figures. Activation traffic per library model is an estimate; ONNX uploads compute it from the graph.
- Device memory size, bandwidth and power-mode caps are vendor spec. Dense peak throughput is derived from vendor sparse TOPS (halved, GPU share assumed) and is marked assumed.
- The two reference GPUs (L40S, H100) exist to be measured on Nebius on Day 3; their availability there is unconfirmed.
