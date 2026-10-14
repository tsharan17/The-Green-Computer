# Assumptions (Day 1, L0 simulator)

Every constant below is an assumption until calibrated against measurements (Day 3). The UI labels these values "assumed" or "analytical"; none is shown as measured.

## Latency and memory (`engine/roofline.py`, constants in `engine/assumptions.py`)

| Constant | Value | Meaning |
|---|---|---|
| `ETA_COMPUTE` | fp32 0.45, fp16 0.35, int8 0.25 | Fraction of peak throughput achieved |
| `ETA_MEMORY` | 0.70 | Fraction of peak bandwidth achieved |
| `KAPPA` | 0.15 | Imperfect compute/memory overlap |
| `LAUNCH_OVERHEAD_S` | 10 µs per layer | Kernel launch overhead |
| `LIVE_ACT_FRACTION` | 0.30 | Share of activation traffic resident at once |
| `RUNTIME_OVERHEAD_GB` | 0.35 | Fixed runtime footprint |
| `USABLE_MEM_FRACTION` | 0.85 | Device memory available to the model |

## Power and thermal

- Power model constants (`idle_w`, `dyn_w_max`, `mem_w_max`, `leak_w_25c`, `gamma = 2.5`) are tuned per device so modelled full-load power is within 10% of the nominal power-mode cap (enforced by a test). They are not datasheet values.
- Leakage is held at its 25 °C value; temperature feedback and throttling arrive with the coupled solver (Day 2).
- Thermal resistances per cooling option are assumptions. Throttle at 90 °C, shutdown 105 °C on Jetson; 85/95 °C on the reference GPUs.
- Temperature is a lumped steady state, `T = T_amb + P_avg · R_th`.

## Uncertainty

Relative half-widths of the 95% band: latency 30%, throughput 30%, power 20%, energy 35%, temperature rise 25%, memory 15%. These are priors, not fitted values.

## Accuracy

- The `min_accuracy` constraint defaults to 0.90 and is interpreted as **retention relative to the model's own baseline** (`accuracy_mode: relative`). The plan's "≥ 90% mAP" cannot be met in absolute terms by any published YOLOv8 variant (mAP50-95 is 0.37–0.50), so an `absolute` mode is also supported and will correctly reject those models. Which interpretation is the product default is the owner's decision.
- Retention priors (value, low, high): fp32 1.000; fp16 0.998 (0.990–1.000); int8 0.985 (0.930–1.000).
- An unmeasured int8 configuration is capped at **uncertain** even if its band clears the limit. It becomes feasible only when a measured retention is supplied.

## Device and model library

- Model params, FLOPs and baseline accuracy are published figures. Activation traffic per sample is an estimate until the ONNX parser computes it (Day 2).
- Device memory size, bandwidth and power-mode caps are vendor spec. Dense peak throughput is derived from vendor sparse TOPS (halved, GPU share assumed) and is marked assumed.
- The two reference GPUs (L40S, H100) are included to be measured on Nebius on Day 3; their availability there is unconfirmed.
