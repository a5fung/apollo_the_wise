#!/usr/bin/env bash
# Canonical deploy script for the Hetzner production box.
#
# Sequences git pull → build → up → wait-for-ready → preflight in one chain.
# Any step that fails breaks the chain and exits non-zero, so the operator
# can't accidentally skip preflight after a build/restart.
#
# Usage (from /home/apollo/apollo_the_wise on the prod box):
#   bash scripts/deploy.sh market-agent    # market-agent only
#   bash scripts/deploy.sh both            # market-agent + orchestrator
#   bash scripts/deploy.sh orchestrator    # orchestrator only
#   bash scripts/deploy.sh execution       # apollo-execution (#256 W2 cutover —
#                                          # gated; see docs/ops/execution_split_cutover.md)
#   bash scripts/deploy.sh staging         # on-demand pre-prod mirror (#256 W3 —
#                                          # dispatches to scripts/deploy_staging.sh;
#                                          # its own compose project + flow)
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
  echo "Usage: bash scripts/deploy.sh <market-agent|orchestrator|both|execution|staging>"
  echo "No default scope — choose explicitly to avoid leaving a service stale (#154)."
  exit 2
fi
SCOPE="$1"

# #256 W3: staging is a wholly separate compose project + flow (its own DB seed,
# no scope-drift guard, no trading preflight chain — it runs LIVE_TRADING_ENABLED=
# false). Dispatch BEFORE any prod logic so the prod path below stays byte-identical.
if [ "$SCOPE" = "staging" ]; then
  exec bash scripts/deploy_staging.sh "${@:2}"
fi

# ── DEPLOY WINDOWS (operator 2026-08-21, HARD) ───────────────────────────────
# "we ran into too many deploy issues... set a daily deploy window, one during
# market hours and one after hours and we only deploy in those windows going
# forward unless I override."
#
# Derived from a full census of all 66 scheduled jobs in scheduler.py (ET):
#   12:00-13:00  MARKET  — the ONLY hour of the session with zero cron jobs.
#                          09:00-10:05 is the ORB/money block, 15:45 is the
#                          partial-exit scan, 16:00-16:55 holds NINETEEN jobs.
#                          Continuous per-minute position watchdogs still run
#                          here and cannot be moved (they guard open money) —
#                          a ~90s restart costs 1-2 of their cycles, which is
#                          the irreducible price of any market-hours deploy.
#   21:15-22:15  AFTER   — clear of evening_position_backstop (21:00), of the
#                          17:30-18:30 shadow/theme block (17 jobs), and of the
#                          02:00 cleanup pair.
# NOTHING was rescheduled to create these windows; they were already empty.
# Two deploys inside these windows on 2026-08-19 and 2026-08-20 each cancelled
# nightly_data_pull mid-run — both landed at ~17:02 ET, which is why this gate
# exists as code rather than as a note someone remembers.
#
# OVERRIDE (operator only): APOLLO_DEPLOY_ANYTIME=1 bash scripts/deploy.sh <scope>
if [ "${APOLLO_DEPLOY_ANYTIME:-0}" != "1" ]; then
  _now_et=$(TZ=America/New_York date +%H%M)
  _dow=$(TZ=America/New_York date +%u)   # 1=Mon .. 7=Sun
  _ok=0
  # Market window 12:00-13:00, weekdays only (no session at the weekend).
  if [ "$_dow" -le 5 ] && [ "$_now_et" -ge 1200 ] && [ "$_now_et" -lt 1300 ]; then _ok=1; fi
  # After-hours window 21:15-22:15, every day.
  if { [ "$_now_et" -ge 2115 ] && [ "$_now_et" -lt 2215 ]; }; then _ok=1; fi
  if [ "$_ok" -ne 1 ]; then
    echo "DEPLOY REFUSED — outside the operator's deploy windows (now $(TZ=America/New_York date '+%a %H:%M') ET)."
    echo "  MARKET window:  12:00-13:00 ET, Mon-Fri"
    echo "  AFTER-HOURS:    21:15-22:15 ET, daily"
    echo "Set by the operator 2026-08-21 after repeated deploys clipped scheduled jobs."
    echo "Operator override:  APOLLO_DEPLOY_ANYTIME=1 bash scripts/deploy.sh $SCOPE"
    exit 12
  fi
