# Assumptions (L0 simulator, engine 0.3.0)

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

**Latency for streams.** For a real-time stream (`workload.streaming`, default on) frames arrive one at a time, so a batch of B makes the first frame wait for B−1 more: reported latency = batch time + (B−1)/fps, and the latency limit applies to that worst frame. Throughput and power are unaffected. Turn streaming off for offline/queued workloads. If no latency limit is set, a recommendation whose worst-case latency exceeds two frame periods carries a warning.

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

## Calibration and measurements (`engine/calibration.py`)

- A measurement is a real run of (device, model, precision, batch). Fields a tool cannot supply stay empty; nothing is filled with a guess.
- For one (device, precision) two scalars are fitted: `eta_scale` (multiplies achieved compute and memory efficiency, chosen per point so predicted batch latency matches, then combined by a geometric mean shrunk toward 1 by `n/(n+1)`) and `power_scale` (only from points carrying a power measurement). There is deliberately no upper cap on the calibrated efficiency: a factor above 1 means the profile's peak or bandwidth is conservative for that device.
- **Acceptance gate:** each point is predicted from a fit to all the other points (leave-one-out). The fit is accepted only if the mean absolute relative error falls to 90% or less of the uncalibrated error, with at least 3 points. Otherwise the factors stay 1.0 and the stored report says why. Every refit is stored, accepted or not; only accepted versions are applied.
- Calibrated bands re-centre on the fitted factors and take their half-width from the largest leave-one-out error ×1.15 (3% floor, 60% ceiling). That width is derived from the same points, so coverage on new data is unproven until more measurements arrive.
- Calibration applies only to the device and precision measured. Latency-derived metrics become `calibrated` only when latency was calibrated; power-derived metrics only when power was.
- An exact match for the evaluated operating point (same device, model, precision, batch, resolution, power mode, native clocks) replaces batch time, capacity and, if measured, active power, labelled `measured`. The coupled thermal solve is not re-run on measured values, and average power at the workload's duty cycle stays predicted.
- A measured accuracy retention (vs the model's FP32 result on the same data) lets that precision be certified instead of capped at uncertain, and a measured value below the limit fails the check.
- Jobs: launching Nebius Serverless Jobs is **not implemented** (no credentials or confirmed API). The app reports this; measurements arrive by import (bench JSON, nvidia-smi CSV, tegrastats) or manual entry.

## Uncertainty

Bands (before calibration) are **corner envelopes, not statistical intervals**. The whole coupled model is re-solved at an optimistic and a pessimistic corner and each metric's band is the min/max over {optimistic, nominal, pessimistic}:

| Parameter | Corner width |
|---|---|
| Achieved efficiency (compute and memory) | ±25% |
| Every power term | ±15% |
| Thermal resistance | ±20% |

Manual-parameter models widen these by 1.5×. Whether the envelope actually covers measured values is checked against measurements on the Verify screen.

## Accuracy

- `min_accuracy` defaults to 0.90 and is interpreted as **retention relative to the model's own baseline** (`accuracy_mode: relative`). The plan's "≥ 90% mAP" cannot be met in absolute terms by any published YOLOv8 variant (mAP50-95 is 0.37–0.50), so an `absolute` mode is also supported and correctly rejects those models. Which interpretation is the product default is the owner's decision.
- Retention priors (value, low, high): fp32 1.000; fp16 0.998 (0.990–1.000); int8 0.985 (0.930–1.000).
- Resolution prior: retention × `1 − 0.30·(1 − s)` (low bound slope 0.60).
- An unmeasured int8 or reduced-resolution configuration is capped at **uncertain** even if its band clears the limit. It becomes feasible only when a measured retention is supplied (at native resolution).

## Search and ranking (`engine/optimise.py`)

- Knobs: precision (3) × batch {1,2,4,8,16} × power mode × cooling × resolution {100,75,50%} × clock trim {100,85,70%}, about 1,000–1,600 candidates per device.
- Ranking: certified feasible before uncertain, then lowest energy per inference. Energies within about 3% are treated as ties and broken by lower latency.
- Pareto set: non-dominated over energy and latency (minimised) and accuracy (maximised), among feasible and uncertain candidates only. Memory is a hard constraint, not a trade-off axis.
- Co-design comparison holds the other side at the baseline. Interaction factor `I = E_comb · E_base / (E_sw · E_hw)`; below 1 the gains reinforce, above 1 they overlap.

## Device and model library

- Model params, FLOPs and baseline accuracy are published figures. Activation traffic per library model is an estimate; ONNX uploads compute it from the graph.
- Device memory size, bandwidth and power-mode caps are vendor spec. Dense peak throughput is derived from vendor sparse TOPS (halved, GPU share assumed) and is marked assumed.
- The two reference GPUs (L40S, H100) exist to be measured on Nebius; no GPU has been measured yet and their availability there is unconfirmed.
- `host-cpu` (this development machine) is the only measured device: compute and bandwidth roofs come from `bench/probe_host.py`; power and thermal constants are assumptions and there is no power measurement.
- ResNet-50 and MobileNetV2 activation traffic comes from parsing the reference graphs in `bench/reference_models.py`, whose parameter and FLOP counts reproduce the published figures (tested).
