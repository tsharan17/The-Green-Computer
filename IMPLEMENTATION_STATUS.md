# Implementation status

Plan: [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md). Updated at the end of every phase.

## Phase 1: audit and baseline (done)

- Read the repository, README, build plan, tests and the system map (rendered from the image-only PDF).
- Baseline before any change: `pytest -q` 202 passed; `ruff check .` clean; `npm run build` OK.
- Added mypy (pydantic plugin) and fixed the 35 type errors it found in existing code.
- Wrote `CLAUDE.md`, `docs/IMPLEMENTATION_PLAN.md`, this file.

## Phase 2: accounts, tenancy, versions, history (done)

What changed
- Alembic migrations (`backend/app/migrations`): `0001_baseline` adopts a 0.7.0 database as-is;
  `0002_accounts_tenancy` adds users, workspaces, memberships, sessions, password resets, project
  versions, artifacts, audit log, usage events and owner columns. Additive only. Data from before
  accounts moves to a "Local workspace" claimed by the first account; library measurements stay
  shared. Runs at start-up (`GC_AUTO_MIGRATE=1`), or `python -m alembic upgrade head`.
- Self-hosted auth (`app/auth`): scrypt hashes (stdlib), opaque session tokens stored as SHA-256,
  HttpOnly SameSite=Lax cookie + `X-GC-CSRF` header + Origin check, bearer API tokens, sign-in
  rate limits, no account enumeration, password change (signs out other sessions), reset by email
  (console outbox in development, SMTP when configured; the link is shown in the response only
  outside production), account deletion (password + typed DELETE; deletes solely-owned
  workspaces with all rows and files, hands shared workspaces over).
- Tenancy: every owned row has `workspace_id`; repository, services, agent tools and routers take
  the caller's workspace; other tenants' objects answer 404. Custom devices carry an owner.
  Measurements and calibrations are per workspace on top of the shared library.
- Projects: immutable versions on every input change, restore-as-new-version, archive, run
  history with the version each run analysed, stored runs downloadable as JSON.
- Uploads: blob store interface (`app/providers/storage.py`, local disk per workspace,
  content-addressed), artifact rows for every upload (refused ones keep no bytes), ONNX validation
  report (inputs/outputs, opsets, operator histogram, unmodelled ops, external data, quantised graphs).
- Audit trail and usage metering (analyses, exports, uploads, execution and GPU seconds) with a
  usage summary that keeps platform cost (operator-configured rates; zero when self-hosted)
  separate from the device electricity estimate of each analysis.
- Web UI: sign-in / sign-up / forgot / reset screens, workspace with onboarding and projects,
  workspace switcher, account page (password, sessions, API tokens, team workspaces and members,
  delete account), project shell with the workflow rail, history tab (versions, runs, files,
  audit). Results are restored from the stored analysis after a reload. New visual system
  (IBM Plex Sans bundled locally, light and dark).

What works in the browser
- Create an account, land on the workspace with an example project, analyse it, reload and still
  see results, open History, change password, create API tokens, create a team workspace and add
  members, delete the account.

Verification (2026-10-19)
- `pytest -q`: 219 passed (17 new: auth, CSRF/Origin, reset, versions, cross-tenant isolation over
  every owned endpoint, roles, deletion, uploads/usage, migrations, legacy claim).
- `ruff check .` clean; `mypy app` clean (83 files); `npm run build` OK.
- `python scripts/acceptance.py http://localhost:8010` against a running server: 22 passed,
  2 skipped (agent and GPU jobs not configured), 0 failed. The script now signs up a throwaway
  account and deletes it at the end.
- Browser check of sign-up, workspace, analysis, history (built-in browser).

Limitations
- No email verification step; sign-up is open unless `GC_ALLOW_SIGNUP=0`.
- PostgreSQL is supported by configuration and portable types but not yet exercised in a test run
  here (no PostgreSQL server in this environment).
