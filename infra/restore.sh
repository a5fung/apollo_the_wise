#!/usr/bin/env bash
# Apollo disaster-recovery restore driver
#
# Run as root on a fresh Ubuntu 22.04+ host. Idempotent — each phase
# writes a marker file in /var/lib/apollo-restore/<phase>.done; re-runs
# skip completed phases. `bash restore.sh --force <phase>` re-runs
# from a given phase, clearing later markers.
#
# Prerequisites (operator):
#  1. Provisioned fresh Ubuntu box, ssh-able as root
#  2. Latest `apollo-YYYYMMDD.sql.gz` downloaded to /tmp/ (or any path)
#  3. Latest `apollo-secrets-YYYYMMDD.tar.gz.gpg` downloaded to /tmp/
#  4. GPG passphrase from Google Password Manager at hand
#
# Reference: docs/ops/disaster_recovery.md

set -u
set -o pipefail

# ── Configuration ─────────────────────────────────────────────────────
REPO_URL="https://github.com/a5fung/apollo_the_wise.git"
REPO_BRANCH="${REPO_BRANCH:-main}"
APP_USER="apollo"
APP_HOME="/home/$APP_USER"
APP_DIR="$APP_HOME/apollo_the_wise"
MARKER_DIR=/var/lib/apollo-restore
COMPOSE_FILE="docker/docker-compose.prod.yml"

# Ordered phase list — single source of truth for execution order AND
# for --force <phase> downstream-marker-clearing semantics.
PHASES=(
    phase_apt
    phase_user
    phase_clone
    phase_prompt
    phase_decrypt_secrets
    phase_nginx_reload
    phase_db_up
    phase_restore_sql
    phase_app_up
    phase_validate
    phase_finish
)

# Force-re-run support: `bash restore.sh --force phase_clone` clears markers
# from phase_clone AND all later phases so the whole tail re-runs.
FORCE_FROM=""
if [ "${1:-}" = "--force" ] && [ -n "${2:-}" ]; then
    FORCE_FROM="$2"
fi

# ── Colors ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

banner()  { echo -e "\n${CYAN}━━━ $* ━━━${NC}"; }
ok()      { echo -e "${GREEN}✔${NC} $*"; }
warn()    { echo -e "${YELLOW}⚠${NC} $*"; }
err()     { echo -e "${RED}✘ $*${NC}" >&2; exit 1; }

# ── Phase scaffolding ────────────────────────────────────────────────
mkdir -p "$MARKER_DIR"

phase_marker() { echo "$MARKER_DIR/$1.done"; }

# If --force <phase> was given, clear that phase's marker AND every later
# phase's marker so the whole downstream tail re-runs. Without this,
# --force only forces the named phase and later phases silently skip on
# their stale markers.
if [ -n "$FORCE_FROM" ]; then
    seen_force=false
    for p in "${PHASES[@]}"; do
        if [ "$p" = "$FORCE_FROM" ]; then seen_force=true; fi
        if $seen_force; then rm -f "$MARKER_DIR/${p}.done"; fi
    done
    $seen_force || err "--force phase '$FORCE_FROM' not in PHASES list"
fi

should_run() {
    local phase="${FUNCNAME[1]}"  # phase function knows its own name
    if [ -f "$(phase_marker "$phase")" ]; then
        ok "Skipping $phase (already complete — delete $(phase_marker "$phase") to re-run)"
        return 1
    fi
    return 0
}

mark_done() { touch "$(phase_marker "${FUNCNAME[1]}")"; }

# ── Phase 1: apt install ──────────────────────────────────────────────
# Docker's apt repo is required for docker-compose-plugin (Compose v2);
# Ubuntu 22.04's `docker.io` package doesn't include it. Caught 2026-05-25
# during DR drill (E: Unable to locate package docker-compose-plugin).
phase_apt() {
    banner "Phase 1: apt install (docker, git, gnupg, postgres-client, nginx)"
    if ! should_run; then return 0; fi

    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        ca-certificates curl gnupg git python3 python3-pip \
        gzip postgresql-client nginx \
        || err "apt-get install (base packages) failed"

    # Add Docker's official apt repository (Ubuntu 22.04+).
    install -m 0755 -d /etc/apt/keyrings
    if [[ ! -s /etc/apt/keyrings/docker.asc ]]; then
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
            -o /etc/apt/keyrings/docker.asc \
            || err "Docker GPG key fetch failed"
        chmod a+r /etc/apt/keyrings/docker.asc
    fi
    local codename
    codename=$(. /etc/os-release && echo "$VERSION_CODENAME")
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $codename stable" \
        > /etc/apt/sources.list.d/docker.list

    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin \
        || err "apt-get install (docker) failed"

    systemctl enable docker
    systemctl start docker
    mark_done
    ok "Phase 1 complete"
}

