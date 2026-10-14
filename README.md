# The Green Computer

Predict how an AI model will behave on a given hardware setup before anything is built, then recommend the software and hardware changes that meet the requirements on the least energy. Tagline: *Predict. Optimise. Verify. Make every computation count.*

Status: **Day 1 of a 6-day build** (thin end-to-end slice). See [BUILD_PLAN.md](BUILD_PLAN.md) for the phased plan and [docs/assumptions.md](docs/assumptions.md) for every constant the simulator assumes.

## What works today

- Library of 5 models (MobileNetV2, ResNet-50, YOLOv8 n/s/m) and 5 devices (Jetson Orin Nano/NX/AGX, plus L40S and H100 reference GPUs).
- Analytical L0 simulator: roofline latency, power, energy, steady-state temperature, throttling risk, memory fit, cost and carbon. Every number carries a unit, uncertainty band and provenance label.
- Five-state constraint certification using pessimistic bounds. Hard constraints (default 55 W, 90% accuracy) are never relaxed.
- Search over precision, batch, power mode and cooling, ranked by certified feasibility then energy.
- FastAPI backend (SQLite) and a React page. An example robotics project is seeded on start.

Not yet: ONNX parsing, coupled thermal solver, real GPU measurements, the Nemotron agent, datasheet import. All edge numbers are **analytical predictions**, not measurements.

## Run it

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

Copy `.env.example` to `.env` for the Nebius and Tavily keys (not needed yet).

## Licence

Apache-2.0. See [LICENSE](LICENSE).
