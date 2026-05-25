#!/usr/bin/env bash
# Canonical deploy script for the Hetzner production box.
#
# Sequences git pull → build → up → wait-for-ready → preflight in one chain.
# Any step that fails breaks the chain and exits non-zero, so the operator
# can't accidentally skip preflight after a build/restart.
#
# Usage (from /home/apollo/apollo_the_wise on the prod box):
#   bash scripts/deploy.sh                 # market-agent only (default)
#   bash scripts/deploy.sh both            # market-agent + orchestrator
#   bash scripts/deploy.sh orchestrator    # orchestrator only
#
# The 2026-05-13 outage happened because deploy verification was a separate
# documented step that the operator skipped. Wrapping the full sequence in
# this script makes the preflight non-bypassable from the canonical path.
set -euo pipefail

SCOPE="${1:-market-agent}"
COMPOSE_FILE="docker/docker-compose.prod.yml"

case "$SCOPE" in
  market-agent)
    SERVICES="market-agent"
    ;;
  orchestrator)
    SERVICES="orchestrator"
    ;;
  both)
    SERVICES="market-agent orchestrator"
    ;;
  *)
    echo "Unknown scope: $SCOPE (expected market-agent | orchestrator | both)"
    exit 2
    ;;
esac

echo "=== [1/5] git pull origin main ==="
git pull origin main

echo "=== [2/5] Building images: $SERVICES ==="
docker compose --env-file .env -f "$COMPOSE_FILE" build --no-cache $SERVICES

echo "=== [3/5] Restarting containers: $SERVICES ==="
docker compose --env-file .env -f "$COMPOSE_FILE" up -d $SERVICES

# Only wait for market-agent boot if it was actually restarted in step 3.
# Orchestrator-only deploys don't touch market-agent — the boot marker
# from its existing run is older than 90s and we'd time out for no reason.
if [[ "$SERVICES" == *"market-agent"* ]]; then
  echo "=== [4/5] Waiting for market-agent boot to complete ==="
  TIMEOUT=120
  ELAPSED=0
  while ! docker logs --since 90s apollo-market 2>&1 | grep -q 'Missed-outcomes schema initialized'; do
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
      echo "TIMEOUT after ${TIMEOUT}s waiting for market-agent boot. Check 'docker logs apollo-market'."
      exit 3
    fi
  done
  echo "market-agent ready (${ELAPSED}s)"
else
  echo "=== [4/5] Skipped — market-agent not in this deploy scope ==="
fi

echo "=== [5/5] Preflight smoke test ==="
if ! docker exec apollo-market python -m scripts.preflight_check; then
  echo ""
  echo "DEPLOY FAILED — preflight (safeguards) reported infra failure(s)."
  echo "The container is running but entry-pipeline safeguards can't authenticate."
  echo "DO NOT declare this deploy green. Either fix the issue and re-run, or rollback."
  exit 4
fi

echo ""
echo "=== [5b/6] Preflight DB UPDATE prepare validation ==="
if ! docker exec apollo-market python -m scripts.preflight_db_updates; then
  echo ""
  echo "DEPLOY FAILED — DB UPDATE prepare validation reported type/schema error(s)."
  echo "asyncpg can't prepare one or more trade-lifecycle UPDATEs against the"
  echo "current schema. This is the CRMD-class bug surface (2026-05-14). Fix"
  echo "before declaring green."
  exit 5
fi

echo ""
echo "=== [5c/6] Preflight column-write authority check (Gate 5 G) ==="
if ! docker exec apollo-market python -m scripts.audit_column_writes check; then
  echo ""
  echo "DEPLOY FAILED — unauthorized writer to mi_live_trades column(s)."
  echo "Some function writes a column it's not in ALLOWED_WRITERS for. This"
  echo "is the trade-state-ownership invariant (BW / KLAR / CRMD bug class)."
  echo "Either (a) add the writer to ALLOWED_WRITERS in scripts/audit_column_writes.py,"
  echo "or (b) refactor it to call the authorized writer instead."
  exit 6
fi

echo ""
echo "=== [5d/6] Preflight import-shadowing check (2026-05-20 outage class) ==="
if ! docker exec apollo-market python -m scripts.preflight_import_shadowing; then
  echo ""
  echo "DEPLOY FAILED — function-local 'from X import Y' shadows module-level import."
  echo "This is the 2026-05-20 UnboundLocalError outage class. Python makes the name"
  echo "a LOCAL variable for the entire function, so any reference BEFORE the local"
  echo "import raises UnboundLocalError at runtime. EP scans died for 1h21m this way."
  echo "Fix: remove the redundant function-local import. Module-level binding suffices."
  exit 7
fi

echo ""
echo "=== [5e/6] Preflight YAML duplicate-key check (2026-05-24 SNDK class) ==="
if ! docker exec apollo-market python -m scripts.preflight_yaml_dupe_keys; then
  echo ""
  echo "DEPLOY FAILED — data_gated_reviews.yaml has entries with duplicate top-level"
  echo "keys. YAML last-wins silently overwrites earlier values, causing reviews to"
  echo "surface in weekly digest with the wrong status (caught 2026-05-24 when"
  echo "theme_assignment_sndk_class_refinement showed up as pending despite being"
  echo "closed_on: 2026-05-18 with a full outcome block — a stray 'status: pending'"
  echo "appeared 50 lines later in the same entry)."
  echo "Fix: remove redundant key lines and re-run."
  exit 8
fi

echo ""
echo "=== [5f/6] Preflight command-parity check (2026-05-25 /breadth class) ==="
# Run on host (not inside container) because it reads channels/telegram.py +
# agent.py source files directly. Both are in the repo so host has access.
if ! python3 scripts/preflight_command_parity.py; then
  echo ""
  echo "DEPLOY FAILED — Telegram slash command registration is inconsistent."
  echo "BotCommand / CommandHandler / agent dispatch dict diverged (caught 2026-05-25"
  echo "when /breadth + 7 other commands had BotCommand + agent dispatch but no"
  echo "CommandHandler → Telegram silently dropped them all)."
  echo "Fix: align the four places per the script's output, or add an explicit"
  echo "allowlist entry in scripts/preflight_command_parity.py with a comment."
  exit 9
fi

echo ""
echo "=== DEPLOY OK — preflight passed for: $SERVICES ==="
