# The Green Computer

A vendor-neutral AI and hardware co-design platform. Describe or upload an AI model and a hardware
system, set what must be true, and see how the model will execute on that hardware before anything
is built: latency, memory, power, energy, heat, throttling, cost and carbon, operator by operator.
Then choose software and hardware changes, compare the result against today, run the model for
real where you can, and export what you decided.

It runs entirely on your own machine: no API keys, no vendor accounts, no AI provider. Local NVIDIA
GPUs and your own devices (through the device agent) are optional ways to measure, never requirements.

## Start it

- **Windows:** double-click **`Start The Green Computer.bat`** in this folder.
- **macOS / Linux:** run `./start.sh`.

It opens http://localhost:8000 in your browser. Keep the window open while you use the app, and
press Ctrl+C there to stop. The first start takes a few minutes: it creates the Python environment
and builds the interface, and needs Python 3.11+ and Node.js 20+. Later starts take seconds. Your
data stays in `green_computer.db` and `gc_data/` in this folder. Options: `--port 8080`,
`--rebuild`, `--no-browser`.

## What you can do

1. **Workspace.** Create an account; projects live in a private or a team workspace. Every change of
   inputs is a version; every analysis, plan, upload and export is in the project's history.
2. **Model and hardware.** Upload an ONNX model (validated, with a graph summary) or pick one of the
   library models; pick a board, MCU, FPGA or accelerator from the library or describe your own.
   Each hardware category lists exactly which files it accepts: device profiles (YAML/JSON, values
   may carry units), Vivado / ST Edge AI / Vela reports, power and telemetry logs, firmware ELF
   files, datasheets (read offline; scans go to OCR when installed, otherwise manual review).
   Schematics, PCBs, RTL, netlists and assembly are shown as planned, with what to send instead.
3. **Constraints and environment.** Throughput, power, latency, memory and accuracy limits; ambient
   temperature, cooling, hours of use, electricity price and grid carbon; how it runs today.
4. **Analysis (of today's setup only).** The verdict, what limits it, the numbers against your
   limits, and four figures: a board heat map, the warm-up curve, where the energy goes and power
   over one batch. No change is suggested here. Optional detail views (under "More detail") show a
   **system map** (model stages on the hardware, memory paths, heat, bottlenecks, step-through
   playback), an **execution timeline**, a **memory map** (tensor lifetimes, peak working set
   against capacity), **thermal and cooling** (cooling charts that show how warm a room each
   option can handle) and **energy and performance** (every metric with its range and source).
5. **Recommendations: try changes.** Changes at five levels: the AI model, how it runs, hardware
   settings, hardware or cooling choice, and directional chip/board ideas, ranked for your
   requirements. Click one and the engine re-runs the analysis with it: new verdict, what moves, and
   the same four figures today next to the change. Optionally ask the language model for more
   candidates (see below); nothing it proposes is applied until the engine evaluates it.
6. **Validation: plan, compare, measure.** Combine changes into a design plan; the engine
   re-analyses today, each change alone and the combination, parameter by parameter. Plans are saved
   as immutable versions. Run the model on this server's CPU (ONNX Runtime, isolated and
   time-limited) for measured latency and a measured operator trace; import measurements (bench
   JSON, CSV, JSON, nvidia-smi, tegrastats); compare predicted with measured and calibrate.
7. **Results and export.** The engineering report (Markdown, HTML, PDF), plan JSON, comparisons and
   recommendations (CSV/JSON), traces, a hardware change specification, a deployment
   configuration, the recipe scripts, a complete plan package, and an INT8 ONNX model when
   quantisation runs and its outputs match the original.

The app walks you through this in order: a numbered stepper at the top, the same six stages in the
side navigation, and Back / Next buttons on every page.

## Honesty rules

- Every number carries its range and its source: analytical, calibrated, measured, vendor
  specification or assumed. Predicted traces are labelled predicted; only real runs or imported logs
  are measured, and the two are never mixed.
- Exports are labelled *generated and validated*, *generated* or *template*. No changed PCB, RTL or
  chip-design file is ever produced; chip and board ideas are directional what-ifs.