- Rate limits are in-memory (one process). Use one worker or a shared limiter in production.
- Members can only be added if they already have an account (no invitation emails).

## Phase 3: intake, validation, capability detection (done)

What changed
- Format catalogue per hardware category (board/SoC, MCU, FPGA, accelerator, custom system) and
  for models (`app/engine/intake_formats.py`): each format is supported (a parser exists),
  planned or unsupported, with what it gives the analysis and the exact format that works today.
  Schematic, PCB/Gerber, RTL, netlist, assembly and raw firmware images are honestly "planned".
- One upload door `POST /intake/upload`: identifies the file, validates it, records an artifact
  with its report, keeps bytes only for usable files, and answers valid / needs_review / invalid /
  unsupported (never a fake success).
- Device-profile validation with units (`app/engine/hw_validate.py`): values may be written as
  "68 GB/s", "250 mW", "8 GiB", "85 °C"; conversions are reported; required fields, plausible
  ranges and consistency (throttle < shutdown, mode caps above idle, default cooling exists...)
  are checked. Downloadable template profile.
- Firmware footprint from ELF section tables (`app/engine/elf_report.py`, ELF32/64, both byte
  orders): flash and RAM use checked against the project device.
- Offline datasheet reading (`app/engine/datasheet_scan.py`): text per page, scanned-page
  detection, candidate values with page and source line for a person to confirm. OCR runs only if
  Tesseract + pytesseract + pymupdf are installed; otherwise scans go to manual review.
- ONNX validation report: checker result, inputs/outputs, opsets, operator histogram, operators
  without a cost model, external data, already-quantised graphs, dynamic dimensions (the UI asks
  for a value and re-checks).
- Interfaces: `providers/execution.py` (local CPU required; CUDA/TensorRT only when ONNX Runtime
  has them and a flag is set; Nebius behind `GC_ENABLE_NEBIUS`; remote device planned) and
  `providers/ai.py` (optional assistant). `GET /capabilities` reports everything live.
