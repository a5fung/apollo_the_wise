#!/usr/bin/env bash
# service_watchdog.sh — per-service liveness watchdog (#256 W4, 2026-07-05)
# + disk-space check (#422, 2026-07-06).
#
# Operator-picked over configuring uptime-kuma (which sat EMPTY for 3 months —
# UI-config drifts; a versioned script doesn't). Host cron every 5 min:
# checks each core container's docker state (running + healthy when a
# healthcheck exists) plus an independent HTTP probe on the orchestrator's
# host-mapped port. Alerts on the DOWN transition, re-alerts every 6h while
# still down, sends a RECOVERED note on the way back up. Success = silent.
#
# Also checks `/` disk usage (#422 — an unbounded disk was the #1 identified
# silent-infra-death risk from the #418 productization sweep): alerts >=85%,
# and at >=90% additionally runs SAFE prunes only (builder cache + dangling
# images) — never `docker system prune --volumes`, which would risk deleting
# a volume that reads as "unused" only because its container happens to be
# down (e.g. postgres_data). Same transition/dedup/recover file mechanics as
# the service checks, one shared state file (disk.high) instead of per-service.
#
# Telemetry: Telegram (dynamic text FENCED — the 2026-07-05 restore-check
# lesson: raw underscores 400 the legacy-Markdown API and '|| true' eats it)
# + best-effort mi_audit_log rows (service_down / service_recovered /
# disk_space_high / disk_space_prune_run / disk_space_recovered /
# watchdog_heartbeat). Dedup state lives in FILES, deliberately NOT the DB —
# the watchdog must keep working when postgres is the thing that's down.
#
# Two-tier confirmation for the service-down check (#532, 2026-08-06): see
# the comment above check_service() for the measurement that justifies it.
# Hard-down states alert on tick 1, unchanged. Soft (ambiguous / likely
# mid-deploy) states need 2 consecutive failing ticks (~5 min) before they
# promote to a real DOWN alert — tracked in a per-service "$svc.pending"
# file alongside the existing "$svc.down" alert-state file.
#
# Known blind spot (accepted): runs on the same host it watches — whole-host
# death needs an external pinger (filed as a follow-up).

set -uo pipefail  # not -e: every failure routes through explicit handling

# APP_DIR/STATE_DIR/LOG_FILE overrides are test hooks (same pattern as the
# pre-existing WATCHDOG_SERVICES_OVERRIDE below) — added for
# tests/test_service_watchdog_532.py, which runs this script for real
# against a temp STATE_DIR/LOG_FILE and a fake `docker` on PATH instead of
# the production host paths. Defaults are unchanged production values, so
# behaviour is identical to before when nothing overrides them.
APP_DIR=${WATCHDOG_APP_DIR_OVERRIDE:-/home/apollo/apollo_the_wise}
ENV_FILE=$APP_DIR/.env
STATE_DIR=${WATCHDOG_STATE_DIR_OVERRIDE:-/home/apollo/backups/watchdog_state}
LOG_FILE=${WATCHDOG_LOG_FILE_OVERRIDE:-/home/apollo/backups/watchdog.log}
REALERT_SECS=$((6 * 3600))

# Space-separated container list; override for testing only.
SERVICES=${WATCHDOG_SERVICES_OVERRIDE:-"apollo-orchestrator apollo-market apollo-execution apollo-postgres apollo-redis"}

mkdir -p "$STATE_DIR"

# Run-lock (d3 review): without it, a hung run + the next */5 tick both see the
# missing state file and double-fire the DOWN alert. Overlap = silent no-op.
exec 9>"$STATE_DIR/.lock"
flock -n 9 || exit 0

if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

# Shared telemetry helpers (log / telegram_alert / audit_event) — one canonical
# copy; the per-script copies drifted within a day (d3 /simplify). Sourced via
# $APP_DIR (not a hardcoded literal) so the WATCHDOG_APP_DIR_OVERRIDE test
# hook above can point this at a real ops_lib.sh checkout; resolves to the
# exact same production path when unset.
# shellcheck disable=SC1091
. "$APP_DIR/infra/ops_lib.sh" || {
    echo "$(date -u +%FT%TZ) FATAL: ops_lib.sh missing" >> "$LOG_FILE"; exit 1; }