- Accuracy effects of quantisation or pruning are priors with stated risk, never promises.
- The optional AI assistant cannot produce numbers; the engine computes all of them.

## Quick start

```powershell
scripts/dev.ps1          # Windows: installs, builds the UI, serves http://localhost:8000
```
```bash
scripts/dev.sh           # macOS / Linux / Git Bash
```

Open http://localhost:8000, create an account (it comes with an example project), and press
Analyse. Optional: `python scripts/demo_data.py http://localhost:8000` fills a demo account with
analysed projects, a plan, exports and a local run.

Production-like stack with PostgreSQL: `docker compose up --build` (see `docker-compose.yml`).
Configuration is by environment variables; `.env.example` lists every one. Never commit `.env`.

## Architecture

Workflow: inputs → verification → analysis → recommendations (engine, optional AI candidates) →
validation (plan builder, real runs) → results and exports. The full description, with a status for
each part, is in [docs/architecture.md](docs/architecture.md).

```
 Browser (React + Vite, hash routes)
   │  /api/v1  (cookie session + CSRF header, or bearer token; X-GC-Workspace)
   ▼
 FastAPI ── auth/ (accounts, sessions, workspaces) ── services/ ── db/ (SQLAlchemy, Alembic)
   │                                                     │            SQLite locally, PostgreSQL in production
   ├── engine/   pure, deterministic: roofline, power⇄temperature⇄throttling solver, uncertainty,
   │             search, advice, plans, cooling catalogue, intake validators, report/PDF writers
   ├── twin/     predicted and measured execution traces (schema green-computer.trace/1)
   ├── providers/  ExecutionBackend (local CPU required; CUDA/TensorRT optional; your own device through
   │               the device agent), BlobStore (local disk), EmailSender (log or SMTP), ArtifactGenerator labels
   └── execution/  isolated worker process: benchmark with profiler, INT8 quantisation, comparison
```

Repository map: `backend/app` (API, engine, twin, providers, migrations), `backend/tests`,
`frontend/src` (pages, twin views, components), `frontend/e2e` (Playwright), `bench/` (benchmark
scripts for GPU hosts), `scripts/` (dev, acceptance, demo data, API docs, e2e server), `docs/`.

## Checks

```
cd backend && .venv/Scripts/python -m pytest -q        # unit, API, integration (PostgreSQL with GC_TEST_PG_URL)
cd backend && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m mypy app
cd frontend && npm run lint && npm run build && npx playwright test
python scripts/acceptance.py http://localhost:8000     # against a running server
```

Details: [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md), [docs/api.md](docs/api.md),
[docs/security.md](docs/security.md), [docs/assumptions.md](docs/assumptions.md),
[docs/LAUNCH_PLAN.md](docs/LAUNCH_PLAN.md).

## What is and is not verified

| Piece | Status |
|---|---|
| Engine, API, accounts, tenancy, intake, twin, plans, exports | Tested: backend unit/API/integration tests, Playwright browser journeys, axe accessibility checks, acceptance script |
| PostgreSQL | Migrations and a full journey tested against PostgreSQL 16; SQLite is the local default |
| Local execution | Real ONNX Runtime CPU runs tested; measures latency and operator time, not power or temperature |
| Predictions | Analytical with stated assumptions; the only measurements so far are CPU latencies on the development machine |
| CUDA / TensorRT backends | Detected and gated; never run here (no NVIDIA GPU) |
| Terms, privacy and acceptable-use pages | Written to match the implementation; **draft, needs professional legal review** |
| Datasheet PDFs | Read offline by pattern; each value shows its page and line and must be confirmed. Tested with generated PDFs |
| OCR for scanned PDFs | Implemented; untested here (no Tesseract installed) |
| Docker image | Built and run before (as an earlier demo deployment); not yet built for the product hosting. The compose stack is written but not run |
| Browser journeys | 15 Playwright tests (sign-up to export, accessibility checks in light and dark) pass against a local server |
| Recipes and deployment configs | Templates; syntax-checked, not run on devices |
| Chip/board what-ifs | Directional analytical what-ifs, not designs |

## Licence

Apache-2.0. See [LICENSE](LICENSE).
