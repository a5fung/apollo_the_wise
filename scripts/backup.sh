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

# Shared telemetry helpers (log / telegram_alert / audit_event) — one canonical
# copy in the repo; the per-script copies drifted within a day (d3 /simplify
# 2026-07-05). telegram_alert now LOGS send failures instead of eating them.
# shellcheck disable=SC1091
. /home/apollo/apollo_the_wise/infra/ops_lib.sh || {
    echo "$(date -u +%FT%TZ) FATAL: ops_lib.sh missing — run git pull in the app dir" >> "$LOG_FILE"; exit 1; }

# Step 1 — pg_dump
if ! docker exec apollo-postgres pg_dump -U apollo apollo 2>>"$LOG_FILE" | gzip > "$BACKUP_FILE"; then
    err_tail=$(tail -10 "$LOG_FILE" 2>/dev/null | tr '\n' ' ' | cut -c1-300)
    telegram_alert "🚨 *Apollo backup FAILED* (pg_dump)"$'\n```\n'"${err_tail}"$'\n```'
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
        # Cluster roles incl. password hashes (#256 W4, 2026-07-05) — pg_dump
        # never recreates roles; restore.sh pre-creates EXPECTED_ROLES but that
        # can't restore role PASSWORDS (dashboard_ro login died after a real DR
        # until reset). Hashes are secrets -> this belongs in the ENCRYPTED
        # bundle, not beside the plaintext dump.
        docker exec apollo-postgres pg_dumpall -U apollo --roles-only \
            > "$bundle_dir/roles.sql" 2>>"$LOG_FILE" || true
        if [ ! -s "$bundle_dir/roles.sql" ]; then
            # d3 review: the redirect creates a 0-byte file even when pg_dumpall
            # fails; bundling it would false-positive Phase 8's "Applied
            # roles.sql" during a REAL DR. Alert + drop the empty file so
            # restore.sh takes its explicit missing-roles.sql warning path.
            rm -f "$bundle_dir/roles.sql"
            telegram_alert "⚠️ *Apollo backup: roles.sql dump came back EMPTY* — bundle ships without it; DR falls back to EXPECTED_ROLES pre-create (role passwords need manual reset). Check pg_dumpall errors in the backup log."
            audit_event "backup_roles_dump_empty" "pg_dumpall --roles-only produced no output; roles.sql omitted from tonight's bundle"
        fi
        {
            printf 'apollo-secrets bundle %s\n' "$(date -Iseconds)"
            printf 'staged in: %s\n' "$stage_root"
            printf 'includes (best-effort):\n'
            ls -la "$bundle_dir" | awk 'NR>1 {print "  " $NF " (" $5 " bytes)"}'
        } > "$bundle_dir/MANIFEST.txt"
    } 2>>"$LOG_FILE"

    local bundle_files=(.env gdrive-token.json apollo.conf crontab.txt MANIFEST.txt)
    [ -s "$bundle_dir/roles.sql" ] && bundle_files+=(roles.sql)
    if ! tar -czf "$bundle_dir/bundle.tar.gz" -C "$bundle_dir" \
            "${bundle_files[@]}" 2>>"$LOG_FILE" || \
       ! gpg --batch --yes \
           --passphrase-file "$BACKUP_PASSPHRASE_FILE" \
           --symmetric --cipher-algo AES256 \
           -o "$SECRETS_BLOB" "$bundle_dir/bundle.tar.gz" 2>>"$LOG_FILE"; then
        local bundle_err
        bundle_err=$(tail -10 "$LOG_FILE" | tr '\n' ' ' | cut -c1-300)
        telegram_alert "🚨 *Apollo secrets backup FAILED (encrypt step)*"$'\n```\n'"${bundle_err}"$'\n```'
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
    telegram_alert "🚨 *Apollo secrets backup FAILED (upload step)*"$'\n```\n'"${secrets_err}"$'\n```\n'"pg_dump succeeded; encrypted blob exists locally at ${SECRETS_BLOB}."
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
        telegram_alert "🚨 *Apollo gdrive backup FAILED — OAuth token expired*"$'\n'"Reauthorize: \`python3 scripts/gdrive_backup.py --setup credentials.json\` locally, then scp the new \`gdrive-token.json\` to prod."$'\n'"Local pg_dump succeeded (${dump_mb}MB). Off-site backup unavailable until re-auth."
    else
        telegram_alert "🚨 *Apollo gdrive backup FAILED*"$'\n```\n'"${err_tail}"$'\n```\n'"Local pg_dump succeeded (${dump_mb}MB)."
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
