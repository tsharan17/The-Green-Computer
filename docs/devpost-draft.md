# Devpost submission draft

Edit the bracketed parts after you have run the live checks. Do not claim anything this project has not verified.

**Project name:** The Green Computer
**Tagline:** Predict. Optimise. Verify. Make every computation count.
**Track:** Best Apps and Agents

## Inspiration

Engineers who put AI on robots and edge devices find out late that the model overheats, throttles, blows the power budget or sits on the wrong board. Fixing it means weeks of trial and error across the model, the software, the hardware and sometimes the chip.

## What it does

The Green Computer predicts how an AI model will behave on a given hardware setup before anything is built, then recommends changes at four levels: the AI model (quantise, prune, smaller input, a lighter model), how you run it (batching, power mode, clocks), the hardware you choose (another board, better cooling) and the chip or board design (what-if ideas with their modelled effect). It gives a plain-language verdict, the cheapest certified fix, how sure it is about each number, a shareable report and a recipe of scripts. Real measurements feed back and calibrate the model only if that demonstrably helps. Hard requirements (power, accuracy, latency) are never relaxed.

## How we built it

- A deterministic engine: per-layer roofline performance, a coupled power, temperature, leakage and thermal-throttling solve, uncertainty carried by re-solving at optimistic and pessimistic corners, five-state constraint certification, a search of thousands of configurations, effort-aware repair, hardware what-ifs.
- **The Green Agent: NVIDIA Nemotron on Nebius Token Factory** plans and explains by calling the engine as tools. It never computes a number; a guardrail rejects any figure not found in a tool result, and it cannot change the user's requirements.
- **Nebius Serverless Jobs on NVIDIA GPUs** for real benchmarks that feed calibration, launched through the Nebius CLI.
- **Tavily** to find datasheets for unknown hardware; Nemotron extracts the values; a person must confirm them.
- FastAPI, SQLite, React; one container.

## Challenges

Keeping an LLM from ever being the source of a number; modelling heat and throttling inside the search instead of after it; being honest about uncertainty when the only real measurements available were on a CPU.

## Accomplishments we are proud of

The guardrail and the read-only requirements; validating the model graph parser against published ResNet-50 and MobileNetV2 parameter and FLOP counts; calibration that rejects itself when it does not help (on real runs it cut held-out error from 130% to 16%).

## What we learned

[Fill in after the live runs.]

## What is not done (please be straight with judges)

- No Jetson, GPU or power measurement yet: Jetson numbers are predictions.
- [Update after running `scripts/check_nebius.py`: say whether the Token Factory agent and the Nebius GPU job launcher were verified live, and what you changed.]
- Generated recipes are syntax-checked only; the chip-design what-ifs are directional.

## Built with

Nebius Token Factory, NVIDIA Nemotron, Nebius Serverless Jobs and Endpoints, Tavily, Python, FastAPI, SQLAlchemy, NumPy, ONNX, ONNX Runtime, React, TypeScript, Vite.

## Feedback on Token Factory, AI Cloud and NVIDIA tools (required; also enters the Most Valuable Feedback award)

[Write this from what you actually hit when you run the live checks. Useful, specific points: how model IDs are discovered, whether tool calling worked on each Nemotron model, rate limits and latency, the shape of `nebius ai job get` output (it is undocumented), how to read job output (logs vs object storage), how to push to the registry, CPU-only endpoint options, and anything in `docs/nebius-findings` style notes you kept.]

## Submission checklist

- [ ] Devpost registered; Nebius Builder Program joined (one account per verified email)
- [ ] Decide on a provisional patent **before** the repo or video goes public (the repo must be public and open source)
- [ ] Public repo, Apache-2.0 licence visible in the About section, no keys or `.env` committed
- [ ] README: setup, architecture, where Nemotron / Token Factory / Nebius are used, honest limitations (done; re-read after live runs)
- [ ] Demo URL works with no login and stays up until 15 Dec (`scripts/acceptance.py <url>` passes)
- [ ] Video under 3 minutes, public on YouTube, no copyrighted music (`docs/demo-script.md`)
- [ ] Text description and track filled in; feedback section written from real experience
- [ ] Credits checked so the demo and Token Factory calls last through judging (`docs/credits-and-cost.md`)