check_service() {
    # Echoes "<tier>::<reason>" (tier = hard|soft) on failure, or nothing
    # when healthy. Tier is decided HERE, at the point each failure mode is
    # known, rather than by pattern-matching the reason text later — the
    # reason text is prose for the operator, not a stable machine contract.
    #
    # ── Two-tier confirmation (#532, 2026-08-06) ──────────────────────────
    # 30-day production query of mi_audit_log: 10 service_down alerts,
    # ZERO real outages. Every one was a deploy restart caught mid-flight —
    # `docker healthcheck: starting`, `container state: created`,
    # `container state: removing`, `container state: restarting`, and the
    # orchestrator's HTTP /health probe failing while the container
    # restarted — and every one recovered on the very next 5-min tick.
    # These states are AMBIGUOUS: indistinguishable, in a single snapshot,
    # from the start of a real failure. They are the SOFT tier below and
    # require a 2nd consecutive failing tick (~5 min later, via the
    # "$svc.pending" file in the main loop) before promoting to an actual
    # DOWN alert.
    # HARD states (exited/dead/paused/container-not-found/inspect-timeout/
    # docker-reported-unhealthy) still alert on tick 1, unchanged — none of
    # these describe a container mid-healthy-deploy. `unhealthy` in
    # particular is safe to trust immediately: Docker itself only reports it
    # after the healthcheck's own start_period has elapsed AND `retries`
    # consecutive probes have failed, so a container that genuinely fails to
    # boot still alerts fast via Docker's own model — no invented timer.
    local svc="$1"
    local state health rc
    # timeout (d3 review): a hung docker daemon — exactly the class a liveness
    # watchdog must catch — would otherwise block this call forever and the
    # watchdog would hang silently instead of alerting.
    state=$(timeout 8 docker inspect -f '{{.State.Status}}' "$svc" 2>/dev/null)
    rc=$?
    if [ "$rc" = 124 ]; then
        echo "hard::docker inspect timed out — daemon unresponsive?"
        return
    elif [ "$rc" != 0 ]; then
        echo "hard::container not found"
        return
    fi
    if [ "$state" != "running" ]; then
        case "$state" in
            exited|dead|paused)
                echo "hard::container state: $state" ;;
            *)
                # starting/created/restarting/removing/anything else
                # unlisted — ambiguous mid-deploy states, soft tier. Note
                # `restarting` sits here even though a crash-loop is a real
                # outage: a crash-loop STAYS `restarting` across many ticks,
                # so it still alerts on tick 2 (~10 min), just not tick 1.
                echo "soft::container state: $state" ;;
        esac
        return
    fi
    health=$(timeout 8 docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$svc" 2>/dev/null)
    if [ -n "$health" ] && [ "$health" != "healthy" ]; then
        if [ "$health" = "unhealthy" ]; then
            echo "hard::docker healthcheck: $health"
        else
            # Docker healthcheck status is one of starting/healthy/unhealthy
            # — "healthy" is filtered above, "unhealthy" just above, so the
            # only thing that reaches here is "starting" (the exact 8/02 and
            # 8/04 false-alarm pattern above).
            echo "soft::docker healthcheck: $health"
        fi
        return
    fi
    # Independent HTTP probe where the host can reach one directly.
    if [ "$svc" = "apollo-orchestrator" ]; then
        curl -fsS -m 10 http://127.0.0.1:8000/health >/dev/null 2>&1 \
            || { echo "soft::HTTP /health probe failed (port 8000)"; return; }
    fi
}

now=$(date +%s)

# ── Shared alert state-machine (#435): the create-file / dedup-6h-realert / recover-on-clear
# file mechanic was typed 3× (service loop + disk-warn + disk-critical; the header's own
# drift-irony note is why this gets extracted). ONE helper owns the file bookkeeping; each
# caller keeps its OWN tier-specific alert actions (the messages differ). Manages `$state_file`
# and echoes the transition, using globals $now + $REALERT_SECS:
#   fire    — fresh ok->active crossing (first alert)
#   refire  — still active AND the re-alert window elapsed (re-alert due)
#   hold    — active but inside the dedup window (say nothing)
#   recover — was active, now clear (announce recovery + remove state)
#   clear   — still clear (nothing to do)
alert_state() {
    local state_file="$1" active="$2" last
    if [ "$active" = 1 ]; then
        if [ ! -f "$state_file" ]; then
            echo "$now" > "$state_file"; echo fire
        else
            last=$(cat "$state_file" 2>/dev/null || echo 0)
            if [ $((now - last)) -ge "$REALERT_SECS" ]; then
                echo "$now" > "$state_file"; echo refire
            else
                echo hold
            fi
        fi
    elif [ -f "$state_file" ]; then
        rm -f "$state_file"; echo recover
    else
        echo clear
    fi
}

