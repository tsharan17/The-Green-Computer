# The Green Computer

Predict how an AI model will behave on a given hardware setup before anything is built, then recommend the software and hardware changes that meet the requirements on the least energy. Tagline: *Predict. Optimise. Verify. Make every computation count.*

Status: **Day 5 of a 6-day build.** See [BUILD_PLAN.md](BUILD_PLAN.md) for the phased plan and [docs/assumptions.md](docs/assumptions.md) for every constant the simulator assumes.

## How to use it (3 steps)

1. **Describe.** Pick the AI model, the hardware and what must be true (frames per second, watts, accuracy, delay, room temperature), or try an example, or just tell the Green Agent in words.
2. **Results.** A plain-language verdict ("your current setup fails because it overheats and slows to 70%"), the cheapest fix, and recommendations at four levels: **change the AI model** (quantise, prune, smaller input, a lighter model), **change how you run it** (batching, power mode, clocks), **choose better hardware** (another board, better cooling) and **redesign the chip or board** (what-if ideas with how much each would help). Each recommendation says what it gains, why, what it costs, how sure we are and how to check it.
3. **Export.** A shareable report (Markdown / web page / print to PDF) and a recipe: scripts to convert the model, build a TensorRT engine, set the Jetson power mode, measure on the board, plus design notes for hardware engineers.

Two extra pages: **Technical details** (every number with its range and source, heat model, all options tried) and **Real measurements** (add measurements; predictions are re-checked and calibrated only if that helps).

## What works today

- **Plain-language verdict and cheapest fix:** certified fixes ranked by engineering effort (not just energy); if nothing works it names the binding requirements and never relaxes them.
- **Recommendations at four levels** with gain, reason, trade-offs, confidence, effort and validation steps. Model-level ideas: FP16/INT8, structured pruning, smaller input, and lighter models compared by their published accuracy. Hardware: other boards and cooling. Design what-ifs: memory bandwidth, compute, dynamic/idle/leakage power, heat path, each with its modelled effect and what limits the workload today.
- **Hardware import from a datasheet:** Tavily finds the pages, Nemotron extracts values, you review and confirm (nothing is used until you do; the agent cannot confirm). Manual entry goes through the same gate.
- **Report and recipe export** rendered from the stored analysis.
- **Models:** 5 library models, ONNX upload (pickle refused) and manual parameters. **Hardware:** Jetson Orin Nano/NX/AGX, two reference GPUs, this computer, plus anything you import.
- **Coupled solver and honest uncertainty:** power sets temperature, temperature sets leakage, a thermal governor slows the clock; every metric has a best-case to worst-case range and a source label.
- **Measurements and calibration:** import real runs (bench JSON, nvidia-smi, tegrastats) or enter them; calibration is accepted only if it predicts held-out points better. A measured INT8 accuracy lets INT8 be certified.
- **Green Agent:** Nemotron on Nebius Token Factory plans and explains through tools; a guardrail rejects figures not found in tool results; it cannot change your requirements. Disabled until `TOKEN_FACTORY_API_KEY` is set and **not yet run against the real service**.
- **Nebius GPU benchmarks:** Serverless Jobs launcher via the `nebius` CLI. **Never run against a real account.**
- **Real data so far:** ResNet-50 and MobileNetV2 benchmarks on this development machine CPU (latency only). **No GPU and no power measurement yet; Jetson results are analytical predictions.**

Not yet: any GPU/Jetson measurement, live-verified Nebius/Nemotron/Tavily calls, Tavily datasheet import, constraint repair, LLM prefill/decode and safetensors input. All edge numbers are **analytical predictions**, not measurements.

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