fi
COMPOSE_FILE="docker/docker-compose.prod.yml"
# Which container the boot-wait + trade preflights exec against, and any extra
# compose `--profile` args (#256 W2). Default = apollo-market so every existing
# scope is byte-identical; only the `execution` scope changes them.
PREFLIGHT_CONTAINER="apollo-market"
COMPOSE_PROFILE_ARGS=""

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
  execution)
    # #256 W2 cutover: the apollo-execution service (compose profile: split).
    # ONLY safe AFTER market-agent has been flipped to intelligence — starting it
    # while market-agent still runs combined = double execution. Run the trade
    # preflights against apollo-execution (the container that holds the creds +
    # entry pipeline). See docs/ops/execution_split_cutover.md.
    SERVICES="apollo-execution"
    PREFLIGHT_CONTAINER="apollo-execution"
    COMPOSE_PROFILE_ARGS="--profile split"
    ;;
  *)
    echo "Unknown scope: $SCOPE (expected market-agent | orchestrator | both | execution)"
    exit 2
    ;;
esac

# ── [0/5] Disk hygiene (2026-06-16 incident) ────────────────────────────────────
# A 46GB build cache on an 84%-full disk corrupted a --no-cache pip layer: tzlocal's
# .dist-info was written but the module dir was NOT, so `pip list` showed it installed
# yet `import tzlocal` failed → apollo-market crash-looped. Builds here are --no-cache,
# so the build cache is NEVER reused — prune it every deploy to keep it bounded, then
# HARD-GUARD against building on a near-full disk (the corruption trigger).
echo "=== [0/5] Disk hygiene: prune unused build cache + free-space guard ==="
docker builder prune -f >/dev/null 2>&1 || true
AVAIL_GB=$(df -BG / | awk 'NR==2 {gsub(/[A-Za-z]/,"",$4); print int($4)}')
echo "Root disk free after prune: ${AVAIL_GB:-?}G"
if [ "${AVAIL_GB:-0}" -lt 8 ]; then
  echo ""
  echo "DEPLOY ABORTED — only ${AVAIL_GB}G free after pruning the build cache. A --no-cache"
  echo "build on a near-full disk writes CORRUPTED layers (metadata lands but module files"
  echo "don't — the 2026-06-16 tzlocal crash). Free disk first (e.g. 'docker image prune -af',"
  echo "rotate logs), then re-deploy."
  exit 20
