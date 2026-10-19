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

## Release 2, slice A: simple first, powerful on demand (done)

What works
- Kelly green (#4CBB17) and white identity in light and dark: hairline rules instead of cards, kelly
  as a fill with dark ink, a deeper kelly for links. State is always icon + words + colour.
- Guided start (`#/start`, where new accounts land): use case → model (library or ONNX upload) →
  hardware → "What matters most?" (Balanced, Faster response, Lower power, Lower heat, Lower cost, Fit
  into memory) → Analyse → Summary. `POST /guide/start`, `GET /guide/use-cases`.
- The priority changes which feasible setup is recommended (`engine/optimise.py` `PRIORITY_METRIC`);
  it never loosens a requirement. Stored on the spec as `priority` (additive, default `balanced`).
- Summary screen per project: verdict today → with the plan, biggest bottleneck in plain words,
  recommended next step (what, why, benefit, trade-off, confidence, evidence, how to check it, plus
  the smallest fix if it differs), then "Explain" (bars against your limits) and "Engineering detail"
  (every metric with range and source, checks, run JSON).
- Decision bar on every project screen: setup, outcome today, recommended plan, expected improvement,
  confidence, one primary action (Analyse / Review the plan / Export).
- Simple / Engineering display preference, stored per user (`GET/PUT /auth/preferences`, migration
  `0006_user_preferences`). Simple folds detail and tucks the five engineering views under one
  disclosure; Engineering opens everything.
- Glossary with plain-language terms and "Why does this matter?" disclosures; human error messages
  with a recovery action; skeleton loading and empty states.
- Workspace: first-run explanation with the three steps, project health table (outcome today,
  bottleneck, outcome with the plan, energy saving, "inputs changed since"), `GET /projects-health`.
- Five analysed example projects in one click (`POST /guide/demo`): microcontroller voice, smart
  camera, FPGA inspection, GPU server, cloud detection.
- Global search (Ctrl/Cmd+K) over projects, plans, analyses, recommendations, hardware, models,
  components and tensors, scoped to the workspace (`GET /search`).
- Sign-in screen states what the product does, the first step and the result, with a labelled
  illustration of a result.

Tested
- `tests/api/test_guide.py`: priority ranking, guided start, demo + health + staleness, search
  (including another workspace seeing nothing), preferences validation.
- `tests/test_postgres.py` now also drives the guided start, demo, health, search and preferences on
  PostgreSQL, and checks search isolation there.
- Playwright: the journeys follow the new flow (sign-up → guided start; analyse → Summary → decision
  bar → plan); new journeys for the guided start with the mode switch (persisted across reload) and
  for example projects + search. axe WCAG 2.1 A/AA scans run on the guided start, workspace and every
  project screen in both Simple and Engineering modes, in light and dark.
- Checked by hand in the browser at desktop and phone width (no horizontal scroll), light and dark.

Still analytical or not done in this slice
- The twin pages (system map, timeline, memory, thermal, energy), Recommendations and Verify keep
  their existing layouts under the decision bar; they do not yet carry their own Summary/Explain/
  Engineering levels. Slices B–H (system graph and parsers, 3D map, multi-node thermal, cooling v2,
  device agent, handoff packages, operations) are not started.

Verification (2026-10-19)
- `pytest -q --basetemp <scratch>`: 262 passed, 2 skipped (PostgreSQL, run separately);
  `GC_TEST_PG_URL=... pytest tests/test_postgres.py`: 2 passed (local pgserver, PostgreSQL 16).
- `ruff check .` clean; `mypy app` clean (111 files).
- `npx tsc --noEmit`, `npm run lint`, `npm run build`: clean.
- `npx playwright test`: 9 passed (7 journeys + 2 accessibility scans covering both modes).

## Release 2, slice B: hardware system graph and bounded design-file parsers (done)

What works
- Versioned system graph per project (`green-computer.system-graph/1`, `schemas/system_graph.py`,
  table `system_graphs`, migration `0007_system_graphs`, additive). Components and connections with
  attributes; every component, connection and attribute names its origin (library profile, file,
  hand entry) and a confidence (stated / parsed / derived / assumed / measured). Logical diagram
  positions and physical board positions (mm) are separate fields and never mixed.
- Version 0 is built from the device profile (`engine/system_graph.py`, pure): compute, memory, power,
  cooling, plus flash and on-chip memory when present, each linked to the execution trace component
  of the same role. The latest trace adds per-component event counts, busy time and heat.
- Parsers (`engine/design_parsers.py`, pure, size/depth/count bounded), routed by the upload door:
  - KiCad 6+ schematic (.kicad_sch): parts, title block, sub-sheets, labels. Wires are not traced.
  - KiCad board (.kicad_pcb, v5+): outline size, copper layers, thickness, footprints with x/y,
    rotation and side, nets between parts (wide nets such as GND summarised).
  - Verilog-2001 / SystemVerilog subset (.v, .sv): modules, parameters, ANSI and non-ANSI ports
    with widths, instance hierarchy, external modules. Widths use a literal-only arithmetic
    evaluator (no `eval`).
  - Vivado report_timing_summary: WNS/TNS/WHS/THS/WPWS, endpoints, clocks, "constraints met".
  - Vitis/Vivado HLS csynth.rpt and csynth.xml: latency and interval in cycles, target/estimated
    clock, resource estimates and availability.
  - Already supported and now merged into the graph: Vivado utilisation and power reports.
- Bad files are refused with a reason and recorded without keeping the bytes (truncated or
  unbalanced S-expressions, KiCad 5 legacy .sch, VHDL, no modules, unknown reports). VHDL, other
  EDA formats, netlists and Gerbers stay "planned" and name the format that works today.
- API: `GET /projects/{id}/system-graph`, `/versions`, `/{version}`, `/sources`, `/diff?from=&to=`,
  `POST /system-graph/from-files` (merge uploaded files into a new version), `POST /system-graph`
  (save an edited graph; validated for unique ids, existing parents and connection ends, no
  parent cycles, same device as the project). A new fact for an existing attribute is kept next to
  the old one with its own origin, never silently replaced.
- UI: a "Hardware graph" section on the System map page with a plain summary, version picker,
  "add uploaded design files", Explain (counts by kind, board layout drawn to scale in mm, with top
  and bottom shown by shape), and Engineering detail (filterable parts table with source,
  confidence, trace events, every fact; connections table; limitations).

Tested
- `tests/engine/test_design_parsers.py` (16): every parser on realistic fixtures
  (`tests/fixtures/design/`), refusal of nine kinds of bad input, safe width arithmetic, graph
  build/merge/validate/diff, provenance kept on merge.
- `tests/api/test_system_graph.py` (3): upload answers, invalid uploads not stored, versions, diff,
  save and validation errors, trace links, other-workspace access returns 404 on every graph route,
  another workspace's file cannot be merged, unauthenticated 401, rows removed on account deletion.
- PostgreSQL journey now uploads Verilog and builds a graph; deletion check includes `system_graphs`.
- Playwright: a journey uploads Verilog, adds it to the graph and finds its part and source in the
  engineering table; axe scans the System map page (with the graph) in both modes and schemes.
- Checked in the browser with the KiCad, Verilog, Vivado timing and HLS fixtures on the FPGA demo.

What is not claimed
- No electrical, thermal, timing or functional simulation is run on any design file. Timing values
  are shown only as "Vivado static timing analysis" from an uploaded Vivado report; HLS figures are
  labelled as pre-implementation estimates.
- The Verilog reader is a subset parser (no preprocessor, generate elaboration or SystemVerilog
  interfaces/packages); it warns when such constructs are present.

Verification (2026-10-19)
- `pytest -q --basetemp <scratch>`: 281 passed, 2 skipped (PostgreSQL, run separately);
  `GC_TEST_PG_URL=... pytest tests/test_postgres.py`: 2 passed.
- `ruff check .`, `mypy app` (116 files): clean. `tsc`, `eslint`, `vite build`: clean.
- `npx playwright test`: 10 passed.

## Release 2, slice C: interactive 3D map (done)

What works
- A "3D map" section on the System map page (`frontend/src/twin/map3d/`), built with three.js
  0.169 and @react-three/fiber 8.17 (pinned, MIT, no other helper libraries). The WebGL code is a
  separate chunk loaded only on that page; the main bundle stays at about 408 kB.
- One pure scene model (`model.ts`) built from the same schemas as the 2D views: the system graph
  (`system-graph/1`) and execution traces (`trace/1`). The 3D view and its table fallback both
  render that model, so they always show the same parts and values.
- Two layouts, labelled and never mixed:
  - logical: the modelled parts in the 2D map's arrangement; parts, logic modules and clocks read
    from design files sit on top of the block they belong to;
  - physical (board): parts at their millimetre positions from a KiCad board file, top side above
    the board and bottom side below it as outlines, with nets as lines. Without a board file it
    says what to upload instead of drawing a guess.
- Overlays: heat (block colour and height, watts in the label), activity (the running operator's
  parts glow and are outlined, "busy" in the label; memory paths thicken with bandwidth use) and
  plain.
- Playback of one batch on a time slider. "Today and the plan side by side" plays both traces on one
  clock, so the faster setup finishes first.
- Click a block for its kind, heat, board side, source, confidence and whether it is busy. Turn and
  zoom by dragging, the wheel, the arrow and +/- keys on the focused map, or buttons.
- Follows light and dark mode. Fits phone width (camera backs off on narrow screens).
- Accessibility: the map is a labelled image with a text summary and a live line naming the running
  operator; "Show as a table" (and automatically when WebGL is unavailable) gives every value as a
  table; legends use shape and words as well as colour.

Tested
- Playwright journey: logical map renders, keyboard turning and zoom, the table fallback carries
  heat values, today vs plan rows and the shared clock, and the physical layout's honest message
  without a board. axe scans of the System map pass in both modes and both colour schemes.
- Checked by hand: FPGA demo with the KiCad board, Verilog, Vivado timing and HLS fixtures, in
  logical and physical layouts, heat and activity overlays, compare mode, light and dark, desktop
  and phone width.

Not claimed
- Logical positions are a diagram, not a floor plan. Heat values are those of the trace shown
  (predicted unless the trace is measured). Physical layout shows positions only; nothing about
  copper, current or heat spreading is computed.
- No automated pixel tests of the WebGL output; the shared scene model is checked through the
  table view.

Verification (2026-10-19)
- `npx tsc --noEmit`, `npm run lint`, `npm run build`: clean. `npx playwright test`: 11 passed.
- `npm audit --omit=dev`: 0 vulnerabilities. No backend changes in this slice; backend suite as in B.

## Release 2, slice D: thermal attribution, runtime effects, evidence and calibration quality (done)

What works
- Multi-node thermal view (`engine/thermal_nodes.py`, pure): compute die, memory, voltage
  regulators, package and heatsink/board, solved as a resistor network by nodal analysis. Every
  number is labelled:
  - lumped: the decision model, unchanged and still the only one used for pass/fail;
  - attribution: the lumped heat split over the network. Resistances inside the package are
    assumptions unless the profile's extras state `r_jc_k_per_w` / `r_cs_k_per_w`. The
    sink-to-ambient resistance is derived, so all heat at the die reproduces the lumped temperature
    exactly. Heat inputs are scaled to the lumped power;
  - measured: a temperature from a real run at the same operating point;
  - validated / not validated: the lumped prediction is within 3 °C of that measurement, or not.
  The summary names the warmer of die and memory. The regulators' temperature rests on an assumed
  coupling and is presented as a prompt to check.
- Memory hierarchy (`engine/runtime_effects.py`): on-chip memory, main memory or SRAM, flash
  (weights in place) and the host link for discrete GPUs and accelerators. Each level has
  capacity, bandwidth, what it holds, whether it fits, traffic per batch, time at bandwidth and
  the source of the figure.
- Runtime effects, each marked whether the headline latency includes it and whether it is
  analytical or assumed:
  - included in the headline: launch/framework overhead and operator fusion;
  - not included: host transfer (unknown without an operator graph), model loading at start-up,
    batch fill wait, and queueing;
  - queueing: 0 for steady arrivals, an M/D/1 mean wait for random arrivals, and "piles up" when
    utilisation is at or above 100%;
  - offline mode reports time per 1000 inputs instead;
  - a from-arrival-to-answer estimate when the queue is stable.
- Evidence per value (`GET /projects/{id}/evidence`): every headline metric for today and the
  plan, with value, band, provenance, the profile facts and user inputs behind it (with each
  fact's source from the profile), and whether and which calibration version was applied.
- Calibration quality (`GET /calibration/quality?device_id=`, also inside evidence): per precision
  the latency and power fit grades (none / too few / rejected / fair / good / strong) with the
  reason, leave-one-out errors, runs, batches covered and runs that carry a temperature.
- `GET /projects/{id}/physics?which=baseline|best` returns thermal, memory and runtime together.
  It is read-only and nothing is stored.
- UI:
  - Thermal page: "Heat by part", with a temperature ladder (lumped bar plus attribution bars,
    each tagged), measured/validated status with icon and words, label meanings, and the
    resistor network with sources;
  - Energy page: "Around the model: runtime and memory" (plain sentence, runtime effects table,
    memory hierarchy) and "Evidence for every number" (expandable rows, today/plan switch,
    calibration quality table).

Tested
- `tests/engine/test_thermal_runtime.py` (5):
  - all heat at the die reproduces the lumped model exactly;
  - labels, and heat scaled to the lumped power;
  - the die is never hotter than lumped;
  - validated vs not validated;
  - profile resistances replace assumptions;
  - memory levels for SoC, MCU (flash) and GPU (host link);
  - queueing stable, unstable and offline;
  - unknown transfer size without a graph.
- `tests/api/test_physics.py` (2):
  - evidence before and after analysis;
  - 409 for the plan's physics before analysis;
  - a measured temperature at today's exact setup turns status to validated or not validated
    with its source;
  - calibration quality counts runs and temperatures;
  - unknown device returns 404;
  - another workspace gets 404 and an anonymous caller gets 401.
- PostgreSQL journey calls physics, evidence and calibration quality.
- Playwright journey for the new sections. axe passes on the Thermal and Energy pages in both
  modes and colour schemes.
- Checked in the browser on the robot example (heat-limited today).

Not claimed
- The multi-node temperatures are an attribution of the lumped model with assumed internal
  resistances, not a thermal simulation; nothing here is used for pass/fail. Storage and host-link
  speeds and runtime set-up times are named assumptions. Queueing uses textbook models (D/D/1,
  M/D/1), not measured arrival traces.

Verification (2026-10-19)
- `pytest -q --basetemp <scratch>`: 288 passed, 2 skipped; PostgreSQL: 2 passed.
- `ruff`, `mypy app` (120 files), `tsc`, `eslint`, `vite build`: clean.
- `npx playwright test`: 12 passed.

## Release 2, slice E: cooling catalogue v2 (done)

What works
- Catalogue v2 (`data/cooling_catalogue.yaml`, additive; v1 entries still load). Each of the 13
  classes now records:
  - which heat sources it reaches (die, memory, regulators);
  - the heat load it is sized for;
  - what it needs from the place it runs (free air, a fan path, vents, radiator room, a board
    change, a data-centre rack, facility water) and its height;
  - repairability, hazardous materials and on-site water use (null where it depends on the
    facility, and said so).
- "Where it runs" on each project (`ProjectSpec.environment`, additive JSON in the spec, no
  migration): sealed enclosure, dusty site, noise limit, room above the board, data-centre rack,
  facility water. Unset fields rule nothing out.
- Ranking criteria, in order (`engine/cooling_catalogue.py`):
  1. usable where it runs and sized for the heat;
  2. meets the requirements;
  3. lowest lifetime emissions;
  4. shown for judgement, not scored: repairability, recyclability, hazardous materials, water,
     upkeep, noise, cost.
- Options that are ruled out are listed with their reasons, never silently dropped. Cautions
  are shown for usable options (dust and fans, coolant handling).
- Per-heat-source rationale: heat per source from slice D's attribution (labelled as such), its
  share, why it matters, and which usable options reach it. Each option shows the share of the
  heat it reaches.
- UI:
  - Thermal page: the cooling section opens with a plain "best fit here" sentence and the current
    limits (with a link to change them), then the rationale under Explain, a sustainability
    column and the ruled-out options with reasons;
  - Constraints page: a "Where it runs" block.
- Fixed in passing: an absolutely positioned screen-reader label inside a scrolling table widened
  the page on narrow screens. `.table-wrap` is now a positioning context.

Tested
- `tests/api/test_cooling_v2.py` (4):
  - every entry has the v2 fields;
  - blockers for a sealed box, noise, height, heat load, rack and water, and that parts needing
    no airflow stay usable;
  - cautions, sustainability notes and the rationale wording;
  - the API with a sealed, quiet, dusty environment: fans and vents ruled out with reasons.
- The existing cooling test was updated for the added criterion.
- PostgreSQL journey stores an environment and gets the ruled-out options.
- Playwright: the Constraints page "Where it runs" changes the Thermal page's options and reasons.
- Checked in the browser on the robot example, with and without a sealed enclosure, including
  page width.

Not claimed
- Class heat limits, heights, repairability and water notes are planning estimates per class, not
  product data. Confirm with the chosen part's datasheet and a temperature log.

Verification (2026-10-19)
- `pytest -q --basetemp <scratch>`: 292 passed, 2 skipped; PostgreSQL: 2 passed.
- `ruff`, `mypy app`, `tsc`, `eslint`, `vite build`: clean. `npx playwright test`: 13 passed.

## Release 2, slice F: remote device agent (done)

What works
- Protocol `green-computer.agent/1` (`app/remote/protocol.py`, pure; documented in
  `docs/remote-agent.md`).
  - The agent polls over HTTPS; the server never connects to a device.
  - A one-time pairing code (15 minutes, stored hashed, rate-limited) is exchanged for a device
    token (stored hashed) and a per-device HMAC-SHA256 key.
  - The key is derived from the server secret and the device's key version, so the server never
    stores it. Re-pairing rotates it.
  - The server secret comes from `GC_AGENT_SIGNING_SECRET`, or a random key created once in the
    data directory. It is never in source.
- Signed run requests: one allow-listed action (`benchmark_onnx`), bounded parameters, nonce, a
  one-hour expiry, and the approved artifact's SHA-256 and size.
  - Only a validated ONNX model stored in the workspace can be named.
  - Creating the request is the approval, and it is audited with the approver.
- Signed results. The server verifies the signature, job, nonce, file hash and sample bounds, then
  runs the measurement-quality checks (`engine/measurement_quality.py`, pure):
  - runs, spread, outliers, drift, warm-up, timer resolution, temperature rise, duration;
  - verdict good / usable / poor.
  - Measured results that are not poor become measurements (source `remote_agent`, quality
    notes attached), which feed calibration and thermal validation.
  - Simulated results are kept and labelled, never imported.
- The agent (`agent/gc_agent.py`): a single file, standard library only, with ONNX Runtime and
  NumPy for real runs.
  - It verifies signature, addressee, expiry, nonce (replay store), action allow-list, local
    policy limits and the downloaded file's SHA-256.
  - It runs ONNX Runtime CPU inference only, and imports no `subprocess` (it has no shell).
  - It reads Linux thermal zones when present and never guesses temperatures.
  - `--simulate` gives fake, deterministic timings labelled "simulated".
  - Plain http is refused except to localhost or with an explicit flag.
  - If ONNX Runtime refuses a newer IR version, it lowers the header field (with the `onnx`
    package) and says so in the result.
- Revocation invalidates the token at once and fails queued and claimed requests.
- Tables `remote_devices` and `remote_jobs` (migration `0008_remote_agents`, additive). Both are
  workspace-owned and removed with the workspace.
- UI: Verify → "Run on a device":
  - register a device and see the pairing code once, with the exact commands;
  - device list with online / offline / waiting / revoked (icon and words) and the agent's host and
    runtime;
  - new pairing code and revoke;
  - approve a run (file, precision, batch, runs, time limit, with the SHA-256 shown);
  - run list with status, measured/simulated tag, quality verdict and checks, and the stats.

Tested
- `tests/api/test_remote_agent.py` (5) drives the real agent code through the API:
  - pairing, including a wrong code and single use of a code;
  - a simulated run (not imported);
  - a real ONNX Runtime run that is quality-checked and imported as a `remote_agent` measurement;
  - agent-side refusal of a bad signature, a foreign key, a non-allow-listed action, expiry,
    over-policy parameters, replay, and a request tampered with on the server;
  - server-side refusal of a bad result signature, a wrong file hash, out-of-bounds parameters and
    a non-ONNX file;
  - revocation;
  - another workspace sees nothing and gets 404s;
  - rows removed on account deletion;
  - quality verdicts for good, few runs, noisy, drifting, coarse timer, empty and heating.
- Route security tests: every agent route refuses anonymous calls, and a signed-in browser session
  cannot act as a device.
- PostgreSQL journey: register, pair, poll, revoke.
- Playwright `device-agent.spec.ts`:
  - register in the UI and pair the real agent process with the code shown;
  - see the device online, approve a run and run the agent once in simulator mode;
  - see the labelled result, then revoke, after which the agent is refused.
- axe scans the Devices tab in both colour schemes.
- Checked by hand: the preview server with the agent paired from a shell.

Not done or not claimed
- No real device other than this Windows laptop was used. ONNX Runtime's CPU execution provider
  only: no GPU/NPU providers, TensorRT or vendor runtimes. The agent reads no power; import a power
  log for that.
- Agent results are as honest as the device running the agent. The signature proves which paired
  agent sent them, not that the hardware matches its profile.

Verification (2026-10-19)
- `pytest -q --basetemp <scratch>`: 298 passed, 2 skipped; PostgreSQL: 2 passed.
- `ruff` (backend and agent), `mypy app` (125 files), `tsc`, `eslint`, `vite build`: clean.
- `npx playwright test`: 14 passed.

## Remaining limitations (honest list)

- Not built or run here: the Docker image and compose stack (no Docker), CUDA/TensorRT backends (no
  NVIDIA GPU), Nebius jobs and the AI assistant live (no credentials), OCR (no Tesseract).
- Thermal model is lumped; per-component heat is an attribution. Predictions are analytical until
  measurements calibrate them; CPU runs measure latency only.
- In-memory rate limiting (single process); no email verification or MFA; members must already have
  an account.
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