for svc in $SERVICES; do
    raw=$(check_service "$svc")
    tier="${raw%%::*}"
    reason="${raw#*::}"
    state_file="$STATE_DIR/$svc.down"
    pending_file="$STATE_DIR/$svc.pending"
    active=0

    if [ -z "$reason" ]; then
        # Healthy. Drop any stale soft-tier pending observation — silently:
        # per #532 design, a soft-down that clears before its 2nd confirming
        # tick must produce NO Telegram / NO audit row, log line only.
        if [ -f "$pending_file" ]; then
            log "PENDING CLEARED: $svc — cleared before 2nd confirming tick"
            rm -f "$pending_file"
        fi
    elif [ "$tier" != "soft" ] || [ -f "$state_file" ]; then
        # `!= "soft"` (not `== "hard"`) deliberately: check_service() only
        # ever tags "hard" or "soft" today, but this is a liveness
        # watchdog — if a future return point ever forgot the tag, failing
        # toward "alert now" is the safe direction, not "silently wait a
        # tick". Hard-down: alert immediately (tick 1), unchanged pre-#532
        # behaviour.
        # `-f "$state_file"` also covers a service ALREADY confirmed DOWN
        # (reached via hard, or a prior soft promotion) that is STILL
        # failing, hard or soft — it must stay active without re-entering
        # the 2-tick pending gate below, or a `restarting` crash-loop would
        # spuriously RECOVER every other tick as a fresh pending file cycles.
        # The 2-tick gate applies only to the clear -> failing transition.
        [ -f "$pending_file" ] && rm -f "$pending_file"
        active=1
    else
        # Soft tier, not yet confirmed down: require a 2nd CONSECUTIVE
        # failing tick (~5 min, the next cron run) before promoting to DOWN.
        if [ -f "$pending_file" ]; then
            rm -f "$pending_file"
            active=1
        else
            echo "$now" > "$pending_file"
            log "PENDING: $svc — $reason (soft tier, confirming on next tick)"
        fi
    fi

    case "$(alert_state "$state_file" "$active")" in
        fire)
            log "DOWN: $svc — $reason"
            audit_event "service_down" "watchdog: $svc DOWN — $reason"
            telegram_alert "🔴 *Service DOWN: ${svc}*"$'\n```\n'"$reason"$'\n```\n'"Watchdog re-alerts every 6h while down; recovery is announced." ;;
        refire)
            log "STILL DOWN: $svc — $reason"
            telegram_alert "🔴 *Service STILL DOWN: ${svc}*"$'\n```\n'"$reason"$'\n```' ;;
        recover)
            log "RECOVERED: $svc"
            audit_event "service_recovered" "watchdog: $svc recovered"
            telegram_alert "🟢 *Service recovered: ${svc}*" ;;
    esac
done

# ── Disk-space check (#422, 2026-07-06) ──────────────────────────────────────
# infra/service_watchdog.sh watched container liveness but not disk — a full
# disk degrades/kills every container silently (no clean crash signal; writes
# just start failing) well before docker itself notices anything is wrong.
# Reuses the SAME file-based transition/dedup/recover mechanics as
# check_service() above. TWO independent state files (not one) because the
# warn and critical tiers must arm/disarm independently: disk.high persists
# through the whole 85-100% band (only clears below 85%) so the WARN alert
# doesn't re-fire on every tick while stuck high; disk.critical clears below
# 90% specifically, so a 92% -> 87% -> 91% bounce still re-triggers the
# prune+CRITICAL alert on the fresh >=90% crossing even though disk.high
# never dropped. Without this split, the >=90% branch has no dedup at all —
# it would prune + Telegram on every 5-min tick while stuck critical (288/day).
DISK_WARN_PCT=85
DISK_PRUNE_PCT=90
disk_state_file="$STATE_DIR/disk.high"
disk_critical_file="$STATE_DIR/disk.critical"

