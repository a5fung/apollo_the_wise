#!/usr/bin/env bash
# service_watchdog.sh — per-service liveness watchdog (#256 W4, 2026-07-05).
#
# Operator-picked over configuring uptime-kuma (which sat EMPTY for 3 months —
# UI-config drifts; a versioned script doesn't). Host cron every 5 min:
# checks each core container's docker state (running + healthy when a
# healthcheck exists) plus an independent HTTP probe on the orchestrator's
# host-mapped port. Alerts on the DOWN transition, re-alerts every 6h while
# still down, sends a RECOVERED note on the way back up. Success = silent.
#
# Telemetry: Telegram (dynamic text FENCED — the 2026-07-05 restore-check
# lesson: raw underscores 400 the legacy-Markdown API and '|| true' eats it)
# + best-effort mi_audit_log rows (service_down / service_recovered /
# watchdog_heartbeat). Dedup state lives in FILES, deliberately NOT the DB —
# the watchdog must keep working when postgres is the thing that's down.
#
# Known blind spot (accepted): runs on the same host it watches — whole-host
# death needs an external pinger (filed as a follow-up).

set -uo pipefail  # not -e: every failure routes through explicit handling

APP_DIR=/home/apollo/apollo_the_wise
ENV_FILE=$APP_DIR/.env
STATE_DIR=/home/apollo/backups/watchdog_state
LOG_FILE=/home/apollo/backups/watchdog.log
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
# copy; the per-script copies drifted within a day (d3 /simplify).
# shellcheck disable=SC1091
. /home/apollo/apollo_the_wise/infra/ops_lib.sh || {
    echo "$(date -u +%FT%TZ) FATAL: ops_lib.sh missing" >> "$LOG_FILE"; exit 1; }

check_service() {
    # Echoes a failure reason, or nothing when healthy.
    local svc="$1"
    local state health rc
    # timeout (d3 review): a hung docker daemon — exactly the class a liveness
    # watchdog must catch — would otherwise block this call forever and the
    # watchdog would hang silently instead of alerting.
    state=$(timeout 8 docker inspect -f '{{.State.Status}}' "$svc" 2>/dev/null)
    rc=$?
    if [ "$rc" = 124 ]; then
        echo "docker inspect timed out — daemon unresponsive?"
        return
    elif [ "$rc" != 0 ]; then
        echo "container not found"
        return
    fi
    if [ "$state" != "running" ]; then
        echo "container state: $state"
        return
    fi
    health=$(timeout 8 docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$svc" 2>/dev/null)
    if [ -n "$health" ] && [ "$health" != "healthy" ]; then
        echo "docker healthcheck: $health"
        return
    fi
    # Independent HTTP probe where the host can reach one directly.
    if [ "$svc" = "apollo-orchestrator" ]; then
        curl -fsS -m 10 http://127.0.0.1:8000/health >/dev/null 2>&1 \
            || { echo "HTTP /health probe failed (port 8000)"; return; }
    fi
}

now=$(date +%s)
for svc in $SERVICES; do
    reason=$(check_service "$svc")
    state_file="$STATE_DIR/$svc.down"
    if [ -n "$reason" ]; then
        if [ ! -f "$state_file" ]; then
            # up -> down transition
            echo "$now" > "$state_file"
            log "DOWN: $svc — $reason"
            audit_event "service_down" "watchdog: $svc DOWN — $reason"
            telegram_alert "🔴 *Service DOWN: ${svc}*"$'\n```\n'"$reason"$'\n```\n'"Watchdog re-alerts every 6h while down; recovery is announced."
        else
            last_alert=$(cat "$state_file" 2>/dev/null || echo 0)
            if [ $((now - last_alert)) -ge $REALERT_SECS ]; then
                echo "$now" > "$state_file"
                log "STILL DOWN: $svc — $reason"
                telegram_alert "🔴 *Service STILL DOWN: ${svc}*"$'\n```\n'"$reason"$'\n```'
            fi
        fi
    else
        if [ -f "$state_file" ]; then
            rm -f "$state_file"
            log "RECOVERED: $svc"
            audit_event "service_recovered" "watchdog: $svc recovered"
            telegram_alert "🟢 *Service recovered: ${svc}*"
        fi
    fi
done

# Daily heartbeat (~12:00–12:04 UTC slot of the */5 cron): proves the watchdog
# itself is alive — a dead cron is otherwise indistinguishable from all-green.
if [ "$(date -u +%H)" = "12" ] && [ "$(date -u +%M)" -lt 5 ]; then
    audit_event "watchdog_heartbeat" "service watchdog alive; watching: $SERVICES"
    log "heartbeat"
fi

exit 0