# ── Phase 2: apollo user ──────────────────────────────────────────────
phase_user() {
    banner "Phase 2: create apollo user (uid 1000, docker group)"
    if ! should_run; then return 0; fi
    if ! id -u "$APP_USER" >/dev/null 2>&1; then
        useradd -m -u 1000 -s /bin/bash "$APP_USER" || err "useradd failed"
    fi
    usermod -aG docker "$APP_USER"
    mkdir -p "$APP_HOME/.ssh"
    chmod 700 "$APP_HOME/.ssh"
    chown -R "$APP_USER:$APP_USER" "$APP_HOME/.ssh"
    warn "Operator: paste your ssh pubkey into $APP_HOME/.ssh/authorized_keys (chmod 0600) before disconnecting"
    mark_done
    ok "Phase 2 complete"
}

# ── Phase 3: clone repo ──────────────────────────────────────────────
phase_clone() {
    banner "Phase 3: clone repo to $APP_DIR (branch $REPO_BRANCH)"
    if ! should_run; then return 0; fi
    if [ -d "$APP_DIR/.git" ]; then
        ok "Repo already cloned; pulling latest"
        sudo -u "$APP_USER" git -C "$APP_DIR" pull origin "$REPO_BRANCH"
    else
        sudo -u "$APP_USER" git clone -b "$REPO_BRANCH" "$REPO_URL" "$APP_DIR" \
            || err "git clone failed"
    fi
    mark_done
    ok "Phase 3 complete"
}

# ── Phase 4: prompts ─────────────────────────────────────────────────
# Stores operator-provided values into env vars for later phases.
# Idempotent: re-prompts only if env vars not provided OR marker missing.
phase_prompt() {
    banner "Phase 4: collect operator inputs"

    # Re-prompt for passphrase even when marker exists — it lives only in the
    # current shell (never persisted to disk). Paths persist; passphrase doesn't.
    if [ -f "$(phase_marker "$FUNCNAME")" ] && [ -f "$MARKER_DIR/restore_inputs" ]; then
        # shellcheck disable=SC1091
        . "$MARKER_DIR/restore_inputs"
        echo -n "GPG passphrase (paths cached from prior run; no echo): "
        read -rs GPG_PASSPHRASE
        echo ""
        [ -n "$GPG_PASSPHRASE" ] || err "Empty passphrase"
        export GPG_PASSPHRASE SECRETS_BLOB_PATH SQL_DUMP_PATH
        ok "Phase 4: paths reused, passphrase collected"
        return 0
    fi

    echo -n "GPG passphrase (paste from Google Password Manager; no echo): "
    read -rs GPG_PASSPHRASE
    echo ""
    [ -n "$GPG_PASSPHRASE" ] || err "Empty passphrase"

    echo -n "Absolute path to apollo-secrets-YYYYMMDD.tar.gz.gpg: "
    read -r SECRETS_BLOB_PATH
    [ -r "$SECRETS_BLOB_PATH" ] || err "File not readable: $SECRETS_BLOB_PATH"

    echo -n "Absolute path to apollo-YYYYMMDD.sql.gz: "
    read -r SQL_DUMP_PATH
    [ -r "$SQL_DUMP_PATH" ] || err "File not readable: $SQL_DUMP_PATH"

    umask 077
    {
        printf 'SECRETS_BLOB_PATH=%q\n' "$SECRETS_BLOB_PATH"
        printf 'SQL_DUMP_PATH=%q\n'    "$SQL_DUMP_PATH"
    } > "$MARKER_DIR/restore_inputs"
    export GPG_PASSPHRASE SECRETS_BLOB_PATH SQL_DUMP_PATH

    mark_done
    ok "Phase 4 complete"
}

