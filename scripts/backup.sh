#!/bin/bash
# Apollo nightly backup → Google Drive
#
# Cron: 0 2 * * * /home/apollo/backup.sh
# Deployed to: apollo@87.99.134.162:/home/apollo/backup.sh
#
# Failure surfacing: Telegrams on any failure step AND writes an
# audit row to mi_audit_log so the apollo-market backup-health-check
# job can detect missed runs.
set -u
set -o pipefail

BACKUP_DIR=/home/apollo/backups
ENV_FILE=/home/apollo/apollo_the_wise/.env
BACKUP_FILE=$BACKUP_DIR/apollo-$(date +%Y%m%d).sql.gz
LOG_FILE=$BACKUP_DIR/gdrive.log

# Source Telegram credentials (read-only; .env is chmod 600)
if [ -r "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

telegram_alert() {
    # $1 = message text; uses first user from TELEGRAM_ALLOWED_USER_IDS
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
    # $1 = event_type; $2 = summary (will be truncated by call site to 500)
    local event="$1"
    local summary="${2:0:500}"
    docker exec -i apollo-postgres psql -U apollo -d apollo -v ON_ERROR_STOP=1 \
        -c "INSERT INTO mi_audit_log (event_type, summary, detail) VALUES ('$event', \$\$${summary}\$\$, '');" \
        >/dev/null 2>&1 || true
}

# Step 1 — pg_dump
if ! docker exec apollo-postgres pg_dump -U apollo apollo 2>>"$LOG_FILE" | gzip > "$BACKUP_FILE"; then
    err_tail=$(tail -10 "$LOG_FILE" 2>/dev/null | tr '\n' ' ' | cut -c1-300)
    telegram_alert "🚨 *Apollo backup FAILED* (pg_dump)%0A\`\`\`%0A${err_tail}%0A\`\`\`"
    audit_event "backup_failed" "pg_dump failed: ${err_tail}"
    exit 1
fi

dump_size=$(stat -c %s "$BACKUP_FILE" 2>/dev/null || echo "?")
dump_mb=$((dump_size / 1024 / 1024))

# Step 1b — Encrypted secrets bundle (.env + gdrive-token.json + nginx + crontab)
# Skipped if BACKUP_PASSPHRASE_FILE absent (e.g., post-restore before operator
# recreates the passphrase file). Failure here NEVER blocks pg_dump path.
#
# Plaintext .env / gdrive-token are staged in /dev/shm (RAM-backed tmpfs)
# so they never touch disk. Function-scoped `trap RETURN` unconditionally
# removes the staging dir on either success or failure path — dedups the
# previous cleanup branches and removes the shred -u step entirely
# (shred is ext4-journaling-best-effort anyway; tmpfs has no persistence).
SECRETS_BLOB=$BACKUP_DIR/apollo-secrets-$(date +%Y%m%d).tar.gz.gpg

run_secrets_backup() {
    # Use tmpfs when available so plaintext stays in RAM. Fall back to
    # default $TMPDIR if /dev/shm is missing (containerized hosts).
    local stage_root
    if [ -d /dev/shm ] && [ -w /dev/shm ]; then
        stage_root=/dev/shm
    else
        stage_root=${TMPDIR:-/tmp}
    fi
    local bundle_dir
    bundle_dir=$(mktemp -d -p "$stage_root")
    chmod 700 "$bundle_dir"
    # Unconditional cleanup on function return (success OR failure path)
    # shellcheck disable=SC2064
    trap "rm -rf '$bundle_dir'" RETURN

    {
        cp "$ENV_FILE" "$bundle_dir/.env" 2>/dev/null || true
        cp /home/apollo/gdrive-token.json "$bundle_dir/gdrive-token.json" 2>/dev/null || true
        cp /etc/nginx/sites-available/apollo.conf "$bundle_dir/apollo.conf" 2>/dev/null || true
        crontab -u apollo -l > "$bundle_dir/crontab.txt" 2>/dev/null || true
        {
            printf 'apollo-secrets bundle %s\n' "$(date -Iseconds)"
            printf 'staged in: %s\n' "$stage_root"
            printf 'includes (best-effort):\n'
            ls -la "$bundle_dir" | awk 'NR>1 {print "  " $NF " (" $5 " bytes)"}'
        } > "$bundle_dir/MANIFEST.txt"
    } 2>>"$LOG_FILE"

    if ! tar -czf "$bundle_dir/bundle.tar.gz" -C "$bundle_dir" \
            .env gdrive-token.json apollo.conf crontab.txt MANIFEST.txt 2>>"$LOG_FILE" || \
       ! gpg --batch --yes \
           --passphrase-file "$BACKUP_PASSPHRASE_FILE" \
           --symmetric --cipher-algo AES256 \
           -o "$SECRETS_BLOB" "$bundle_dir/bundle.tar.gz" 2>>"$LOG_FILE"; then
        local bundle_err
        bundle_err=$(tail -10 "$LOG_FILE" | tr '\n' ' ' | cut -c1-300)
        telegram_alert "🚨 *Apollo secrets backup FAILED (encrypt step)*%0A\`\`\`%0A${bundle_err}%0A\`\`\`"
        audit_event "gdrive_secrets_failed" "Encryption failed: ${bundle_err}"
        return 1
    fi

    # Upload encrypted blob via existing OAuth path
    local secrets_log_tmp
    secrets_log_tmp=$(mktemp)
    if GDRIVE_TOKEN_FILE=/home/apollo/gdrive-token.json \
       GDRIVE_FOLDER_ID=1kXY1LAld1_ZwFa28ZAh3cLVNft7agamb \
       python3 /home/apollo/gdrive_backup.py "$SECRETS_BLOB" >"$secrets_log_tmp" 2>&1; then
        local secrets_file_id secrets_size
        secrets_file_id=$(grep -oE '[A-Za-z0-9_-]{20,}' "$secrets_log_tmp" | tail -1)
        cat "$secrets_log_tmp" >> "$LOG_FILE"
        rm -f "$secrets_log_tmp"
        secrets_size=$(stat -c %s "$SECRETS_BLOB" 2>/dev/null || echo "?")
        audit_event "gdrive_secrets_success" "Uploaded $(basename "$SECRETS_BLOB") (${secrets_size}B) → drive_file_id=${secrets_file_id}"
        return 0
    fi
    local secrets_err
    secrets_err=$(tail -10 "$secrets_log_tmp" | tr '\n' ' ' | cut -c1-300)
    cat "$secrets_log_tmp" >> "$LOG_FILE"
    rm -f "$secrets_log_tmp"
    telegram_alert "🚨 *Apollo secrets backup FAILED (upload step)*%0A\`\`\`%0A${secrets_err}%0A\`\`\`%0A%0Apg_dump succeeded; encrypted blob exists locally at ${SECRETS_BLOB}."
    audit_event "gdrive_secrets_failed" "Upload failed: ${secrets_err}"
    return 1
}

if [ -r "${BACKUP_PASSPHRASE_FILE:-}" ]; then
    run_secrets_backup || true   # never let secrets failure exit the script
else
    telegram_alert "⚠️ *Apollo secrets backup SKIPPED* — \`BACKUP_PASSPHRASE_FILE\` unset or unreadable. Recreate per \`docs/ops/disaster_recovery.md\` Phase 6."
    audit_event "secrets_backup_skipped" "BACKUP_PASSPHRASE_FILE unset/unreadable; secrets not encrypted this run"
fi

# Step 2 — Google Drive upload
upload_log_tmp=$(mktemp)
if GDRIVE_TOKEN_FILE=/home/apollo/gdrive-token.json \
   GDRIVE_FOLDER_ID=1kXY1LAld1_ZwFa28ZAh3cLVNft7agamb \
   python3 /home/apollo/gdrive_backup.py "$BACKUP_FILE" >"$upload_log_tmp" 2>&1; then
    file_id=$(grep -oE '[A-Za-z0-9_-]{20,}' "$upload_log_tmp" | tail -1)
    cat "$upload_log_tmp" >> "$LOG_FILE"
    rm -f "$upload_log_tmp"
    audit_event "gdrive_backup_success" "Uploaded $(basename "$BACKUP_FILE") (${dump_mb}MB) → drive_file_id=${file_id}"
else
    err_tail=$(tail -15 "$upload_log_tmp" | tr '\n' ' ' | cut -c1-400)
    cat "$upload_log_tmp" >> "$LOG_FILE"
    rm -f "$upload_log_tmp"
    # Distinguish OAuth refresh failure from generic — operator knows to re-auth
    if echo "$err_tail" | grep -q "invalid_grant\|RefreshError"; then
        telegram_alert "🚨 *Apollo gdrive backup FAILED — OAuth token expired*%0AReauthorize: \`python3 scripts/gdrive_backup.py --setup credentials.json\` locally, then scp the new \`gdrive-token.json\` to prod.%0A%0ALocal pg_dump succeeded (${dump_mb}MB). Off-site backup unavailable until re-auth."
    else
        telegram_alert "🚨 *Apollo gdrive backup FAILED*%0A\`\`\`%0A${err_tail}%0A\`\`\`%0A%0ALocal pg_dump succeeded (${dump_mb}MB)."
    fi
    audit_event "gdrive_backup_failed" "Upload failed: ${err_tail}"
    # Don't exit non-zero — local dump succeeded, retention still runs
fi

# Step 3 — Local retention
#   pg_dump:        7 days  (large files, can re-fetch from gdrive if older)
#   secrets blob:  30 days  (tiny encrypted blobs, wider rollback if a cred
#                            rotation breaks something)
find "$BACKUP_DIR" -name 'apollo-*.sql.gz' -mtime +7 -delete 2>>"$LOG_FILE"
find "$BACKUP_DIR" -name 'apollo-secrets-*.tar.gz.gpg' -mtime +30 -delete 2>>"$LOG_FILE"
