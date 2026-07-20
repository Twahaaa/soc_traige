#!/usr/bin/env bash
# Full-stack end-to-end runner for the SOC triage dashboard.
#
# Brings up:
#   - Redis Streams on :6379   (assumed already running as a system daemon — checked)
#   - Qdrant      on :6333   (started via Docker if down)
# Then runs Playwright, which itself starts (or reuses):
#   - FastAPI dashboard on :8000
#   - Next.js dev        on :3000
#
# Pre-existing `triage_reports` collection + reports in Qdrant are left in place;
# no synthetic data is seeded (real pipeline reports are used as fixtures).
#
# Usage:
#   backend/scripts/run_dashboard_e2e.sh
#
# Exits non-zero if any step fails. Run from repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
QDRANT_CONTAINER="${QDRANT_CONTAINER:-soc-qdrant}"

log() { printf '[e2e] %s\n' "$*" >&2; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { log "missing required binary: $1"; exit 1; }
}

require_cmd docker
require_cmd curl
require_cmd redis-cli
require_cmd npx

# 1. Redis must be reachable. Fail fast with a clear message.
if ! redis-cli ping >/dev/null 2>&1; then
  log "Redis is not reachable on :6379 — please start it first (system daemon / docker)."
  exit 1
fi
log "Redis: OK"

# 2. Redis consumer group must exist for the WS bridge to read new entries.
log "Ensuring consumer group group:dashboard on stream:triage_reports"
redis-cli XGROUP CREATE stream:triage_reports group:dashboard '$' MKSTREAM >/dev/null 2>&1 \
  || log "consumer group already exists (BUSYGROUP) — OK"

# 3. Qdrant — start a fresh container if the port isn't listening.
if ! curl -sf --max-time 2 http://localhost:6333/ >/dev/null 2>&1; then
  log "Qdrant not reachable on :6333 — starting container '${QDRANT_CONTAINER}'"
  docker rm -f "${QDRANT_CONTAINER}" >/dev/null 2>&1 || true
  mkdir -p "${REPO_ROOT}/qdrant_storage"
  docker run -d \
    --name "${QDRANT_CONTAINER}" \
    -p 6333:6333 -p 6334:6334 \
    -v "${REPO_ROOT}/qdrant_storage:/qdrant/storage" \
    qdrant/qdrant >/dev/null
  # Wait for healthy (max ~15s)
  for _ in $(seq 1 30); do
    if curl -sf --max-time 1 http://localhost:6333/ >/dev/null 2>&1; then break; fi
    sleep 0.5
  done
fi

# 4. Ensure the collection exists (re-uses one created by past pipeline runs).
log "Qdrant: OK ($(curl -s --max-time 2 http://localhost:6333/collections | head -c 200))"
if ! curl -sf --max-time 2 http://localhost:6333/collections/triage_reports >/dev/null 2>&1; then
  log "Collection triage_reports not found — please run the pipeline once to seed real reports"
  log "(e.g. uv run python backend/scripts/e2e_full_pipeline.py). Falling back to empty collection."
fi

# 5. Run Playwright. It will start FastAPI (:8000) and Next dev (:3000) via
#    playwright.config.ts `webServer` entries (reuseExistingServer=true).
log "Running Playwright E2E suite"
cd "${REPO_ROOT}/frontend"
if [ -d "node_modules/playwright-core" ]; then
  npx playwright install chromium >/dev/null 2>&1 || log "playwright install skipped (offline?)"
fi
npx playwright test --project=chromium "$@"
RC=$?
log "Playwright exit code: ${RC}"
exit ${RC}