# Product launch plan

Goal: turn this repository into The Green Computer as a public product, launched on free hosting,
as a web app plus an installable app, in two working days. No API keys, no Nebius, no LLM providers:
the product is the offline engine, the digital twin and the workspace around them.

The NVIDIA/Nebius submission lives in a separate repository
(`The Green Computer Nebius Nvidia`, remote `tsharan17/The-Green-Computer-Nebius-Nvidia`) and its
Cloud Run + Neon deployment. Nothing in this plan reads, builds or deploys from it. This repository
(`tsharan17/The-Green-Computer`) gets its own hosting accounts, database, secrets and domain.

## Where we start

Already built and tested here (see `IMPLEMENTATION_STATUS.md`), so it is not launch work:
accounts and sessions, workspaces and tenant isolation, email confirmation, optional two-step
sign-in, shared rate limiter on PostgreSQL, retention and workspace export, account deletion,
readiness and metrics endpoints, Sentry adapter, security headers, public-demo guard
(`GC_PUBLIC_DEMO`), legal page scaffolding, Dockerfile, CI (tests, lint, e2e, acceptance, audits).

What blocks a launch:

| Gap | Why it matters on free hosting |
|---|---|
| Nebius, Token Factory, Tavily and the Green Agent are wired through backend and UI | The product must not depend on, or mention, API keys or providers |
| Uploaded files live on local disk (`LocalBlobStore`) | Free web services have an ephemeral disk: every restart or deploy loses uploads |
| `server.key` and `agent_signing.key` are created in the data directory | On an ephemeral disk they rotate on restart, which breaks sealed two-step secrets and paired devices |
| Local execution (ONNX Runtime timed runs, INT8 conversion) runs in the web process | A free instance has about 512 MB RAM and a fraction of a CPU; strangers' runs would starve or kill it |
| Memory footprint unknown (numpy, onnx, onnxruntime, matplotlib, seaborn at import) | Must stay well under 512 MB at idle and under load |
| No landing page; the app opens straight into sign-in | Visitors need to see what it is and try it before signing up |
| Docs, README and legal pages are written for judges and the hackathon | A product needs product wording, terms and privacy for a company |
| No web manifest or service worker | Needed for "install the app" on desktop and phone |
| Docker image never built | First build must be a smoke test before launch day |

## Hosting: free stack

| Piece | Service (free tier) | Notes |
|---|---|---|
| App: API + built UI, one container | Render, free web service (Docker) | Sleeps after 15 idle minutes; about 750 free hours a month (one always-on service). No persistent disk, no background workers on free |
| Database | Neon, new free project on a separate account from the submission | PostgreSQL; does not expire like Render's free database |
| Uploaded files | Cloudflare R2, free tier (10 GB, S3 API, no egress fees) | Needs an S3-compatible `BlobStore` (new code, below) |
| DNS, CDN, TLS at the edge, bot rules | Cloudflare free | Needs a domain (the only real cost, about $10 a year). Without one, launch on `*.onrender.com` |
| Email: confirmation, reset | Resend free tier over SMTP | The existing `GC_SMTP_*` settings work as they are; add SPF/DKIM records in Cloudflare |
| Error tracking | Sentry free tier | `GC_ERROR_REPORTER=sentry`, adapter already exists |
| Keep-awake and uptime alerts | UptimeRobot free, `/api/v1/ready` every 5 minutes | Avoids 30-60 s cold starts |
| CI and nightly backups | GitHub Actions | Scheduled `pg_dump` of Neon to R2 |

Free tiers change; confirm each limit on the provider's pricing page while setting up.

Fallbacks, if the 512 MB instance is too small after measuring:
Oracle Cloud Always Free (ARM VM, never sleeps, you run it) or Hugging Face Spaces (Docker, more
memory, sleeps when idle).

## Web and app

One codebase, three ways in:

1. **Web app** (launch): responsive React UI at the product domain.
2. **Installable PWA** (launch): manifest, icons, a service worker that caches only the app shell
   (never API responses), install button. Works on desktop and phone without an app store.
3. **Desktop app, fully offline** (after launch): Tauri shell with the Python engine bundled as a
   sidecar (PyInstaller). Runs local execution on the user's own machine, uses no hosting, and
   keeps model details on the user's computer. This is where heavy runs belong.
4. **Store apps** (later, if asked for): Capacitor wrapper, mainly for opening shared reports.

## Work, in order

### 1. Product edition: remove providers (day 1, morning) (done 2026-10-30)

The top-level `agent/` folder is the remote device agent (no provider) and stays. Uploaded PDF
datasheets now go through the offline scan (`engine/datasheet_profile.extraction_from_scan`) instead
of the language model. The two Nebius-named GPU profiles were renamed `nvidia-l40s` and
`nvidia-h100-sxm`.

Delete, not hide, so the product has nothing that asks for a key:
- Backend: `app/agent/`, `app/integrations/` (Nebius jobs, Tavily), `api/v1/agent.py`, Nebius and
  Token Factory paths in `providers/ai.py`, `providers/execution.py`, `services/benchmark_service.py`,
  `execution_service.py`, `capabilities.py`, `guide_service.py`, `hardware_service.py`,
  `api/v1/files.py`, `hardware.py`, `measurements.py`, `config.py` (`LLMSettings`), `security.py`
  wording. Keep the offline datasheet scan (`engine/datasheet_scan.py`): it needs no network.
