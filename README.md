# The Green Computer

Predict how an AI model will behave on a given hardware setup **before anything is built**, then recommend the changes that meet your requirements on the least energy: to the AI model, to how you run it, to the hardware you choose, and to the chip or board itself. *Predict. Optimise. Verify. Make every computation count.*

> **Honest status (release 0.6.0).** The product works end to end and is tested (164+ backend tests, an end-to-end journey test, an acceptance script). Its numbers are **predictions** from a physics model with stated assumptions; the only real measurements so far are ResNet-50 and MobileNetV2 latency on the developer's CPU. The Green Agent (Nemotron on Nebius Token Factory), the Nebius GPU job launcher and datasheet import (Tavily) were built from the vendors' documentation and tested against fakes: **they have not been run against the live services.** The Docker image and the Nebius endpoint deployment have never been built or run. See [docs/for-judges.md](docs/for-judges.md) and the table at the end.

## How to use it (3 steps)

1. **Describe.** Pick the AI model, the hardware and what must be true (frames per second, watts, accuracy, delay, room temperature), or try an example, or tell the Green Agent in words.
2. **Results.** A plain-language verdict ("your current setup fails because it overheats and slows to 70%"), the cheapest fix, and recommendations at four levels: **change the AI model** (quantise, prune, smaller input, a lighter model), **change how you run it** (batching, power mode, clocks), **choose better hardware** (another board, better cooling) and **redesign the chip or board** (what-if ideas with their modelled effect). Each recommendation says what it gains, why, what it costs, how sure we are and how to check it.
3. **Export.** A shareable report (Markdown / web page / PDF via print) and a recipe: scripts to convert the model, build a TensorRT engine, set the Jetson power mode, measure on the board, plus design notes for hardware engineers.

Two more pages: **Technical details** (every number with its best-case to worst-case range and source, the heat model, all options tried) and **Real measurements** (predicted vs measured; calibration applied only if it predicts held-out measurements better).

## Quick start

One command (installs, builds the UI, serves http://localhost:8000):

```powershell
scripts/dev.ps1          # Windows
```
```bash
scripts/dev.sh           # macOS / Linux / Git Bash
```

Or step by step: `cd backend && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"`, `cd frontend && npm install && npm run build`, then `cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000`.

Check a running copy end to end (local or the deployed URL): `python scripts/acceptance.py http://localhost:8000`.

Optional keys go in `.env` (copy `.env.example`; never commit it): `TOKEN_FACTORY_API_KEY` for the Green Agent, `TAVILY_API_KEY` for datasheet import, `NEBIUS_PROJECT_ID` plus the `nebius` CLI for GPU jobs. Then run `backend/.venv/Scripts/python scripts/check_nebius.py`; see [docs/connecting-nebius.md](docs/connecting-nebius.md). The app works without any of them.

## How it fits together

```
 Browser (React)  ── /api/v1 ──►  FastAPI ──► Engine (pure Python, no network)
   Describe / Results / Export        │         roofline → power ⇄ temperature ⇄ throttling
   Technical details / Measurements   │         uncertainty corners → certification → search
                                      │         repair · what-ifs · advice · report · recipe
                                      ├──► SQLite: projects, runs, measurements, calibrations, drafts
                                      ├──► Green Agent ──► Nemotron on Nebius Token Factory (tools only)
                                      ├──► Tavily (datasheet search) ──► Nemotron (extract) ──► you confirm
                                      └──► `nebius ai job` ──► Serverless Job on an NVIDIA GPU (bench/)
```

The agent never computes a number: it plans and explains by calling the engine as tools, a guardrail rejects any figure not found in a tool result, and the user's requirements are read-only to it.

## Repository map

| Path | What |
|---|---|
| `backend/app/engine/` | The deterministic engine and the advice, repair, what-if, recipe and report logic |
| `backend/app/agent/` | Token Factory client, router, tools, loop, guardrail, datasheet extraction |
| `backend/app/api/`, `services/`, `db/`, `integrations/`, `security.py` | API, orchestration, storage, Nebius/Tavily clients, public-demo safeguards |
| `backend/app/data/` | Device and model library (YAML), committed real measurements |
| `frontend/` | The React app |
| `bench/` | Benchmark scripts and the Nebius job entrypoint |
| `deploy/`, `Dockerfile`, `docker-compose.yml` | Container and Nebius endpoint deployment (never built or run) |
| `scripts/` | `dev.*`, `check_nebius.py`, `acceptance.py`, a fake model server for credential-free development |
| `docs/` | Assumptions, connecting Nebius, judge guide, demo script, Devpost draft, credits and cost |

## Public demo mode

`GC_PUBLIC_DEMO=1` turns off the actions that spend money (GPU jobs, datasheet search), rate limits the agent and the analysis per address, caps uploads and gives each visitor their own project. See [deploy/endpoint.md](deploy/endpoint.md).

## What is and is not verified

| Piece | Status |
|---|---|
| Engine, API, UI, report, recipes' syntax, calibration, safeguards | Tested (unit, API, end-to-end journey, acceptance script, browser checks) |
| Parser | Reproduces the published parameter and FLOP counts of ResNet-50 and MobileNetV2 |
| Real measurements | CPU latency only, on the development machine. **No GPU, Jetson or power data** |
| Green Agent, Nebius jobs, Tavily import | Built from vendor docs, tested with fakes. **Never run live** |
| Recipes | Syntax-checked, never run on a device |
| Docker image, Nebius endpoint | Written, **never built or deployed** |
| Chip-design what-ifs | Directional: the model has no on-chip memory hierarchy |

## Licence

Apache-2.0. See [LICENSE](LICENSE).