# ── Phase 5: decrypt secrets bundle ──────────────────────────────────
phase_decrypt_secrets() {
    banner "Phase 5: decrypt secrets bundle + place files"
    if ! should_run; then return 0; fi

    # Stage decrypted plaintext in tmpfs (/dev/shm) so .env + gdrive-token
    # never touch disk. Function-scoped trap removes the dir on RETURN
    # whether the placements below succeed or err out.
    local stage_root decrypt_dir
    if [ -d /dev/shm ] && [ -w /dev/shm ]; then
        stage_root=/dev/shm
    else
        stage_root=${TMPDIR:-/tmp}
    fi
    decrypt_dir=$(mktemp -d -p "$stage_root")
    chmod 700 "$decrypt_dir"
    # shellcheck disable=SC2064
    trap "rm -rf '$decrypt_dir'" RETURN

    printf '%s' "$GPG_PASSPHRASE" | \
        gpg --batch --yes --passphrase-fd 0 \
            --decrypt "$SECRETS_BLOB_PATH" 2>/tmp/restore-gpg.log | \
        tar -xzf - -C "$decrypt_dir" \
        || err "Decryption/extract failed; see /tmp/restore-gpg.log"

    # Place files at correct locations
    if [ -r "$decrypt_dir/.env" ]; then
        mkdir -p "$APP_DIR"
        install -o "$APP_USER" -g "$APP_USER" -m 0600 \
            "$decrypt_dir/.env" "$APP_DIR/.env" || err ".env install failed"
        ok "Restored $APP_DIR/.env (0600)"
    else
        err ".env missing from bundle — cannot proceed"
    fi

    if [ -r "$decrypt_dir/gdrive-token.json" ]; then
        install -o "$APP_USER" -g "$APP_USER" -m 0600 \
            "$decrypt_dir/gdrive-token.json" "$APP_HOME/gdrive-token.json"
        ok "Restored $APP_HOME/gdrive-token.json (0600)"
    else
        warn "gdrive-token.json missing — nightly off-site backup will fail until re-auth"
    fi

    if [ -r "$decrypt_dir/apollo.conf" ]; then
        install -o root -g root -m 0644 \
            "$decrypt_dir/apollo.conf" /etc/nginx/sites-available/apollo.conf
        ln -sf /etc/nginx/sites-available/apollo.conf /etc/nginx/sites-enabled/apollo.conf
        ok "Restored nginx site"
    else
        warn "apollo.conf missing — TradingView webhook proxy not configured"
    fi

    if [ -r "$decrypt_dir/crontab.txt" ]; then
        crontab -u "$APP_USER" "$decrypt_dir/crontab.txt"
        ok "Restored crontab for $APP_USER"
    else
        warn "crontab.txt missing — nightly backup not scheduled"
    fi

    # Show manifest for operator verification
    if [ -r "$decrypt_dir/MANIFEST.txt" ]; then
        echo -e "${CYAN}Bundle manifest:${NC}"
        cat "$decrypt_dir/MANIFEST.txt"
    fi

    # Cleanup handled by function-scoped trap RETURN above (tmpfs has no
    # persistence, no shred needed). Old shred + rmdir kept as belt-and-
    # suspenders for the fallback /tmp path, but the trap is authoritative.

    mark_done
    ok "Phase 5 complete"
}

# ── Phase 6: nginx reload ────────────────────────────────────────────
phase_nginx_reload() {
    banner "Phase 6: reload nginx"
    if ! should_run; then return 0; fi
    if nginx -t 2>&1; then
        systemctl reload nginx || systemctl start nginx
        ok "Phase 6 complete"
    else
        warn "nginx -t failed; TradingView webhook unavailable until fixed manually"
    fi
    mark_done
}

# ── Phase 7: bring up postgres + redis ───────────────────────────────
# docker-compose v2 does NOT auto-load .env from the project root when -f points
# to a subdirectory file (docker/docker-compose.prod.yml here). Must pass
# --env-file explicitly or POSTGRES_PASSWORD/REDIS_PASSWORD substitute to empty
# and postgres exits with "superuser password is not specified". Caught
# 2026-05-25 DR drill.
phase_db_up() {
    banner "Phase 7: docker compose up postgres + redis (300s pg_isready)"
    if ! should_run; then return 0; fi
    cd "$APP_DIR"
    sudo -u "$APP_USER" docker compose --env-file .env -f "$COMPOSE_FILE" \
        up -d postgres redis \
        || err "docker compose up postgres redis failed"

    # Poll pg_isready — 300s headroom for slow boxes (advisor 2026-05-23)
    local elapsed=0
    while [ $elapsed -lt 300 ]; do
        if docker exec apollo-postgres pg_isready -U apollo >/dev/null 2>&1; then
            ok "Postgres ready after ${elapsed}s"
            mark_done
            return 0
        fi
        sleep 5
        elapsed=$((elapsed + 5))
    done
    err "Postgres did not become ready within 300s"
}

# ── Phase 8: restore SQL dump ────────────────────────────────────────
phase_restore_sql() {
    banner "Phase 8: restore SQL dump from $SQL_DUMP_PATH"
    if ! should_run; then return 0; fi

    # Drop and recreate database for clean target
    docker exec apollo-postgres psql -U apollo -d postgres -v ON_ERROR_STOP=1 \
        -c "DROP DATABASE IF EXISTS apollo;" \
        -c "CREATE DATABASE apollo OWNER apollo;" \
        || err "Drop/recreate database failed"

    # Restore the dump
    gunzip < "$SQL_DUMP_PATH" | \
        docker exec -i apollo-postgres psql -U apollo -d apollo -v ON_ERROR_STOP=1 \
        > /tmp/restore-psql.log 2>&1 \
        || err "psql restore failed; see /tmp/restore-psql.log"

    # Sanity-check row counts in key tables
    local audit_count trade_count
    audit_count=$(docker exec apollo-postgres psql -U apollo -d apollo -tA \
        -c "SELECT COUNT(*) FROM mi_audit_log;" 2>/dev/null || echo "0")
    trade_count=$(docker exec apollo-postgres psql -U apollo -d apollo -tA \
        -c "SELECT COUNT(*) FROM mi_live_trades;" 2>/dev/null || echo "0")
    [ "$audit_count" -gt 0 ] || err "mi_audit_log row count zero after restore"
    ok "Restored: mi_audit_log=$audit_count rows, mi_live_trades=$trade_count rows"

    mark_done
}

