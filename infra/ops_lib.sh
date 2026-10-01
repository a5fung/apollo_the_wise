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
#   - telegram_alert "$msg": sent as Telegram HTML (#121, 2026-10-01). Callers keep
#     writing the small legacy-Markdown dialect they always have — *bold*,
#     `code`, and ``` fences on their own lines — and the function converts it:
#     every &, < and > in the text is HTML-escaped FIRST, so a bare underscore, a
#     psql error or a "<none>" can no longer 400 the send (the 2026-07-05
#     restore-check lesson, which the old parse_mode=Markdown could only dodge by
#     fencing). Dynamic/error text should still ride inside a ``` fence: it renders
#     as a monospace block, and the markup pass leaves a fence's content alone.
#     If Telegram rejects the HTML send it is re-sent as PLAIN TEXT (tags removed,
#     entities unescaped - identifiers come through byte-for-byte). Failures are
#     LOGGED, never silent.
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

# ── Telegram HTML layer (#121) ────────────────────────────────────────────────
# bash 3.2 compatible (the dev box) and GNU/BSD sed compatible (-E, LC_ALL=C so an
# invalid byte in a docker error cannot abort the conversion).

_tg_escape() {
    # stdin -> stdout, & first so the entities we emit are not re-escaped
    LC_ALL=C sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'
}

_tg_markup() {
    # stdin (ALREADY escaped, no ``` fence in it) -> `code` and *bold* as tags.
    # Code first; bold may not span a tag (the [^*<>] class), so a stray * cannot
    # produce mis-nested HTML - it is left as a literal * instead.
    LC_ALL=C sed -E -e 's/`([^`]+)`/<code>\1<\/code>/g' \
                    -e 's/\*([^*<>]+)\*/<b>\1<\/b>/g'
}

_tg_md_to_html() {
    # $1 = legacy-Markdown-dialect text -> HTML on stdout.
    local fence='```' text rest seg out="" in_pre=0 more piece
    # printf x / strip-x: $(...) would otherwise eat trailing newlines; the extra \n
    # we feed sed is removed again, so GNU and BSD sed (which differ on a final
    # unterminated line) give the same bytes.
    text=$(printf '%s\n' "$1" | _tg_escape; printf x); text=${text%x}; text=${text%$'\n'}
    rest=$text
    while :; do
        case "$rest" in
            *"$fence"*) seg=${rest%%"$fence"*}; rest=${rest#*"$fence"}; more=1 ;;
            *)          seg=$rest;              rest="";                more=0 ;;
        esac
        if [ "$in_pre" = 1 ]; then
            # drop ONE newline after the opening fence and ONE before the closing one
            seg=${seg#$'\n'}; seg=${seg%$'\n'}
            out="${out}<pre>${seg}</pre>"
        else
            piece=$(printf '%s\n' "$seg" | _tg_markup; printf x); piece=${piece%x}; piece=${piece%$'\n'}
            out="${out}${piece}"
        fi
        [ "$more" = 1 ] || break
        if [ "$in_pre" = 1 ]; then in_pre=0; else in_pre=1; fi
    done
    printf '%s' "$out"
}

_tg_to_plain() {
    # $1 = HTML we built -> words only: tags out, entities unescaped (&amp; LAST).
    printf '%s\n' "$1" | LC_ALL=C sed -e 's/<[^>]*>//g' \
        -e 's/&lt;/</g' -e 's/&gt;/>/g' -e 's/&amp;/\&/g'
}

telegram_alert() {
    # $1 = message text; uses first user from TELEGRAM_ALLOWED_USER_IDS
    local msg="$1"
    local chat_id html plain err
    chat_id=$(printf '%s' "${TELEGRAM_ALLOWED_USER_IDS:-}" | cut -d, -f1)
    if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "$chat_id" ]; then
        return 0  # no creds — file log already captured detail
    fi
    html=$(_tg_md_to_html "$msg")
    if err=$(curl -fsS -m 15 \
            "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            --data-urlencode "chat_id=$chat_id" \
            --data-urlencode "text=$html" \
            --data-urlencode "parse_mode=HTML" 2>&1 >/dev/null); then
        return 0
    fi
    log "telegram_alert HTML send rejected (${err:-no curl output}) — retrying as plain text"
    plain=$(_tg_to_plain "$html")
    if err=$(curl -fsS -m 15 \
            "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            --data-urlencode "chat_id=$chat_id" \
            --data-urlencode "text=$plain" 2>&1 >/dev/null); then
        return 0
    fi
    log "telegram_alert send FAILED (curl/API: ${err:-no curl output}) — alert text was: $msg"
    return 0
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