- Frontend: `AgentPanel`, `AgentStageCard`, `AiBadge`, `NebiusJobsPanel`, the web-search half of
  `HardwareImportCard`, Nebius items in `VerifyPanel` and `RecommendationCatalogue`.
- Repo: `deploy/` (Cloud Run), `scripts/check_nebius.py`,
  `scripts/fake_token_factory.py`, `docs/connecting-nebius.md`, `for-judges.md`, `devpost-draft.md`,
  `demo-script.md`, `credits-and-cost.md`, `.gcloudignore`; provider entries in `.env.example`.
- Database: leave applied migrations alone. Unused columns stay; a new revision drops nothing yet.
- Tests that cover removed code go with it; the suite, ruff, mypy, lint and build must stay clean.

### 2. Fit free hosting (day 1, midday) (done 2026-10-30, not yet deployed)

- `R2BlobStore` (S3-compatible, `boto3` or plain signed `httpx`) implementing `BlobStore`;
  `path()` downloads to a temporary file for callers that need a file on disk. Chosen by
  `GC_BLOB_BACKEND=s3` plus `GC_S3_*` settings; local disk stays the default.
- Require `GC_SECRET_KEY` and `GC_AGENT_SIGNING_SECRET` in production (refuse to start without them
  rather than generating keys on an ephemeral disk).
- Hosted mode: local execution and INT8 conversion are switched off on the public server with a plain
  message ("runs on your machine in the desktop app"), predictions and the twin stay. Upload size cap
  (for example 50 MB) and per-account daily analysis limits on top of the existing rate limiter.
- Memory: lazy-import onnxruntime, matplotlib and seaborn; measure idle and peak RSS with the largest
  sample analysis; target under 400 MB peak.
- `render.yaml` blueprint for the free web service, health check `/api/v1/ready`, `GC_TRUST_PROXY=1`,
  `GC_ENV=production`, `GC_REQUIRE_EMAIL_VERIFICATION=1`, the Neon URL in `postgresql+psycopg://` form.
- Build the Docker image once locally or in CI and run it against a throwaway Neon branch.

### 3. Security pass (day 1, afternoon) (done 2026-10-30; live checks at go-live)

- Re-run the cross-tenant tests and add any endpoint added since; spot-check by hand on the live URL
  with two accounts.
- Confirm no secret is in the image (`.dockerignore`, `.env` never copied) or the repo history.
- Sign-up abuse: email confirmation required, sign-up rate limit, Cloudflare bot rules on
  `/api/v1/auth/*`.
- `pip-audit` and `npm audit` clean.

### 4. Launch experience (day 2, morning) (done 2026-10-31)

- Landing page at `/` (static, fast, no sign-in): what it does in one line, screenshots, how the
  numbers are made, "Try it" and "Sign up". The app moves to `/app`.
- Try without an account: a read-only example project with a finished analysis and comparison.
- Guided first run after sign-up: example model, three devices compared, results in under 2 minutes.
- "How we estimate" page: predicted vs measured, error bands, what is modelled and what is not.
- Legal: rewrite `app/legal/*.md` for the product (operator name, contact, hosting sub-processors:
  Render, Neon, Cloudflare, Resend, Sentry). Have them reviewed after launch.
- Product README, `docs/deploy.md` updated for this stack, contact and feedback link in the app.

### 5. Installable app (day 2, midday) (done 2026-11-02)

- `manifest.webmanifest`, icons (192, 512, maskable), theme colours, a service worker for the shell
  only, an "Install" button where the browser supports it.
- Pass at phone width (375 px) over landing, sign-in, workspace, results; charts scroll inside their
  card, never the page.
- Playwright: a mobile-viewport journey and axe in both colour schemes.

### 6. Go live (day 2, afternoon)

- Accounts: Render, new Neon, Cloudflare (domain, R2), Resend, Sentry, UptimeRobot.
  These are yours to create; the app needs only their environment variables.
- Deploy, run `scripts/acceptance.py https://<domain>`, then a manual run on a phone and a laptop
  with a fresh account: sign up, confirm email, analyse, compare, export, install, delete account.
- Nightly backup workflow, then one test restore into a Neon branch.
- Freeze a `v1.0.0` tag.

### After launch

Desktop app (Tauri + bundled engine), billing (Stripe) once there is demand, invitation emails,
pip-installable CLI, GitHub Action for CI comments, Vite 6 upgrade, store apps if asked for.

## Decisions needed

1. Product domain and the name on it (needed for legal pages, email sender and the manifest).
   Name decided: The Green Computer. No domain bought: launching on `the-green-computer.onrender.com`.
2. The operator named in the terms: you personally, or a company. Decided: T Sharan.
   Contact and email sender: shwethasharan.office@gmail.com (set in `render.yaml`).
3. Whether visitors may upload their own ONNX models on the free server (recommended: yes, capped at
   50 MB, analysis only, no execution).

## Done means

- No provider code, keys or mentions in the repository or the UI.
- The live site passes the acceptance script, the security pass and the manual phone and laptop runs.
- A restart or redeploy loses nothing: files in R2, keys in environment variables, data in Neon.
- `IMPLEMENTATION_STATUS.md` has a "Product launch" section with what was verified and what was not.