disk_pct=$(df -P / 2>/dev/null | awk 'NR==2 {gsub("%","",$5); print $5}')
# Defensive: only trust a pure-digit result — a malformed df/awk parse must
# not blow up the `-ge` integer comparisons below under set -u.
case "$disk_pct" in ''|*[!0-9]*) disk_pct="" ;; esac

# Warn tier (>=85%): plain fire/dedup/recover via alert_state (#435). The [ -n ] guard
# short-circuits the -ge test when disk_pct is empty (set -u safe), same as the original.
disk_warn_active=$([ -n "$disk_pct" ] && [ "$disk_pct" -ge "$DISK_WARN_PCT" ] && echo 1 || echo 0)
case "$(alert_state "$disk_state_file" "$disk_warn_active")" in
    fire)
        log "DISK HIGH: / at ${disk_pct}%"
        audit_event "disk_space_high" "watchdog: / usage at ${disk_pct}% (warn threshold ${DISK_WARN_PCT}%)"
        telegram_alert "🟠 *Disk space HIGH*"$'\n```\n'"/ usage: ${disk_pct}% (warn >= ${DISK_WARN_PCT}%)"$'\n```\n'"Watchdog re-alerts every 6h while high; recovery is announced." ;;
    refire)
        log "DISK STILL HIGH: / at ${disk_pct}%"
        telegram_alert "🟠 *Disk space STILL HIGH*"$'\n```\n'"/ usage: ${disk_pct}%"$'\n```' ;;
    recover)
        log "DISK RECOVERED: / usage back below ${DISK_WARN_PCT}%"
        audit_event "disk_space_recovered" "watchdog: / usage back below ${DISK_WARN_PCT}%"
        telegram_alert "🟢 *Disk space recovered* — / usage back below ${DISK_WARN_PCT}%" ;;
esac

# Critical tier (>=90%): SEPARATE state file, same dedup/recover shape, so it
# arms/disarms on its own 90% line rather than piggybacking on disk.high.
#
# ADOPTED-MODIFIED (operator 2026-07-05, from Gemini review): at >=90% ALSO
# run SAFE prunes only — build cache + dangling images. The proposed
# `docker system prune -af --volumes` is REJECTED: if postgres (or any
# service) is down at prune time, its volume reads as "unused" and that
# command would DESTROY THE DATABASE. NEVER auto-prune volumes.
# Critical tier (>=90%) via alert_state (#435): fire AND refire both run the safe prune
# (matches the original run_prune=1 on both transition + re-alert); recover is log-only.
disk_crit_active=$([ -n "$disk_pct" ] && [ "$disk_pct" -ge "$DISK_PRUNE_PCT" ] && echo 1 || echo 0)
case "$(alert_state "$disk_critical_file" "$disk_crit_active")" in
    fire|refire)
        log "DISK CRITICAL: / at ${disk_pct}% — running safe prune (builder cache + dangling images only, no volumes)"
        prune_out=$( { timeout 60 docker builder prune -f; timeout 60 docker image prune -f; } 2>&1 )
        log "prune output: $prune_out"
        audit_event "disk_space_prune_run" "watchdog: / at ${disk_pct}% >= ${DISK_PRUNE_PCT}% — ran docker builder prune -f + docker image prune -f (dangling only; volumes never touched)"
        telegram_alert "🔴 *Disk space CRITICAL (${disk_pct}%)* — ran safe prune (builder cache + dangling images only; volumes NEVER touched)"$'\n```\n'"$prune_out"$'\n```' ;;
    recover)
        log "DISK CRITICAL cleared: / usage back below ${DISK_PRUNE_PCT}%" ;;
esac

# Daily heartbeat (~12:00–12:04 UTC slot of the */5 cron): proves the watchdog
# itself is alive — a dead cron is otherwise indistinguishable from all-green.
if [ "$(date -u +%H)" = "12" ] && [ "$(date -u +%M)" -lt 5 ]; then
    audit_event "watchdog_heartbeat" "service watchdog alive; watching: $SERVICES"
    log "heartbeat"
fi

exit 0