fi

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
  NEED_ORCH=0; NEED_MARKET=0; NEED_EXEC=0
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    case "$f" in
      channels/*|core/*|main.py)              NEED_ORCH=1 ;;
      # #324: broker/ + execution_routes RUN on apollo-execution (not the market-agent
      # image that `both` recreates). They still need NEED_MARKET (shared image build)
      # AND NEED_EXEC (recreate the running broker), else the fix lands in the image but
      # the live apollo-execution stays stale — the LZB silent-dark class.
      agents/market_intelligence/broker/*|agents/market_intelligence/execution_routes.py) NEED_MARKET=1; NEED_EXEC=1 ;;
      agents/market_intelligence/*|scripts/*)
          NEED_MARKET=1
          # #456 (2026-07-26): broker/ above is NOT the whole execution surface.
          # apollo-execution runs scheduler.py and keeps 29 EXECUTION_OWNED jobs
          # ("Job partition: role=execution — kept 29" in its boot log), and those
          # job paths import 38 modules from agents/market_intelligence — db.py,
          # regime.py, collector.py, trading_calendar.py, scheduler.py, constants.py
          # among them. All of those matched this generic arm and got NEED_MARKET
          # only, so a fix to any of them built into the shared image and left the
          # RUNNING execution container on old code. Silent-dark: no error, no
          # signal. Found while shipping the stop-ack watchdog defer, which would
          # itself have shipped dark.
          # The subset is MACHINE-DERIVED into scripts/exec_loaded_modules.txt and
          # drift-checked by preflight [5n/7] — deliberately not hand-enumerated
          # here, because a hand-synced list is the exact drift that already cost
          # us #474 (root-yaml COPY) and #260 (three ticker-extraction copies).
          if grep -Fxq "$f" scripts/exec_loaded_modules.txt 2>/dev/null; then
              NEED_EXEC=1
          fi
          ;;
      tests/*|docs/*|*.md|.apollo_open_tasks.json|.githooks/*) ;;  # #221 deploy-irrelevant: docs/tests/governance/SoT + local git hooks (.githooks run on git ops, never inside the container) — present in the image but never executed, so they require no redeploy. MUST precede the yaml arms (a tests/ fixture yaml is not deployable config).
      # The two KNOWN market-agent-only runtime yamls keep their narrow scope (the
      # 2026-07-09 incident: the catch-all dragged all 3 services into review-yaml-only
      # deploys; review 7/17 caught the generic arm below re-introducing that via
      # NEED_ORCH — data_gated_reviews.yaml changes near-every session, so the deploy
      # friction is real, not theoretical).
      data_gated_reviews.yaml|theme_ecosystems.yaml) NEED_MARKET=1 ;;
      # NESTED yamls (any subdir): keep the catch-all's FULL-scope guarantee incl.
      # NEED_EXEC — shell case `*` matches `/`, so without this arm a future shared/
      # or docker/ yaml would silently skip the execution container (the LZB
      # silent-dark class; review 7/17).
      */*.yaml)                               NEED_ORCH=1; NEED_MARKET=1; NEED_EXEC=1 ;;
      # #474 class-kill (2026-07-16): any OTHER root-level yaml (integrations.yaml +
      # future ones) is runtime config carried by BOTH images via the Dockerfiles'
      # `COPY *.yaml ./` glob — new root yamls need no hand-added COPY or case arm.
      # Deliberately NOT NEED_EXEC: no broker-read ROOT yaml exists today — if one
      # appears, add its explicit arm with NEED_EXEC.
      *.yaml)                                 NEED_ORCH=1; NEED_MARKET=1 ;;
      *)                                      NEED_ORCH=1; NEED_MARKET=1; NEED_EXEC=1 ;;  # shared/, docker/, requirements/, … → all incl execution runtime
    esac
  done <<< "$CHANGED"
  MISSING=""
  if [ "$NEED_ORCH" = 1 ] && [[ "$SERVICES" != *orchestrator* ]]; then MISSING="orchestrator"; fi
  # apollo-execution runs the SAME image as market-agent, so it covers
  # agents/market_intelligence/ changes too (#256 W2).
  if [ "$NEED_MARKET" = 1 ] && [[ "$SERVICES" != *market-agent* && "$SERVICES" != *apollo-execution* ]]; then MISSING="${MISSING:+$MISSING }market-agent"; fi
  if [ -n "$MISSING" ]; then
    echo ""
    echo "DEPLOY ABORTED — this pull changed files owned by: $MISSING"
    echo "but scope '$SCOPE' excludes them. Deploying would leave that service on"
    echo "stale code (the 2026-05-28 /partialnow silent gap). Changed files:"
    echo "$CHANGED" | sed 's/^/  /'
    echo "Re-run with a scope that covers it, e.g.: bash scripts/deploy.sh both"
    exit 11
  fi
  # #324: execution-runtime DRIFT — broker/ or execution_routes changed, but this scope
  # does NOT recreate apollo-execution and it IS running. NOT an abort (a broker fix is a
  # legit two-step: `both` builds the shared image, `deploy.sh execution` recreates the
  # running broker). A loud WARNING — re-printed at the very end so it can't be missed the
  # way the LZB fix was (DEPLOY OK printed, execution left dark). feedback_deploy_both_excludes_execution.
  EXEC_DRIFT=0
  if [ "$NEED_EXEC" = 1 ] && [[ "$SERVICES" != *apollo-execution* ]] \
     && docker ps --format '{{.Names}}' | grep -qx 'apollo-execution'; then
    EXEC_DRIFT=1
    echo ""
    echo "⚠️  EXECUTION-RUNTIME DRIFT (#324/#456): this pull changed code that RUNS on"
    echo "    apollo-execution — broker/, execution_routes, or one of the 38 modules its"
    echo "    jobs import (scripts/exec_loaded_modules.txt) — but scope '$SCOPE' does NOT"
    echo "    recreate it. After this deploy you MUST also run:"
    echo "        bash scripts/deploy.sh execution"
    echo "    (else the fix lands in the image but the LIVE execution container stays stale)."
  fi
fi

echo "=== [2/5] Building images: $SERVICES ==="
docker compose --env-file .env -f "$COMPOSE_FILE" $COMPOSE_PROFILE_ARGS build --no-cache $SERVICES

echo "=== [3/5] Restarting containers: $SERVICES ==="
docker compose --env-file .env -f "$COMPOSE_FILE" $COMPOSE_PROFILE_ARGS up -d $SERVICES

