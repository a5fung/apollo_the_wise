#!/usr/bin/env bash
# staging_restore_check.sh — nightly proof that the latest pg_dump actually RESTORES.
# (#256 W4, 2026-07-05.)
#
# Runs on the prod host (cron 03:30 UTC, ~90 min after backup.sh): restores the newest
# apollo-*.sql.gz into a throwaway pgvector container (SAME image as prod postgres) with
# psql ON_ERROR_STOP=1 — the exact invocation infra/restore.sh uses in a real DR — then
# probes key-table row counts. Kills the last silent-failure gap in the backup chain:
# gdrive staleness already alerts (04:33 ET job) but nothing proved the dump RESTORES.
#
# Telemetry contract: success -> backup_restore_check_ok audit row (no Telegram; reserve
# Telegram for actionable). Any failure -> backup_restore_check_failed audit row +
# Telegram alert. Trade state is NEVER touched — the restore target is an ephemeral
# container (no volume) removed on exit; prod containers are never restarted or written
# beyond the one mi_audit_log telemetry row (same designed sink backup.sh uses).

set -uo pipefail  # deliberately NOT -e: every failure routes through fail() so the
                  # alert + cleanup always run (a silent death here recreates the
                  # exact blind spot this script exists to close)

BACKUP_DIR=/home/apollo/backups
APP_DIR=/home/apollo/apollo_the_wise
ENV_FILE=$APP_DIR/.env
LOG_FILE=$BACKUP_DIR/restore-check.log
CONTAINER=apollo-restore-check
ERR_TMP=$(mktemp)
START_TS=$(date +%s)

# Same image as prod postgres — the dump needs pgvector for CREATE EXTENSION vector.
IMAGE=$(docker inspect apollo-postgres --format '{{.Config.Image}}' 2>/dev/null || echo "pgvector/pgvector:pg16")

if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

log() { echo "$(date -u +%FT%TZ) $*" >> "$LOG_FILE"; }

telegram_alert() {
    # $1 = message text; uses first user from TELEGRAM_ALLOWED_USER_IDS (backup.sh idiom)
    local msg="$1"
    local chat_id
    chat_id=$(printf '%s' "${TELEGRAM_ALLOWED_USER_IDS:-}" | cut -d, -f1)
    if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "$chat_id" ]; then
        return 0  # no creds, skip silently — file log already captured detail
    fi
    curl -fsS -m 15 \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=$chat_id" \
        --data-urlencode "text=$msg" \
        --data-urlencode "parse_mode=Markdown" >/dev/null 2>&1 || true
}

audit_event() {
    # $1 = event_type; $2 = summary. Telemetry-only INSERT (backup.sh idiom).
    local event="$1"
    local summary="${2:0:500}"
    docker exec -i apollo-postgres psql -U apollo -d apollo -v ON_ERROR_STOP=1 \
        -c "INSERT INTO mi_audit_log (event_type, summary, detail) VALUES ('$event', \$\$${summary}\$\$, '');" \
        >/dev/null 2>&1 || true
}

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; rm -f "$ERR_TMP"; }

fail() {
    local reason="$1"
    log "FAIL: $reason"
    audit_event "backup_restore_check_failed" "$reason"
    telegram_alert "🚨 *Backup restore-check FAILED* — $reason — the nightly dump may NOT be restorable. See $LOG_FILE"
    cleanup
    exit 1
}

# 1. Newest dump, freshness-gated (a stale dump passing would be a false green).
LATEST=$(ls -1t "$BACKUP_DIR"/apollo-*.sql.gz 2>/dev/null | head -1)
[ -n "$LATEST" ] || fail "no apollo-*.sql.gz found in $BACKUP_DIR"
if [ -z "$(find "$LATEST" -mmin -1560 2>/dev/null)" ]; then
    fail "latest dump older than 26h: $(basename "$LATEST")"
fi

# 2. Ephemeral restore target (no volume; bounded memory; auto-removed).
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" --memory=2g \
    -e POSTGRES_USER=apollo -e POSTGRES_PASSWORD=restorecheck -e POSTGRES_DB=apollo \
    "$IMAGE" >/dev/null 2>"$ERR_TMP" || fail "restore container failed to start: $(tail -c 300 "$ERR_TMP")"

# 3. Wait for postgres (init does an internal restart — require a stable psql).
ready=0
for _ in $(seq 1 30); do
    if docker exec "$CONTAINER" psql -U apollo -d apollo -c 'SELECT 1' >/dev/null 2>&1; then
        sleep 3  # ride out the initdb restart window
        if docker exec "$CONTAINER" psql -U apollo -d apollo -c 'SELECT 1' >/dev/null 2>&1; then
            ready=1; break
        fi
    fi
    sleep 2
done
[ "$ready" = 1 ] || fail "restore container postgres never became ready (60s)"

# 4. Restore — the same psql ON_ERROR_STOP=1 path infra/restore.sh uses for real DR.
if ! gunzip -c "$LATEST" | docker exec -i "$CONTAINER" psql -q -U apollo -d apollo \
        -v ON_ERROR_STOP=1 >/dev/null 2>"$ERR_TMP"; then
    fail "psql restore errored for $(basename "$LATEST"): $(tail -c 400 "$ERR_TMP")"
fi

# 5. Coherence probes — key tables non-empty + plausible table count.
COUNTS=$(docker exec "$CONTAINER" psql -U apollo -d apollo -tA -c \
    "SELECT (SELECT count(*) FROM mi_live_trades) || '|' ||
            (SELECT count(*) FROM mi_audit_log)   || '|' ||
            (SELECT count(*) FROM mi_ep_alerts)   || '|' ||
            (SELECT count(*) FROM mi_themes)      || '|' ||
            (SELECT count(*) FROM mi_strategies)  || '|' ||
            (SELECT count(*) FROM information_schema.tables WHERE table_schema='public')" \
    2>"$ERR_TMP") || fail "coherence probe query failed: $(tail -c 300 "$ERR_TMP")"

IFS='|' read -r n_trades n_audit n_alerts n_themes n_strats n_tables <<< "$COUNTS"
for pair in "mi_live_trades:$n_trades" "mi_audit_log:$n_audit" "mi_ep_alerts:$n_alerts" \
            "mi_themes:$n_themes" "mi_strategies:$n_strats"; do
    [ "${pair##*:}" -gt 0 ] 2>/dev/null || fail "restored ${pair%%:*} is EMPTY (dump incoherent?)"
done
[ "$n_tables" -gt 40 ] 2>/dev/null || fail "restored schema has only $n_tables public tables"

# 6. Green.
DURATION=$(( $(date +%s) - START_TS ))
SUMMARY="restored $(basename "$LATEST") in ${DURATION}s: trades=$n_trades audit=$n_audit ep_alerts=$n_alerts themes=$n_themes strategies=$n_strats tables=$n_tables"
log "OK: $SUMMARY"
audit_event "backup_restore_check_ok" "$SUMMARY"
cleanup
exit 0
