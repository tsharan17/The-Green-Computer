# The Green Computer

A vendor-neutral AI and hardware co-design platform. Describe or upload an AI model and a hardware
system, set what must be true, and see how the model will execute on that hardware before anything
is built: latency, memory, power, energy, heat, throttling, cost and carbon, operator by operator.
Then choose software and hardware changes, compare the result against today, run the model for
real where you can, and export what you decided.

It runs entirely on your own machine. NVIDIA GPUs, Nebius cloud jobs and an AI assistant are
optional accelerators, never requirements.

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
4. **Analysis.** A predicted execution trace drives five views: a **system map** (model stages on the
   hardware, memory paths, heat, bottlenecks, step-through playback), an **execution timeline**,
   a **memory map** (tensor lifetimes, peak working set against capacity, bandwidth pressure),
   **thermal and cooling** (warm-up, throttling, cooling needed, catalogue options ranked by stated
   sustainability criteria) and **energy and performance** (energy by cause and stage, every metric
   with its range and source). Charts have tooltips, table views and CSV/JSON export.
5. **Recommendations and plans.** Changes at five levels: the AI model, how it runs, hardware
   settings, hardware or cooling choice, and directional chip/board ideas. Select any of them into a
   design plan; the engine re-analyses today, each change alone and the combination, and shows every
   parameter and output old versus new. Plans are saved as immutable versions.
6. **Verify, history, export.** Run the model on this server's CPU (ONNX Runtime, isolated and
   time-limited) for measured latency and a measured operator trace; import measurements (bench
   JSON, CSV, JSON, nvidia-smi, tegrastats); compare predicted with measured and calibrate. Export
   the engineering report (Markdown, HTML, PDF), plan JSON, comparisons and recommendations
   (CSV/JSON), traces, a hardware change specification, a deployment configuration, the recipe
   scripts, a complete plan package, and an INT8 ONNX model when quantisation runs and its outputs
   match the original.

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

```
 Browser (React + Vite, hash routes)
   │  /api/v1  (cookie session + CSRF header, or bearer token; X-GC-Workspace)
   ▼
 FastAPI ── auth/ (accounts, sessions, workspaces) ── services/ ── db/ (SQLAlchemy, Alembic)
   │                                                     │            SQLite locally, PostgreSQL in production
   ├── engine/   pure, deterministic: roofline, power⇄temperature⇄throttling solver, uncertainty,
   │             search, advice, plans, cooling catalogue, intake validators, report/PDF writers
   ├── twin/     predicted and measured execution traces (schema green-computer.trace/1)
   ├── providers/  ExecutionBackend (local CPU required; CUDA/TensorRT/Nebius optional; remote device
   │               planned), AIProvider (optional), BlobStore (local disk), EmailSender (log or SMTP),
   │               ArtifactGenerator labels
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
[docs/connecting-nebius.md](docs/connecting-nebius.md).

## What is and is not verified

| Piece | Status |
|---|---|
| Engine, API, accounts, tenancy, intake, twin, plans, exports | Tested: backend unit/API/integration tests, Playwright browser journeys, axe accessibility checks, acceptance script |
| PostgreSQL | Migrations and a full journey tested against PostgreSQL 16; SQLite is the local default |
| Local execution | Real ONNX Runtime CPU runs tested; measures latency and operator time, not power or temperature |
| Predictions | Analytical with stated assumptions; the only measurements so far are CPU latencies on the development machine |
| CUDA / TensorRT backends | Detected and gated; never run here (no NVIDIA GPU) |
| Nebius jobs, AI assistant, datasheet web search | Built from vendor documentation, tested with fakes; off unless configured |
| OCR for scanned PDFs | Implemented; untested here (no Tesseract installed) |
| Docker image and compose stack | Written; not built in the development environment |
| Recipes and deployment configs | Templates; syntax-checked, not run on devices |
| Chip/board what-ifs | Directional analytical what-ifs, not designs |

## Licence

Apache-2.0. See [LICENSE](LICENSE).