# ── Phase 9: bring up apollo services ────────────────────────────────
phase_app_up() {
    banner "Phase 9: deploy.sh both (runs 5-gate preflight chain)"
    if ! should_run; then return 0; fi
    cd "$APP_DIR"
    sudo -u "$APP_USER" bash scripts/deploy.sh both \
        || err "deploy.sh failed; inspect output and re-run with --force phase_app_up"
    mark_done
    ok "Phase 9 complete"
}

# ── Phase 10: validation ─────────────────────────────────────────────
phase_validate() {
    banner "Phase 10: post-restore validation"
    if ! should_run; then return 0; fi

    cd "$APP_DIR"
    echo -e "\n${CYAN}--- readiness_check.py --verbose ---${NC}"
    sudo -u "$APP_USER" python3 scripts/readiness_check.py --verbose || \
        warn "readiness_check.py exited non-zero — review L1 invariants above"

    echo -e "\n${CYAN}--- preflight_check.py ---${NC}"
    sudo -u "$APP_USER" python3 scripts/preflight_check.py || \
        warn "preflight_check.py exited non-zero — Alpaca creds or safeguards issue"

    echo -e "\n${CYAN}--- docker compose ps ---${NC}"
    sudo -u "$APP_USER" docker compose --env-file .env -f "$COMPOSE_FILE" ps

    cat <<EOF

${YELLOW}━━━ MANUAL VALIDATION REQUIRED ━━━${NC}

The following checks require operator action (no automation possible):

  1. Telegram /status — bot responds within 5s; per-mode equity matches
     Alpaca web UI within \$1.
  2. Telegram /trades — open position list matches Alpaca portfolio page
     exactly (symbol + qty).
  3. Telegram /account — daytrade_count and drawdown_breaker state plausible.
  4. Trigger sync_positions manually (iterates both paper + live modes internally):
       docker exec apollo-market python -c "import asyncio; from agents.market_intelligence.broker.order_manager import sync_positions; print(asyncio.run(sync_positions()))"
     Verify no discrepancy in Telegram alert.
  5. Recent audit log (no errors post-restore start):
       docker exec apollo-postgres psql -U apollo -d apollo -c "SELECT event_type, created_at FROM mi_audit_log WHERE created_at > NOW() - INTERVAL '1 hour' ORDER BY created_at DESC LIMIT 20;"

EOF
    mark_done
    ok "Phase 10 complete"
}

# ── Phase 11: finish ─────────────────────────────────────────────────
phase_finish() {
    banner "Phase 11: post-restore manual followups"
    cat <<EOF

${GREEN}━━━ RESTORE COMPLETE ━━━${NC}

Final manual steps required:

  (a) Recreate /home/apollo/.backup-passphrase from Google Password Manager:
        umask 077
        printf '%s' '<paste passphrase>' > /home/apollo/.backup-passphrase
        chmod 400 /home/apollo/.backup-passphrase
        chown apollo:apollo /home/apollo/.backup-passphrase

      Without this, tomorrow's 02:00 ET secrets backup will Telegram SKIPPED
      and the 04:33 ET health check will alert STALE within 36h.

  (b) Verify next 02:00 ET cron run writes both gdrive_backup_success and
      gdrive_secrets_success audit rows.

  (c) Update TradingView webhook URL if the new server has a different
      public IP. Existing TRADINGVIEW_WEBHOOK_SECRET in .env survives —
      only the URL needs updating in TradingView alert templates.

  (d) Re-add ssh deploy key to GitHub if you regenerated keys for the new
      host (only needed for private repo clone; this repo is currently
      public so step is optional).

EOF
    ok "All phases complete"
}

# ── Driver ────────────────────────────────────────────────────────────
banner "Apollo disaster recovery restore"
echo "Started: $(date -Iseconds)"
echo "Marker dir: $MARKER_DIR"
[ -n "$FORCE_FROM" ] && warn "Force re-run from phase: $FORCE_FROM"

[ "$(id -u)" -eq 0 ] || err "Must run as root"

for p in "${PHASES[@]}"; do
    "$p"
done

echo "Finished: $(date -Iseconds)"
