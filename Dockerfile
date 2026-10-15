# The Green Computer: one container serving the API and the web UI on port 8000.
#
# STATUS: written but never built (no Docker was available on the machine this was developed on).
# The steps it performs were checked by hand: a clean virtualenv install of backend/ imports and
# serves, and the frontend builds with the output redirected as below.
#
#   docker build -t green-computer .
#   docker run --rm -p 8000:8000 --env-file .env green-computer
#
# Public demo: add  -e GC_PUBLIC_DEMO=1  (turns off billed actions, adds rate limits).

# ---- 1. build the web UI -----------------------------------------------------------------
FROM node:20-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# The Vite config writes into ../backend/app/static; redirect to a plain folder for the copy below.
RUN npx tsc --noEmit && npx vite build --outDir /ui-dist --emptyOutDir

# ---- 2. the application ------------------------------------------------------------------
FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GC_DB_URL=sqlite:////data/green_computer.db
WORKDIR /srv
COPY backend/pyproject.toml ./backend/pyproject.toml
COPY backend/app ./backend/app
# Editable install keeps the source tree in place, so the UI can be dropped into app/static.
RUN pip install -e ./backend
COPY --from=ui /ui-dist ./backend/app/static
# bench/ holds the scripts injected into Nebius GPU jobs.
COPY bench ./bench
RUN useradd --system --create-home --uid 10001 gc && mkdir -p /data && chown gc /data
USER gc
WORKDIR /srv/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"
# One worker on purpose: SQLite and the in-memory rate limiter are per-process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
