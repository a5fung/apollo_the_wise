#!/usr/bin/env bash
# Apollo STAGING DB seed (#256 W3) — restore the latest prod pg_dump into the
# STAGING postgres instance. Run as a step inside `deploy.sh staging`, or manually
# on the prod box. A twofer: gives staging realistic data AND rehearses the DR
# restore path against a real dump.
#
# SAFETY (advisor 2026-06-13): the only path to prod data is naming the wrong
# container. This script references the staging instance ONLY via $STAGING_PG, and
# REFUSES to run unless that container's compose-project label == 'apollo-staging'
# (a typo'd-but-present container can pass a name compare; the project label can't).
# The destructive DROP runs against a PHYSICALLY SEPARATE instance + volume, never
# the prod apollo postgres.
set -u
set -o pipefail

STAGING_PG="apollo-staging-postgres"
EXPECTED_PROJECT="apollo-staging"
BACKUP_GLOB="/home/apollo/backups/apollo-*.sql.gz"
# referenced by GRANT/OWNER in the dump; pre-create so ON_ERROR_STOP doesn't halt.
# ⚠ This restore recipe (roles + DROP/CREATE + gunzip|psql + sanity counts) is a FORK
# of infra/restore.sh::phase_restore_sql — KEEP EXPECTED_ROLES IN SYNC with it until
# #281 extracts a shared restore_db() both call (the DR-script sourcing needs care).
EXPECTED_ROLES=(dashboard_ro)

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✔${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${RED}✘ $*${NC}" >&2; exit 1; }
banner(){ echo -e "\n${CYAN}━━━ $* ━━━${NC}"; }

banner "Staging DB seed → $STAGING_PG"

# ── GUARD 1: target container exists AND is labeled part of apollo-staging ─────
proj=$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' \
        "$STAGING_PG" 2>/dev/null) \
    || err "Container '$STAGING_PG' not found. Bring staging up first (deploy.sh staging)."
[ "$proj" = "$EXPECTED_PROJECT" ] \
    || err "REFUSING TO SEED: '$STAGING_PG' is in compose project '$proj', not '$EXPECTED_PROJECT'. Aborting before any destructive SQL."
ok "Target verified: '$STAGING_PG' in project '$proj'"

# ── GUARD 2: it must be ready ─────────────────────────────────────────────────
docker exec "$STAGING_PG" pg_isready -U apollo >/dev/null 2>&1 \
    || err "'$STAGING_PG' is not accepting connections (pg_isready failed)."

# ── Locate the newest prod dump ───────────────────────────────────────────────
# shellcheck disable=SC2012
DUMP=$(ls -1t $BACKUP_GLOB 2>/dev/null | head -1)
[ -n "$DUMP" ] && [ -r "$DUMP" ] \
    || err "No readable dump matching $BACKUP_GLOB. Run the nightly backup (scripts/backup.sh) first."
dump_age_h=$(( ( $(date +%s) - $(stat -c %Y "$DUMP") ) / 3600 ))
ok "Using dump: $DUMP (${dump_age_h}h old, $(( $(stat -c %s "$DUMP") / 1024 / 1024 ))MB)"
[ "$dump_age_h" -gt 48 ] && warn "Dump is >48h old — staging data will be stale."

# ── Pre-create roles the dump references (idempotent) ─────────────────────────
for role in "${EXPECTED_ROLES[@]}"; do
    docker exec "$STAGING_PG" psql -U apollo -d postgres -v ON_ERROR_STOP=1 \
        -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='$role') THEN CREATE ROLE $role; END IF; END \$\$;" \
        >/dev/null || err "Pre-create role $role failed"
done
ok "Pre-created roles: ${EXPECTED_ROLES[*]}"

# ── DROP + recreate the staging DB, then restore ──────────────────────────────
# (Guarded above; this only ever targets $STAGING_PG = the apollo-staging instance.)
docker exec "$STAGING_PG" psql -U apollo -d postgres -v ON_ERROR_STOP=1 \
    -c "DROP DATABASE IF EXISTS apollo;" \
    -c "CREATE DATABASE apollo OWNER apollo;" \
    || err "Drop/recreate staging database failed"
ok "Recreated empty staging database"

gunzip < "$DUMP" | \
    docker exec -i "$STAGING_PG" psql -U apollo -d apollo -v ON_ERROR_STOP=1 \
    > /tmp/staging-restore.log 2>&1 \
    || err "Restore failed; see /tmp/staging-restore.log"

# ── Sanity-check ──────────────────────────────────────────────────────────────
audit_count=$(docker exec "$STAGING_PG" psql -U apollo -d apollo -tA \
    -c "SELECT COUNT(*) FROM mi_audit_log;" 2>/dev/null || echo "0")
trade_count=$(docker exec "$STAGING_PG" psql -U apollo -d apollo -tA \
    -c "SELECT COUNT(*) FROM mi_live_trades;" 2>/dev/null || echo "0")
[ "${audit_count:-0}" -gt 0 ] || err "mi_audit_log row count zero after restore — seed failed"
ok "Seed complete: mi_audit_log=$audit_count rows, mi_live_trades=$trade_count rows"