# Only wait for market-agent boot if it was actually restarted in step 3.
# Orchestrator-only deploys don't touch market-agent — the boot marker
# from its existing run is older than 90s and we'd time out for no reason.
if [[ "$SERVICES" == *"market-agent"* || "$SERVICES" == *"apollo-execution"* ]]; then
  echo "=== [4/5] Waiting for $PREFLIGHT_CONTAINER boot to complete ==="
  TIMEOUT=120
  ELAPSED=0
  # Wait for the LATE boot marker (scheduler started = app fully booted), NOT
  # the early 'Missed-outcomes schema initialized' (fires ~2s in, while the
  # heavy agent imports + dual-account Alpaca init are still running). Preflight
  # G6 does a full second import of the agent stack + Alpaca bootstrap; running
  # it mid-boot on the small box races/OOM-kills the exec (zero output, false
  # red — 2026-06-05). Gating on true boot-complete makes preflight reliable.
  # (The scheduler-started marker logs in every SERVICE_ROLE.)
  while ! docker logs --since 90s "$PREFLIGHT_CONTAINER" 2>&1 | grep -q 'Market Intelligence scheduler started'; do
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
      echo "TIMEOUT after ${TIMEOUT}s waiting for $PREFLIGHT_CONTAINER boot. Check 'docker logs $PREFLIGHT_CONTAINER'."
      exit 3
    fi
  done
  # Extra settle: the dual-account Alpaca clients finish initializing AFTER the
  # scheduler-started marker, and preflight (safeguard walk at [5/5], G6 at [5g])
  # authenticates against them. Running preflight before Alpaca-ready is the
  # 2026-06-05 false-red ("safeguards can't authenticate" / G6 zero-output).
  # 12s comfortably clears Alpaca init on the small box (boot is ~7-10s total).
  sleep 12
  echo "$PREFLIGHT_CONTAINER ready (${ELAPSED}s + 12s settle)"
else
  echo "=== [4/5] Skipped — no market-image container in this deploy scope ==="
fi

# #278: route the creds-requiring preflights (gate 5 safeguard walk + gate 5g G6) to
# the container that actually holds Alpaca creds + the entry pipeline. Post-#256 split,
# apollo-market boots creds-LESS (intelligence role), so the safeguard walk false-fails
# there ('ALPACA_PAPER_API_KEY not set') AND dies before gates 5b-5j run (it masked the
# #295 import-shadowing finding on 2026-06-16). apollo-execution holds the creds — detect
# it; fall back to PREFLIGHT_CONTAINER in combined (non-split) mode where creds co-locate.
# Caveat: `both` does NOT restart apollo-execution, so gate 5 validates the code execution
# is CURRENTLY running — redeploy execution-relevant broker code via `deploy.sh execution`.
CREDS_CONTAINER="$PREFLIGHT_CONTAINER"
if docker ps --format '{{.Names}}' | grep -qx 'apollo-execution'; then
  CREDS_CONTAINER="apollo-execution"
fi
echo "Preflight routing: code/schema gates → $PREFLIGHT_CONTAINER; creds gates (5, 5g) → $CREDS_CONTAINER"

echo "=== [5/5] Preflight smoke test ==="
if ! docker exec "$CREDS_CONTAINER" python -m scripts.preflight_check; then
  echo ""
  echo "DEPLOY FAILED — preflight (safeguards) reported infra failure(s)."
  echo "The container is running but entry-pipeline safeguards can't authenticate."
  echo "DO NOT declare this deploy green. Either fix the issue and re-run, or rollback."
  exit 4
fi

echo ""
echo "=== [5b/7] Preflight DB UPDATE prepare validation ==="
if ! docker exec "$PREFLIGHT_CONTAINER" python -m scripts.preflight_db_updates; then
  echo ""
  echo "DEPLOY FAILED — DB UPDATE prepare validation reported type/schema error(s)."
  echo "asyncpg can't prepare one or more trade-lifecycle UPDATEs against the"
  echo "current schema. This is the CRMD-class bug surface (2026-05-14). Fix"
  echo "before declaring green."
  exit 5
fi

