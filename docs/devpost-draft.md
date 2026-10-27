# Devpost submission draft

Edit the bracketed parts after you have run the live checks. Do not claim anything this project has not verified. **Deadline: Friday 30 October 2026, 10:00 am Pacific.** Save drafts on Devpost early; you cannot change the submission after the period ends.

**Project name:** The Green Computer
**Tagline:** Predict. Optimise. Verify. Make every computation count.
**Track:** Best Apps and Agents
**Demo URL:** [DEMO URL]  **Code:** https://github.com/tsharan17/The-Green-Computer (must be public, Apache-2.0 shown in the About section)
**Video:** [YouTube link, public, under 3 minutes]

## Inspiration

Engineers who put AI on robots and edge devices find out late that the model overheats, throttles, blows the power budget or sits on the wrong board. Fixing it means weeks of trial and error across the model, the software, the hardware and sometimes the chip.

## What it does

The Green Computer predicts how an AI model will behave on a given hardware setup before anything is built, and walks you through it in one numbered path.

1. **Analysis of today's setup**: a plain verdict, what limits it, the numbers against your limits, and figures for the board heat map, the warm-up, where the energy goes and power over a batch. Nothing is recommended yet.
2. **Recommendation engine**: changes to the AI model (quantise, prune, smaller input, a lighter model), how you run it (batching, power mode, clocks), the hardware you choose (another board, better cooling) and the chip or board design (what-ifs, labelled directional). **Click any change and the whole analysis re-runs with it**: new verdict, what moved, and the figures side by side with today.
3. **Plan, compare, measure, export**: combine changes, compare each alone and together, save immutable plan versions, run the model for real on a CPU and compare predicted with measured, then export a report and a recipe of scripts.

Hard requirements (power, accuracy, latency) are never relaxed. Every number carries its range and its source, and predictions are never presented as measurements.

## How we built it

