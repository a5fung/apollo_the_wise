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

# #154 tier-1: no silent default. A no-arg `deploy.sh` used to pick
# 'market-agent', which silently left the orchestrator on stale code when an
# orchestrator-side change (e.g. a new slash command's CommandHandler) was in
# the deploy — the 2026-05-28 /partialnow "nothing happens" gap. Force a
# conscious scope choice.
if [ $# -eq 0 ]; then
  echo "Usage: bash scripts/deploy.sh <market-agent|orchestrator|both>"
  echo "No default scope — choose explicitly to avoid leaving a service stale (#154)."
  exit 2
fi
SCOPE="$1"
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
BEFORE_PULL=$(git rev-parse HEAD)
git pull origin main
AFTER_PULL=$(git rev-parse HEAD)

# #154 tier-2: scope-drift guard. If this pull brought changes to files owned by
# a service NOT in this deploy's scope, abort — deploying anyway would leave that
# service on stale code (the 2026-05-28 /partialnow gap: orchestrator-side
# CommandHandler change arrived in a market-agent-only deploy). Ownership is
# coarse and biased safe: shared/ambiguous paths require BOTH services.
if [ "$BEFORE_PULL" != "$AFTER_PULL" ]; then
  CHANGED=$(git diff --name-only "$BEFORE_PULL".."$AFTER_PULL")
  NEED_ORCH=0; NEED_MARKET=0
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    case "$f" in
      channels/*|core/*|main.py)              NEED_ORCH=1 ;;
      agents/market_intelligence/*|scripts/*) NEED_MARKET=1 ;;
      tests/*|docs/*|*.md|.apollo_open_tasks.json) ;;  # #221 deploy-irrelevant: docs/tests/governance/SoT — present in the image but never executed, so they require no redeploy
      *)                                      NEED_ORCH=1; NEED_MARKET=1 ;;  # shared/, docker/, requirements/, … → both
    esac
  done <<< "$CHANGED"
  MISSING=""
  if [ "$NEED_ORCH" = 1 ] && [[ "$SERVICES" != *orchestrator* ]]; then MISSING="orchestrator"; fi
  if [ "$NEED_MARKET" = 1 ] && [[ "$SERVICES" != *market-agent* ]]; then MISSING="${MISSING:+$MISSING }market-agent"; fi
  if [ -n "$MISSING" ]; then
    echo ""
    echo "DEPLOY ABORTED — this pull changed files owned by: $MISSING"
    echo "but scope '$SCOPE' excludes them. Deploying would leave that service on"
    echo "stale code (the 2026-05-28 /partialnow silent gap). Changed files:"
    echo "$CHANGED" | sed 's/^/  /'
    echo "Re-run with a scope that covers it, e.g.: bash scripts/deploy.sh both"
    exit 11
  fi
fi

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
  # Wait for the LATE boot marker (scheduler started = app fully booted), NOT
  # the early 'Missed-outcomes schema initialized' (fires ~2s in, while the
  # heavy agent imports + dual-account Alpaca init are still running). Preflight
  # G6 does a full second import of the agent stack + Alpaca bootstrap; running
  # it mid-boot on the small box races/OOM-kills the exec (zero output, false
  # red — 2026-06-05). Gating on true boot-complete makes preflight reliable.
  while ! docker logs --since 90s apollo-market 2>&1 | grep -q 'Market Intelligence scheduler started'; do
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
      echo "TIMEOUT after ${TIMEOUT}s waiting for market-agent boot. Check 'docker logs apollo-market'."
      exit 3
    fi
  done
  # Extra settle: the dual-account Alpaca clients finish initializing AFTER the
  # scheduler-started marker, and preflight (safeguard walk at [5/5], G6 at [5g])
  # authenticates against them. Running preflight before Alpaca-ready is the
  # 2026-06-05 false-red ("safeguards can't authenticate" / G6 zero-output).
  # 12s comfortably clears Alpaca init on the small box (boot is ~7-10s total).
  sleep 12
  echo "market-agent ready (${ELAPSED}s + 12s settle)"
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
echo "=== [5b/7] Preflight DB UPDATE prepare validation ==="
if ! docker exec apollo-market python -m scripts.preflight_db_updates; then
  echo ""
  echo "DEPLOY FAILED — DB UPDATE prepare validation reported type/schema error(s)."
  echo "asyncpg can't prepare one or more trade-lifecycle UPDATEs against the"
  echo "current schema. This is the CRMD-class bug surface (2026-05-14). Fix"
  echo "before declaring green."
  exit 5
fi

echo ""
echo "=== [5c/7] Preflight column-write authority check (Gate 5 G) ==="
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
echo "=== [5d/7] Preflight import-shadowing check (2026-05-20 outage class) ==="
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
echo "=== [5e/7] Preflight YAML duplicate-key check (2026-05-24 SNDK class) ==="
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
echo "=== [5f/7] Preflight command-parity check (2026-05-25 /breadth class) ==="
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
echo "=== [5g/7] Preflight G6 — paper-Alpaca replace_order integration smoke ==="
# Catches the bug classes from 2026-05-27 (cancel→new race) + 2026-05-28
# (str→numeric Pydantic). Both shipped to source without ever exercising the
# production code path against the real broker. Each fired the next day at
# 16:45 ET cron on the actual IBM trade. G6 fires the same path against a
# synthetic test order on every deploy — non-bypassable.
#
# Only runs when SCOPE includes market-agent (the container that holds the
# alpaca-py request constructors + paper credentials). Orchestrator-only
# deploys skip — no relevant code surface changed.
if [[ "$SERVICES" == *"market-agent"* ]]; then
  if ! docker exec apollo-market python -m scripts.preflight_replace_order_smoke; then
    echo ""
    echo "DEPLOY FAILED — paper-Alpaca replace_order integration smoke failed."
    echo "This is the IBM 2026-05-27 / 2026-05-28 bug class — replace_order"
    echo "code path is broken in a way that mocked unit tests don't catch."
    echo "Fix the production replace_order path before deploying, or the next"
    echo "scheduled partial-exit cron will fail silently against a real trade."
    exit 10
  fi
else
  echo "=== [5g/7] Skipped — market-agent not in this deploy scope ==="
fi

echo ""
echo "=== [5h/7] Preflight datetime-hygiene check (LMT / naive-UTC bug class) ==="
# Run on host (reads source files directly via stdlib ast — no container needed,
# applies to both scopes). Bans the timezone footguns that recurred for weeks:
# pytz-as-tzinfo (silently applies the LMT -04:56 offset, shifting the ORB window
# +56 min — #180/#183 2026-06-05), naive datetime.now() (container UTC clock), and
# bare .astimezone() (system-local). With pytz gone, ZoneInfo makes every
# tzinfo=_ET construction correct, so the class cannot recur.
if ! python3 scripts/preflight_datetime_hygiene.py; then
  echo ""
  echo "DEPLOY FAILED — a timezone footgun (LMT / naive-UTC class) was introduced."
  echo "These silently produce WRONG wall-clock times. Fix per the script output,"
  echo "or annotate a reviewed exception with '# tz-ok: <reason>' on the line."
  exit 12
fi

echo ""
echo "=== DEPLOY OK — preflight passed for: $SERVICES ==="