echo ""
echo "=== [5c/7] Preflight column-write authority check (Gate 5 G) ==="
if ! docker exec "$PREFLIGHT_CONTAINER" python -m scripts.audit_column_writes check; then
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
if ! docker exec "$PREFLIGHT_CONTAINER" python -m scripts.preflight_import_shadowing; then
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
if ! docker exec "$PREFLIGHT_CONTAINER" python -m scripts.preflight_yaml_dupe_keys; then
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
if [[ "$SERVICES" == *"market-agent"* || "$SERVICES" == *"apollo-execution"* ]]; then
  if ! docker exec "$CREDS_CONTAINER" python -m scripts.preflight_replace_order_smoke; then
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
echo "=== [5i/7] Preflight model-registry check (scattered model-id drift class) ==="
# Run on host (stdlib ast, no container). Bans string-literal Claude model ids
# outside shared/llm_models.py — scattered ids DRIFT (2026-06-09: theme advisor
# still on opus-4-6 while the judge eval compared opus-4-8; stale pricing rows).
# Escape: '# model-ok: <reason>' on the line.
if ! python3 scripts/preflight_model_registry.py; then
  echo ""
  echo "DEPLOY FAILED — a string-literal model id was introduced outside the registry."
  echo "Import a ROLE constant from shared/llm_models.py instead."
  exit 13
fi

echo ""
echo "=== [5j/7] Execution-boundary check (#256 W1 — intelligence/execution seam) ==="
# Run on host (stdlib, no container). Intelligence-side code reaches broker/*
# ONLY through execution_client.py (the facade W2 swaps for HTTP). Tagged
# exceptions: '# exec-boundary-ok: <reason>' (moves-with-job (W2) etc.).
if ! python3 scripts/check_execution_boundary.py check; then
  echo ""
  echo "DEPLOY FAILED — a direct broker import crossed the execution boundary."
  echo "Route it through agents/market_intelligence/execution_client.py, or tag"
  echo "a sanctioned exception with '# exec-boundary-ok: <reason>'."
  exit 14
fi

echo ""
echo "=== [5k/7] Preflight no-silent-failures check (#381 swallow-a-failure class) ==="
# Run on host (stdlib ast, no container). RATCHET: blocks any NEW broad+silent
# except (bare/Exception with a body that neither raises nor alerts) beyond the
# tracked baseline — the FMP-403 (#380) / theme-shadow-0-rows (#173) class where a
# real failure is swallowed behind a plausible default. The ~174 legacy sites are a
# tracked, SHRINKING baseline (#381 remediation); the gate only fails on NEW ones.
# Escape genuine control-flow with '# loud-ok: <reason>'. THE RULE: fallback != silent.
if ! python3 scripts/preflight_no_silent_failures.py; then
  echo ""
  echo "DEPLOY FAILED — a NEW broad+silent except (swallowed failure) was introduced."
  echo "Surface it (raise, or failure_policy.py's @advisory_fail_open/@trade_state_fail_loud),"
  echo "or annotate genuine control-flow with '# loud-ok: <reason>'. Do NOT bury a real"
  echo "swallow via --update-baseline."
  exit 15
fi

echo ""
echo "=== [5l/7] Preflight ADR-0008 demotion fence (#225 — trade-state demotion class) ==="
# Run on host (stdlib ast, no container). Blocks any except-enclosed trade-state
# DEMOTION (stop_order_id->NULL / status->'closed' / set_stop_order_id(None))
# that lacks a reviewed '# broker-confirmed: <reason>' tag in its except block —
# ADR 0008: only a confirmed broker read/event (or the documented fail-safe
# direction) may demote trade state; a demotion inferred from a caught exception
# is the a41e7c6a phantom-close class. Residuals reviewed + tagged 2026-07-05.
if ! python3 scripts/audit_trade_state_demotions.py check; then
  echo ""
  echo "DEPLOY FAILED — an except-enclosed trade-state demotion lacks a '# broker-confirmed:' tag."
  echo "Either confirm the demoted state with a real broker read/event and tag the block,"
  echo "or remove the demotion. Do NOT tag without actually verifying (ADR 0008)."
  exit 16
fi

