# The Green Computer

Predict how an AI model will behave on a given hardware setup before anything is built, then recommend the software and hardware changes that meet the requirements on the least energy. Tagline: *Predict. Optimise. Verify. Make every computation count.*

Status: **Day 4 of a 6-day build.** See [BUILD_PLAN.md](BUILD_PLAN.md) for the phased plan and [docs/assumptions.md](docs/assumptions.md) for every constant the simulator assumes.

## What works today

- **Models:** 5 library models (MobileNetV2, ResNet-50, YOLOv8 n/s/m), **ONNX upload** (per-layer FLOPs, parameters and bytes from inferred shapes; pickle and `.pt` refused) and manual parameters.
- **Hardware:** Jetson Orin Nano/NX/AGX plus L40S and H100 reference GPUs, with power modes and cooling options.
- **Coupled solver:** power sets temperature, temperature sets leakage, and a thermal governor lowers the clock past the throttle point; latency and power are re-solved. Warm-up curve and time-to-throttle from a lumped RC model.
- **Uncertainty:** every metric's band comes from re-solving the whole model at optimistic and pessimistic corners (an envelope, not a statistical interval). Every number carries a unit, band and provenance label.
- **Certification:** five-state feasibility on pessimistic bounds; hard constraints (default 55 W, 90% accuracy) are never relaxed.
- **Search:** about 1,000–1,600 configurations per device (precision, batch, resolution, power mode, clock, cooling) in under a second, a Pareto set, and a software-only / hardware-only / combined comparison with an interaction factor.
- **Measurements and calibration:** import real runs (bench JSON, nvidia-smi, tegrastats) or enter them by hand; per-(device, precision) calibration is accepted only if it predicts held-out points better (leave-one-out). Exact-match measurements show as `measured`, calibrated predictions as `calibrated`. A measured accuracy retention lets INT8 be certified.
- **Real data so far:** ResNet-50 and MobileNetV2 benchmarks on this development machine's CPU (latency only). **No GPU and no power measurement yet; Jetson results are still analytical.**
- **Green Agent (Day 4):** Nemotron on Nebius Token Factory plans, calls the engine through tools and explains. It never computes a number: a guardrail rejects any figure not found in a tool result, and it cannot change your hard constraints. Disabled (with instructions) until `TOKEN_FACTORY_API_KEY` is set. **Not yet run against the real Token Factory** (no key was available); see [docs/connecting-nebius.md](docs/connecting-nebius.md).
- **Nebius GPU benchmarks:** launches Serverless Jobs through the `nebius` CLI and imports the result. **Never run against a real account**; `scripts/check_nebius.py` verifies your connection first.
- FastAPI backend (SQLite) and a React app with Agent, Evaluation, Energy & Thermal, Optimisation Lab and Verify views.

Not yet: any GPU/Jetson measurement, live-verified Nebius/Nemotron calls, Tavily datasheet import, constraint repair, LLM prefill/decode and safetensors input. All edge numbers are **analytical predictions**, not measurements.

## Run it

One command (installs, builds the UI, starts on http://localhost:8000): `scripts/dev.ps1` on Windows, `scripts/dev.sh` elsewhere. Or step by step:

Backend (Python 3.11+):

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"   # on macOS/Linux: .venv/bin/pip
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

Frontend (Node 20+):

```bash
cd frontend
npm install
npm run build      # writes into backend/app/static, served by the API at http://localhost:8000
npm run dev        # or: dev server on :5173 proxying /api to :8000
```

Tests and checks:

```bash
cd backend && .venv/Scripts/python -m pytest && .venv/Scripts/ruff check .
cd frontend && npm run typecheck
```

Copy `.env.example` to `.env` for the Token Factory key and Nebius settings (optional). Then run `backend/.venv/Scripts/python scripts/check_nebius.py` to test them. `scripts/fake_token_factory.py` is a **fake** provider for developing without credentials.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