- A deterministic engine: per-layer roofline performance, a coupled power, temperature, leakage and thermal-throttling solve, uncertainty carried by re-solving at optimistic and pessimistic corners, five-state constraint certification, a search of thousands of configurations, effort-aware repair, hardware what-ifs.
- **NVIDIA Nemotron on Nebius Token Factory** (runtime calls to the Token Factory inference API) in three places: the **Green Agent**, which plans and answers by calling the engine as tools and never computes a number (a guardrail rejects any figure not in a tool result, and it cannot change the user's requirements); **AI candidates**, extra suggestions returned as schema-checked JSON that are labelled "not evaluated" until the engine evaluates them; and **datasheet extraction** for hardware that is not in the library.
- **Tavily** finds datasheet pages for unknown hardware; Nemotron extracts the values; a person must confirm them.
- **Nebius Serverless Jobs on NVIDIA GPUs** for real benchmarks that feed calibration, launched through the Nebius CLI. [Say "built, not yet run live" unless you ran it.]
- FastAPI, SQLite or PostgreSQL, React and TypeScript; one container.

**How it was built during the submission period:** the repository was started on 13 October 2026, after the period opened on 26 August, so it is a new project. [Optionally add a line on how you worked.]

## Challenges

- Keeping an LLM from ever being the source of a number.
- Modelling heat and throttling inside the search instead of after it.
- Being honest about uncertainty when the only real measurements available were on a CPU.
- Getting dependable structured output from a hosted reasoning model: our first live runs returned JSON with a missing comma, and then no answer at all (see the feedback section). We added a local repair, one retry that quotes the error back, and a larger answer budget.

## Accomplishments we are proud of

The guardrail and the read-only requirements; one numbered path where each step shows the analysis it depends on; validating the model graph parser against published ResNet-50 and MobileNetV2 parameter and FLOP counts; calibration that rejects itself when it does not help (on real runs it cut held-out error from 130% to 16%); automated tests: a backend suite and 15 browser journeys with accessibility checks.

## What we learned

[Write 2 to 4 sentences of your own. Candidates that are true of this project: a language model is best kept as the explainer while a deterministic engine owns the numbers; hosted models need output validation, a repair step and a retry, not trust; a reasoning model needs a token budget that covers its thinking as well as the answer.]

## What is not done (please be straight with judges)

- No Jetson, GPU or power measurement yet: Jetson numbers are predictions.
- **Verified live:** the Green Agent answered through Token Factory (27 October 2026). [Add the model id it used.]
- **AI candidates:** the first two live attempts failed and we fixed it (see feedback). [Update: re-tested on <date>, it worked / still fails because ...]
- **Not run live:** datasheet import with Tavily, and Nebius Serverless Jobs and Endpoints. [Update if you run them.]
- Generated recipes are syntax-checked only; the chip-design what-ifs are directional.
- The Docker image and compose stack are written but not built. [Update when the demo is deployed.]

## Built with

Nebius Token Factory, NVIDIA Nemotron, Python, FastAPI, SQLAlchemy, NumPy, ONNX, ONNX Runtime, React, TypeScript, Vite, Playwright. Integrated but not yet run live: Tavily, Nebius Serverless Jobs and Endpoints. [Move them into the main list only when you have run them.]

## Feedback on Token Factory, AI Cloud and NVIDIA tools (required; also enters the Most Valuable Feedback award)

Things we actually hit, calling Nemotron on Token Factory from a FastAPI app (27 October 2026):

1. **Structured output was unreliable.** Asked for "one JSON object only", a Nemotron model returned JSON with a missing comma between array items (the parser failed at line 25, column 6). Models that follow a schema every time would remove a whole class of repair code. Useful for builders: documentation on whether Token Factory supports a JSON mode or schema-constrained output (`response_format`) for each Nemotron model.
2. **A reply with no answer at all.** Our next attempt returned no JSON object. We believe the model spent its whole `max_tokens` budget (1,400) on reasoning before writing any answer, but we could not confirm it from the response, because the app was not recording `finish_reason` at the time. What would help: say clearly in the docs which Nemotron models reason before answering, whether reasoning tokens count against `max_tokens`, and how to cap or turn off reasoning. Returning the reasoning separately from `content`, and always returning `finish_reason`, makes this easy to detect; we now record `finish_reason` and give the model more room when it is `length`.
3. **Model ids.** The only ids we could find were in third-party catalogues, so we do not trust them: the app lists the provider's `/models` at run time and matches Nemotron models by name, falling back gracefully. A stable, documented alias per Nemotron tier (Ultra, Super, Nano) would let apps avoid that.
4. [Tool calling: did it work on each Nemotron model you tried? Did it ever return malformed arguments? Note which model.]
5. [Latency and rate limits you saw, and what a typical agent turn cost against your credits.]
6. [Builder Program and console: anything confusing about creating keys, finding models, credits or billing.]
7. [Nebius AI Cloud (Serverless Jobs and Endpoints): only write feedback if you ran them. If you did not, say so.]

NVIDIA models and tools: [anything about Nemotron quality, speed or licensing you want to say. Delete this line if you have nothing].

## Testing instructions (for the Devpost form)

Open [DEMO URL], create a free account (no email confirmation needed), open the example project and press **Analyse**, then follow the numbered path: Analysis, Try changes, Plan, Export. The **Ask the assistant** button uses Nemotron on Token Factory and is rate limited. Datasheet search and GPU benchmark launching are switched off in the public demo because they spend credits; see `docs/for-judges.md`. [Add a ready test account here if you create one.]

## Submission checklist

- [ ] Eligibility confirmed (country and age rules in the Official Rules); one Representative named if you are a team
- [ ] Devpost registered; Nebius Builder Program joined (one account per verified email)
- [ ] Decide on a provisional patent **before** the repo goes public (the repo must be public and open source)
- [ ] Repo **public** (it returned "Not Found" to an anonymous request on 27 October, which means private); `LICENSE` (Apache-2.0) visible in the About section; no keys, `.env`, `green_computer.db` or `gc_data/` committed (checked: none tracked)
- [ ] All local changes committed and pushed
- [ ] README: setup, architecture, where Nemotron, Token Factory and Nebius are used, honest status table (updated 27 October)
- [ ] Fresh-clone test: clone into a new folder and run `scripts/dev.ps1` or `scripts/dev.sh`
- [ ] Demo URL works (create an account, no email step) and stays up until 15 December (`scripts/acceptance.py <url>` passes); built with `GC_PUBLIC_DEMO=1`
- [ ] Live checks run: `scripts/check_nebius.py`, AI candidates re-tested, datasheet import run once with the Tavily key (needed for the Best Use of Tavily bonus)
- [ ] Video under 3 minutes, public on YouTube, no copyrighted music or third-party logos (`docs/demo-script.md`)
- [ ] Text description, track and feedback sections filled in from real experience (no bracketed text left)
- [ ] Credits checked so the demo and Token Factory calls last through judging (`docs/credits-and-cost.md`)
- [ ] Submit with time to spare, before 10:00 am Pacific on 30 October 2026