if [[ "$SERVICES" == *market-agent* ]]; then
  echo "=== [5m/7] Preflight judge-eval regression gate (ADR 0030 — grade-surface drift class) ==="
  # Run on host (stdlib ast, no container — the [5l/7] pattern). FAILS the deploy iff the
  # grade surface (judge rubric text/version, catalyst-grader prompt version, JUDGE_MODEL,
  # or the eval corpus content) changed since the last PASSING robustness-eval record —
  # so no prompt edit / model swap / corpus change ever ships ungraded. The rubric hash is
  # recomputed from _RUBRIC's text: accidental edits trip it too. Operator-signed `waiver`
  # in the record is the emergency valve (printed loudly). Market-agent scopes only (the
  # judge runs there); orchestrator-only deploys don't re-gate. Hard-FAIL from day one
  # (operator F3, sitting 2026-07-12).
  if ! python3 scripts/preflight_judge_eval_gate.py; then
    echo ""
    echo "DEPLOY FAILED — the grade surface changed since the last passing judge-robustness eval."
    echo "Re-run scripts/evals/run_judge_robustness_eval.py (on prod) to green, regenerate the"
    echo "pass record from its RESULTS_JSON, and re-deploy. Do NOT hand-edit the record (ADR 0030)."
    exit 17
  fi
  # #547 — separate ENVELOPE signal (max_tokens/timeout/tool_choice/fail-open rules). Never
  # blocks the deploy and never touches the eval-rerun trigger above (operator-ruled
  # 2026-08-13: "these type of fixes shouldn't cause a rerun"). This second, cheap (<1s, no
  # network) invocation only PRINTS a JSON line when the envelope moved; the container is
  # already up at this point (post [4/5] boot wait), so relay that line into mi_audit_log via
  # the in-container companion script — `|| true` on both because an audit-row write must
  # never fail a deploy, matching log_audit_event()'s own never-raises contract.
  ENVELOPE_AUDIT=$(python3 scripts/preflight_judge_eval_gate.py --envelope-audit-json || true)
  if [[ -n "$ENVELOPE_AUDIT" ]]; then
    docker exec "$PREFLIGHT_CONTAINER" python -m scripts.log_judge_envelope_change "$ENVELOPE_AUDIT" || true
  fi
fi

echo ""
echo "=== [5n/7] Preflight execution-deploy-scope check (#456 — silent-dark-execution class) ==="
# Keeps deploy.sh's own execution routing honest. apollo-execution imports a large
# subset of agents/market_intelligence (38 modules, NOT just broker/); a change to
# any of them must recreate the running execution container or it stays stale with
# no error and no signal. scripts/exec_loaded_modules.txt is that subset, and it is
# MACHINE-DERIVED, not hand-written — this gate re-derives it by importing the
# execution entrypoint and FAILS if the container now imports something the list
# (and therefore the routing above) would miss. Under-coverage fails; over-coverage
# only warns, since a stale entry costs an extra recreate, not a dark deploy.
if ! docker exec "$PREFLIGHT_CONTAINER" python -m scripts.preflight_exec_deploy_scope; then
  echo ""
  echo "DEPLOY FAILED — apollo-execution imports modules that deploy.sh would not route"
  echo "to the execution scope, so a change to one of them would ship silent-dark there."
  echo "Regenerate the list and commit it:"
  echo "    docker exec $PREFLIGHT_CONTAINER python -m scripts.preflight_exec_deploy_scope --emit"
  exit 18
fi

echo ""
echo "=== [5o/7] Preflight account-mode-literal check (get_flag_universe 7-weeks-dark rot class) ==="
# Run on host (stdlib ast, no container — the [5h/7] pattern). A query hardcoding
# `account_mode = 'paper'` (or `phase = '...'`) is correct the day it ships and rots
# the day the strategy GRADUATES — the known case sat dark ~7 weeks after MAGNA53
# went live 2026-06-22. Every such literal in agents/ core/ channels/ shared/ must
# carry a reviewed `mode-ok: <reason>` on its line; the annotated inventory is then
# replayed by the nightly graduation sweep (health_checks) whenever a phase actually
# changes or a pinned book goes dormant — the moments no static check can see.
if ! python3 scripts/preflight_account_mode_literals.py; then
  echo ""
  echo "DEPLOY FAILED — a hardcoded account-mode/phase literal was introduced without"
  echo "a reviewed escape. Resolve the mode dynamically, drop the filter, or annotate"
  echo "a deliberate book-pin with '# mode-ok: <reason>' / '-- mode-ok: <reason>'."
  exit 19
fi

echo ""
echo "=== DEPLOY OK — preflight passed for: $SERVICES ==="
# #324: re-surface the execution-runtime drift as the LAST line — the DEPLOY OK above is
# exactly what masked the LZB silent-dark deploy. Impossible to miss here.
if [ "${EXEC_DRIFT:-0}" = 1 ]; then
  echo ""
  echo "⚠️  NOT DONE: execution-loaded code changed — apollo-execution is STILL on stale code."
  echo "    Run now:  bash scripts/deploy.sh execution   (#324/#456, feedback_deploy_both_excludes_execution)"
fi
