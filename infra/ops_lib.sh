# ops_lib.sh — shared telemetry helpers for the host-cron ops scripts
# (backup.sh · staging_restore_check.sh · service_watchdog.sh).
#
# Extracted 2026-07-05 (d3 /simplify): three hand-copied versions of these
# helpers drifted WITHIN A DAY — the Markdown-fence fix landed in two of the
# three copies. One canonical copy, sourced by absolute deployed path.
#
# Contract for callers:
#   - source AFTER setting LOG_FILE (falls back to /dev/null) and AFTER
#     sourcing the app .env (telegram creds come from the environment).
#   - telegram_alert "$msg": dynamic/error text inside the message MUST ride
#     inside a ``` fence — raw underscores 400 the legacy-Markdown API (the
#     2026-07-05 restore-check lesson). Send failures are LOGGED, never silent.
#   - audit_event "type" "summary" ["detail"]: telemetry-only INSERT, best-effort
#     by design (postgres may be the thing that's down). Uses a unique dollar-tag
#     so psql error text containing $$ (e.g. an echoed DO $$ block) can't
#     break the quoting, and tolerates a missing summary/detail arg under set -u.
#     `detail` is an OPTIONAL structured (JSON) machine-readable field, separate
#     from the human-prose `summary` — added #442 (2026-08-08) so downstream
#     readers (e.g. scripts/v1_closeout_status.py's FL-3 clock) don't have to
#     regex-parse `summary` prose, which silently breaks if the wording drifts.
#     Defaults to '' so every pre-existing 2-arg call site is unaffected.

log() { echo "$(date -u +%FT%TZ) $*" >> "${LOG_FILE:-/dev/null}"; }

telegram_alert() {
    # $1 = message text; uses first user from TELEGRAM_ALLOWED_USER_IDS
    local msg="$1"
    local chat_id
    chat_id=$(printf '%s' "${TELEGRAM_ALLOWED_USER_IDS:-}" | cut -d, -f1)
    if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "$chat_id" ]; then
        return 0  # no creds — file log already captured detail
    fi
    curl -fsS -m 15 \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=$chat_id" \
        --data-urlencode "text=$msg" \
        --data-urlencode "parse_mode=Markdown" >/dev/null 2>&1 \
        || log "telegram_alert send FAILED (curl/API) — alert text was: $msg"
}

audit_event() {
    # $1 = event_type; $2 = summary (optional; truncated to 500).
    # $3 = detail (optional; structured JSON string; truncated to 8000 — mirrors
    # log_audit_event's own truncation in agents/market_intelligence/db.py).
    local event="$1"
    local summary="${2:-}"
    local detail="${3:-}"
    summary="${summary:0:500}"
    detail="${detail:0:8000}"
    # Keep the no-detail SQL byte-identical to before #442 (a bare '' literal) —
    # every pre-existing 2-arg call site (backup.sh, staging_restore_check.sh,
    # service_watchdog.sh's disk-space/heartbeat events) hits this branch and
    # must see zero behavior change. Only dollar-quote when a real payload
    # is present.
    local detail_sql="''"
    if [ -n "$detail" ]; then
        detail_sql="\$apollo_detail\$${detail}\$apollo_detail\$"
    fi
    timeout 10 docker exec -i apollo-postgres psql -U apollo -d apollo -v ON_ERROR_STOP=1 \
        -c "INSERT INTO mi_audit_log (event_type, summary, detail) VALUES ('$event', \$apollo_ops\$${summary}\$apollo_ops\$, $detail_sql);" \
        >/dev/null 2>&1 || true
}
