#!/usr/bin/env bash
# Apollo STAGING deploy (#256 W3) — on-demand pre-prod mirror on the prod box.
#
# Dispatched from `deploy.sh staging`. Self-contained: it does NOT share prod's
# scope-drift guard or the 10-gate TRADING preflight chain (staging runs with
# LIVE_TRADING_ENABLED=false, so the trading preflights don't apply). Instead it
# validates what staging EXISTS to validate: build · boot · role partition · the
# HTTP execution transport · a prod-restored DB. The operator runs the Telegram
# smoke (/status, /trades against the staging bot) afterward.
#
# HARD RULE (advisor 2026-06-13): ON-DEMAND. Bring up → verify → smoke → DOWN.
# Never leave staging running across Monday's live-ORB gate — a 24/7 second stack
# risks the HOST OOM killer evicting a PROD container. This script gates the `up`
# on a free-memory check so it can't quietly start under prod when RAM is tight.
set -euo pipefail

cd "$(dirname "$0")/.."   # repo root

COMPOSE_FILE="docker/docker-compose.staging.yml"
ENV_FILE=".env.staging"
PROJECT="apollo-staging"
DC=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p "$PROJECT")
APP_SERVICES=(orchestrator market-agent apollo-execution)
PREFLIGHT_CONTAINER="apollo-staging-execution"
INTEL_CONTAINER="apollo-staging-market"
MIN_FREE_MB="${STAGING_MIN_FREE_MB:-1800}"   # ~1.4G actual stack + headroom
FORCE="${1:-}"

echo "=== Apollo STAGING deploy (project: $PROJECT) ==="

# ── Preconditions ─────────────────────────────────────────────────────────────
[ -r "$ENV_FILE" ] || { echo "FATAL: $ENV_FILE missing. Create it (cp .env .env.staging + swap TELEGRAM_BOT_TOKEN)."; exit 2; }
if [ "$(grep -c '^TELEGRAM_BOT_TOKEN=.\+' "$ENV_FILE" 2>/dev/null || echo 0)" -eq 0 ]; then
  echo "FATAL: $ENV_FILE has no TELEGRAM_BOT_TOKEN — staging bot smoke can't run."; exit 2
fi

# ── Free-memory gate (advisor: prod must never be OOM-evicted by staging) ──────
AVAIL_MB=$(free -m 2>/dev/null | awk '/^Mem:/{print $7}')
echo "Host available memory: ${AVAIL_MB:-unknown} MB (need ≥ ${MIN_FREE_MB} MB)"
if [ -z "$AVAIL_MB" ]; then
  echo "WARN: couldn't read 'free -m' available column — proceed only if you know the box has headroom."
elif [ "$AVAIL_MB" -lt "$MIN_FREE_MB" ]; then
  if [ "$FORCE" = "--force" ]; then
    echo "WARN: only ${AVAIL_MB} MB free (< ${MIN_FREE_MB}) — proceeding anyway (--force). Watch prod containers."
  else
    echo "ABORTED: only ${AVAIL_MB} MB free (< ${MIN_FREE_MB}). A staging stack here could OOM-evict a PROD"
    echo "container. Free memory first, or re-run 'bash scripts/deploy_staging.sh --force' if you've measured headroom."
    exit 3
  fi
fi

# ── Build images (staging project) ────────────────────────────────────────────
echo "=== [1/5] Building staging images: ${APP_SERVICES[*]} ==="
"${DC[@]}" build --no-cache "${APP_SERVICES[@]}"

# ── Infra up first, then SEED, then app (seed needs postgres, app needs data) ──
echo "=== [2/5] Up staging postgres + redis ==="
"${DC[@]}" up -d postgres redis
echo "Waiting for staging postgres (pg_isready, 120s)…"
elapsed=0
until docker exec apollo-staging-postgres pg_isready -U apollo >/dev/null 2>&1; do
  sleep 3; elapsed=$((elapsed + 3))
  [ "$elapsed" -ge 120 ] && { echo "TIMEOUT: staging postgres not ready in 120s."; exit 4; }
done
echo "Staging postgres ready (${elapsed}s)."

echo "=== [3/5] Seed staging DB from latest prod dump ==="
bash scripts/staging_seed.sh   # label-guarded; only ever targets apollo-staging-postgres

echo "=== [4/5] Up staging app services: ${APP_SERVICES[*]} ==="
"${DC[@]}" up -d "${APP_SERVICES[@]}"
echo "Waiting for both split roles to finish boot (scheduler started)…"
for c in "$PREFLIGHT_CONTAINER" "$INTEL_CONTAINER"; do
  elapsed=0
  while ! docker logs --since 120s "$c" 2>&1 | grep -q 'Market Intelligence scheduler started'; do
    sleep 2; elapsed=$((elapsed + 2))
    [ "$elapsed" -ge 150 ] && { echo "TIMEOUT: $c did not reach 'scheduler started' in 150s. Check 'docker logs $c'."; exit 5; }
  done
  echo "  $c booted (${elapsed}s)."
done
sleep 8   # let dual-account clients / routes finish

# ── Verify the DEPLOY MECHANICS staging exists to prove ────────────────────────
echo "=== [5/5] Staging verification (roles · partition · HTTP transport) ==="
echo "--- roles ---"
docker logs --since 3m "$PREFLIGHT_CONTAINER" 2>&1 | grep -E 'Service role|Execution routes registered' | head -3 || true
docker logs --since 3m "$INTEL_CONTAINER"     2>&1 | grep -E 'Service role|Job partition' | head -3 || true

echo "--- HTTP transport round-trip (intelligence -> execution over http) ---"
docker exec -i "$INTEL_CONTAINER" python - <<'PYEOF'
import asyncio
from agents.market_intelligence import execution_client as ec
r = asyncio.run(ec.get_all_positions())
assert isinstance(r, list), f"expected list, got {type(r).__name__} (ExecutionUnreachable would raise)"
print(f"  OK get_all_positions -> list len={len(r)} (transport live, not ExecutionUnreachable)")
PYEOF

echo "--- fresh-boot error scan ---"
me=$(docker logs --since 3m "$INTEL_CONTAINER"     2>&1 | grep -icE 'ExecutionUnreachable|Traceback|CRITICAL' || true)
ee=$(docker logs --since 3m "$PREFLIGHT_CONTAINER" 2>&1 | grep -icE 'Traceback|CRITICAL' || true)
echo "  intelligence errors=$me  execution errors=$ee"
[ "${me:-0}" -eq 0 ] && [ "${ee:-0}" -eq 0 ] || { echo "RED: errors in fresh boot — inspect before trusting staging."; exit 6; }

cat <<EOF

=== STAGING UP — deploy mechanics verified ===
Operator smoke (against the STAGING bot, not prod Apollo):
  • /status     — staging bot replies; equity reads via http transport
  • /trades     — positions + P&L return (or 'couldn't reach execution' = the fail-loud path, never a silent flat)

⚠ TEAR DOWN WHEN DONE — do NOT leave staging running over Monday's live-ORB gate:
    docker compose --env-file $ENV_FILE -f $COMPOSE_FILE -p $PROJECT down

(Add '-v' to also drop the staging DB volume for a fully fresh next cycle.)
EOF