- Web UI: "Model and hardware" page with the category-aware intake panel and per-file results
  (use model, add profile, copy datasheet values into the hardware form, firmware fit), a separate
  "Constraints and environment" page (performance limits, environment, today's baseline), a
  save-as-version / analyse bar, and the "What this installation can do" screen.

Verification (2026-10-19)
- `pytest -q`: 234 passed (15 new intake tests with a generated ELF and generated PDFs, one of
  them text-less like a scan). `ruff` and `mypy` clean. `npm run build` OK. Browser check of the
  input, constraints and capability screens.

Limitations
- OCR is implemented but untested here (no Tesseract in this environment); the capability screen
  reports it unavailable.
- Datasheet candidates are pattern matches: they find common phrasings, not every table layout.
- ELF footprint is static (no heap/stack high-water mark).

## Phase 4: digital twin v1 (done)

What changed
- Versioned trace schema `green-computer.trace/1` (`app/schemas/twin.py`): components with
  normalised x/y/z layout hints (ready for a 3D view), memory paths, tensors, per-operator events
  (time split into compute / memory / launch overhead, FLOPs, bytes, bandwidth use, allocations and
  frees, working set, power, energy split into compute / memory / idle / leakage / cooling,
  components touched), stages, memory timeline, bottlenecks, thermal view, assumptions.
- The ONNX parser now records tensor wiring (producers, consumers; in-place elementwise and view
  operators alias their input), so lifetimes and the working-memory peak come from the graph.
- Trace builder (`app/twin/trace.py`) reuses the engine: the solver's nominal operating point
  (clock after throttling, temperature, leakage), the per-layer roofline at that clock, and the
  power model term by term. Event times sum to the headline batch time and event energies to the
  headline energy per inference (any alignment factor is reported). Library models use their
  published reference graph where one exists; otherwise the trace is one aggregate step and says so.
- Storage: `execution_traces` table (migration 0003), immutable, kind `predicted` or `measured`,
  never mixed. API: create (current / recommended / custom setup), list, get, export JSON or CSV
  (events, memory, tensors) with provenance in every row; usage metered; tenant-isolated.
- Web UI: System map (stages, hardware block diagram, memory paths sized by live bandwidth use,
  heat fill, bottleneck flags, step-through playback with an operator card), Execution timeline
  (Gantt by stage coloured by limiting resource, slowest operators), Memory map (stacked memory vs
  capacity with a scale toggle, tensor lifetimes, bandwidth pressure), Thermal and cooling
  (warm-up curve, throttle point, cooling needed, heat by component), Energy and performance
  (energy by cause and by stage, cost and carbon, plus every metric with its range). Every chart
  has hover tooltips, a table view and raw-data export; series colours are a validated palette.

Verification (2026-10-19)
- `pytest -q`: 240 passed (6 new: exact tensor lifetimes on a hand-checked graph, agreement with
  headline numbers for three model/device pairs, MCU flash layout, thermal and throughput
  bottlenecks, CSV provenance, API + isolation). `ruff`, `mypy` clean; `npm run build` OK.
- Browser check of all five analysis screens on the example project and a ResNet-50 project.

Limitations
- Thermal model is lumped (one node): per-component heat is an attribution of power, not a
  temperature map. The UI says so.
- Operator times are roofline predictions (not cycle-accurate); kernels that fuse in a real
  runtime appear as separate operators here.
- YOLO library models have no built-in graph: upload their ONNX for an operator-level trace.

## Phase 5: plans, cooling catalogue, exports (done)

- `app/engine/plan.py`: recommendations become explicit changes (config, model swap, device swap,
  design what-if, catalogue cooling); stated conflict rules; baseline / each change / combined
  comparison with old-vs-new parameter and metric tables. Saved plans are immutable, versioned by
  name (`design_plans`, migration 0004).
- Cooling catalogue (`app/data/cooling_catalogue.yaml`, 13 classes) ranked by stated criteria
  (meets requirements, lifetime kgCO2e/year, then maintainability/recyclability shown).
- Exports (`exports` table, each labelled generated_validated / generated / template): report
  MD/HTML/PDF (dependency-free PDF writer), plan JSON, comparison CSV/JSON, recommendations
  CSV/JSON, hardware change spec, deployment config (template), recipe zip, plan package with
  MANIFEST, INT8 ONNX only when quantisation runs in the isolated worker and outputs agree
  (cosine >= 0.99 on synthetic inputs; task accuracy explicitly not measured).
- Isolated execution worker (`app/execution/`) with timeout; handles newer ONNX IR versions honestly.
- UI: plan builder, saved plans, cooling options table, export panel with history.
- Verified: `pytest -q`, ruff, mypy clean; browser check of the plan builder and comparison.

## Phase 6: execution, measurements, verification (done)

- Local run (`POST /projects/{id}/executions`): background job driving the isolated worker
  (time limit `GC_EXEC_MAX_SECONDS`, one run per workspace at a time) on the project's uploaded ONNX
  file or the rebuilt reference graph (ResNet-50, MobileNetV2). Stores a latency measurement for the
  `host-cpu` profile (hardware label = the real CPU; power never filled in), refits the workspace
  calibration, a measured trace (`kind=measured`, operator timings from the ONNX Runtime profiler,
  no thermal or energy fields), and a predicted-vs-measured comparison by operator type computed
  before the refit. Jobs interrupted by a restart are marked failed at start-up.
- CUDA / TensorRT backends appear only when ONNX Runtime provides them and `GC_ENABLE_CUDA` /
  `GC_ENABLE_TENSORRT` is set; Nebius jobs refuse unless `GC_ENABLE_NEBIUS=1`.
- Measurement import adds generic CSV (one row per measurement, field names or aliases, unknown
  columns refused) and JSON lists, alongside bench JSON, nvidia-smi and tegrastats.
- UI: "Run on this server" tab with backend status, live job, measured KPIs, prediction error and
  operator-type comparison; the import form offers the new formats.
- Verified: `pytest -q` 252 passed (5 new execution tests with real ONNX Runtime runs); browser
  run of ResNet-50 on this CPU (24.4 ms measured vs 20.2 ms predicted, -17%).
- Limits: CPU power/temperature not measured; GPU backends untested here (no NVIDIA GPU).

## Phase 7: hardening, quality, docs, deployment (done)

- Security: `tests/api/test_security.py` enumerates every operation in the OpenAPI schema (94) and
  proves each answers 401 without a session (except health and the auth flow) and 403 without the
  CSRF header; cookie flags, headers, escaping and safe download names. Model of threats and limits:
  `docs/security.md`. Found and fixed: none exploitable; the report now names the project.
- PostgreSQL: `tests/test_postgres.py` (runs when `GC_TEST_PG_URL` is set; CI provides a PostgreSQL
  16 service) migrates a fresh database, checks every table/column and real foreign keys, and runs a
  full journey including account deletion. Found and fixed a PostgreSQL-only crash (SUM over bigint
  returns Decimal in the usage summary). Run here against PostgreSQL 16 via pgserver.
- Browser tests (Playwright, `frontend/e2e`): sign-up, analysis, design plan, comparison, saved plans,
  analysis screens, exports with downloads, history; ONNX upload and an unsupported RTL file; sign-out
  / sign-in with a wrong password; cross-account isolation; account deletion. Accessibility: axe-core
  WCAG 2.1 A/AA on 13 screens in light and dark modes (fixed nested-interactive roles on charts).
  Downloads now always save (generic blob type). Locally Playwright uses the installed Edge.
- ESLint (typescript-eslint + react-hooks) clean; `npm run lint`.
- Deployment: Dockerfile (production env, PostgreSQL driver, migrations, non-root), compose stack
  with PostgreSQL, CI with backend (ruff, mypy, pytest incl. PostgreSQL), frontend (lint, build),
  e2e and acceptance jobs. `onnxruntime` is now a core dependency (local execution is required).
- Docs: README rewritten, `docs/api.md` generated from OpenAPI (`scripts/api_docs.py`),
  `docs/security.md`; demo data via `scripts/demo_data.py`.

Final verification (2026-10-19)
- `pytest -q` (with `GC_TEST_PG_URL`): 259 passed. `ruff check .` clean. `mypy app` clean (109 files).
- `npx tsc --noEmit`, `npm run lint`, `npm run build`: clean.
- `npx playwright test`: 7 passed (5 journeys + 2 accessibility scans).
- `python scripts/acceptance.py http://localhost:8010`: 22 passed, 2 skipped (assistant and GPU
  jobs not configured), 0 failed. `scripts/demo_data.py` ran end to end.

## Remaining limitations (honest list)

- Not built or run here: the Docker image and compose stack (no Docker), CUDA/TensorRT backends (no
  NVIDIA GPU), Nebius jobs and the AI assistant live (no credentials), OCR (no Tesseract).
- Thermal model is lumped; per-component heat is an attribution. Predictions are analytical until
  measurements calibrate them; CPU runs measure latency only.
- In-memory rate limiting (single process); no email verification or MFA; members must already have
  an account; no 3D view yet (the trace schema carries layout hints for one).
- Only ResNet-50 and MobileNetV2 can be executed without an upload; other library models need their
  ONNX file.

## Verification commands

```
cd backend && .venv/Scripts/python -m pytest -q
cd backend && .venv/Scripts/python -m ruff check .
cd backend && .venv/Scripts/python -m mypy app
cd frontend && npm run lint && npm run build && npx playwright test
python scripts/acceptance.py http://localhost:8000     # against a running server
GC_TEST_PG_URL=postgresql+psycopg://user:pw@host:5432/postgres  # then pytest also covers PostgreSQL
```
