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

# Shared telemetry helpers (log / telegram_alert / audit_event) — one canonical
# copy in ops_lib.sh; the per-script copies drifted within a day (d3 /simplify).
# shellcheck disable=SC1091
. /home/apollo/apollo_the_wise/infra/ops_lib.sh || {
    echo "$(date -u +%FT%TZ) FATAL: ops_lib.sh missing" >> "$LOG_FILE"; exit 1; }

cleanup() { docker rm -f -v "$CONTAINER" >/dev/null 2>&1 || true; rm -f "$ERR_TMP"; }
# EXIT trap (d3 review): an external kill (cron timeout wrapper, SIGTERM)
# mid-run must not leak the restore container + tmp file until tomorrow.
trap cleanup EXIT

fail() {
    local reason="$1"
    log "FAIL: $reason"
    audit_event "backup_restore_check_failed" "$reason"
    # Dynamic text goes INSIDE a code fence — raw psql errors carry underscores
    # (dashboard_ro) that break Telegram legacy-Markdown entity parsing and got
    # the first-ever failure alert silently 400'd (2026-07-05). Fence = no
    # entity parsing inside; real newlines so --data-urlencode wires them.
    telegram_alert "🚨 *Backup restore-check FAILED* — the nightly dump may NOT be restorable."$'\n```\n'"$reason"$'\n```\n'"See $LOG_FILE"
    exit 1
}

# 1. Newest dump, freshness-gated (a stale dump passing would be a false green).
LATEST=$(ls -1t "$BACKUP_DIR"/apollo-*.sql.gz 2>/dev/null | head -1)
[ -n "$LATEST" ] || fail "no apollo-*.sql.gz found in $BACKUP_DIR"
if [ -z "$(find "$LATEST" -mmin -1560 2>/dev/null)" ]; then
    fail "latest dump older than 26h: $(basename "$LATEST")"
fi

# 2. Ephemeral restore target (bounded memory; auto-removed WITH its anonymous volume).
# ⚠ 2026-08-02: the old comment claimed "no volume" and it was WRONG. The postgres image
# declares VOLUME /var/lib/postgresql/data, so `docker run` ALWAYS creates an anonymous
# volume here — and `docker rm` WITHOUT -v leaves it behind. This leaked ~1.4 GB EVERY
# NIGHT: 34 orphaned volumes / ~48 GB had accumulated by the time the disk watchdog fired
# at 85%. `-v` removes the anonymous volume with the container. It CANNOT touch the live
# database: docker_postgres_data is a NAMED volume on a different container, and -v only
# removes anonymous volumes belonging to the container being removed.
docker rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
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

# 3b. Pre-create the roles the dump GRANTs to — the SAME recipe restore.sh
# Phase 8 falls back on, parsed from its EXPECTED_ROLES line so there is ONE
# list. This makes the nightly check the DRIFT FENCE for that hand-maintained
# list: a role added in prod without updating restore.sh fails HERE within 24h
# ("role X does not exist"), instead of surfacing during a real DR. (First
# run 2026-07-05 failed on exactly this — dashboard_ro — proving the fence.)
ROLES_LINE=$(grep -E '^EXPECTED_ROLES=\(' "$APP_DIR/infra/restore.sh" || true)
[ -n "$ROLES_LINE" ] || fail "could not parse EXPECTED_ROLES from infra/restore.sh"
ROLES=$(echo "$ROLES_LINE" | sed -E 's/^EXPECTED_ROLES=\(([^)]*)\).*/\1/')
for role in $ROLES; do
    docker exec "$CONTAINER" psql -U apollo -d postgres -v ON_ERROR_STOP=1 \
        -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='$role') THEN CREATE ROLE $role; END IF; END \$\$;" \
        >/dev/null 2>"$ERR_TMP" || fail "pre-create role '$role' failed: $(tail -c 200 "$ERR_TMP")"
done

# 4. Restore — the same psql ON_ERROR_STOP=1 path infra/restore.sh uses for real DR.
if ! gunzip -c "$LATEST" | docker exec -i "$CONTAINER" psql -q -U apollo -d apollo \
        -v ON_ERROR_STOP=1 >/dev/null 2>"$ERR_TMP"; then
    fail "psql restore errored for $(basename "$LATEST"): $(tail -c 400 "$ERR_TMP")"
fi

# 4b. Boot schema-init on the RESTORED schema (#437) — replay the EXACT agent-boot path
# (`initialize_schema`: CREATE TABLE IF NOT EXISTS → migrations → strategy seed, the same call
# agent.py makes at startup) against the restored dump. A CHECK-constraint / seed crash — the
# 7/6 #424 boot-crash class, which surfaced ONLY at prod boot because card tests mock the pool —
# fails HERE within 24h, mechanically, against the REAL restored schema. Runs in a throwaway
# app-image container sharing the restore container's netns (localhost:5432 = the restored DB);
# the 'restorecheck' password can only reach the ephemeral DB, so prod is NEVER touched.
# (Mechanism verified 2026-07-09 against an empty DB: 77 tables + 7 strategies, exit 0.)
APP_IMAGE=$(docker inspect apollo-market --format '{{.Config.Image}}' 2>/dev/null || echo "docker-market-agent")
if ! docker run --rm --network "container:$CONTAINER" \
        -e POSTGRES_HOST=localhost -e POSTGRES_PORT=5432 -e POSTGRES_USER=apollo \
        -e POSTGRES_PASSWORD=restorecheck -e POSTGRES_DB=apollo \
        "$APP_IMAGE" python -c \
        "import asyncio; from agents.market_intelligence.db import initialize_schema; asyncio.run(initialize_schema())" \
        >/dev/null 2>"$ERR_TMP"; then
    # DISTINCT from a restore failure — the dump restored fine; the CODE's boot schema-init
    # crashes on the restored schema (a deploy would boot-crash). Don't cry "dump unrestorable".
    reason="schema-init/strategy-seed CRASHES on the restored schema (boot-crash class, e.g. a CHECK constraint the code's seed violates): $(tail -c 400 "$ERR_TMP")"
    log "FAIL (schema-init): $reason"
    audit_event "restore_check_schema_init_failed" "$reason"
    telegram_alert "🚨 *Schema-init CRASHES on the restored schema* — a deploy would boot-crash (the #424 CHECK-constraint class). The dump restored fine; this is a CODE-vs-schema incompatibility."$'\n```\n'"$reason"$'\n```\n'"See $LOG_FILE"
    exit 1
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
exit 0
