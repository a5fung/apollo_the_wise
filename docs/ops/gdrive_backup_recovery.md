# Google Drive backup — recovery runbook

## Current state (as of 2026-05-23)

- Local pg_dump runs nightly at 02:00 ET via host cron — **WORKING**. 7 days retained in `/home/apollo/backups/`.
- Off-site Google Drive upload has been **FAILING since 2026-03-29** with `invalid_grant: Bad Request` — OAuth refresh token revoked.
- Root cause likely: Google's policy that refresh tokens for OAuth apps in **Testing** mode expire after 7 days. The script ran 2026-03-22 → 2026-03-28 (6 days) then died — fits exactly.

## Recovery — 3 steps (interactive, browser required)

### Step 1 — Re-generate OAuth token locally

You'll need the original `credentials.json` (OAuth client ID JSON download from Google Cloud Console). If lost, recreate at https://console.cloud.google.com/apis/credentials → "OAuth 2.0 Client IDs" → Desktop app.

```bash
# On local machine:
cd Apollo_Assistant
python3 scripts/gdrive_backup.py --setup credentials.json
# Browser opens; consent to drive.file scope.
# Generates gdrive-token.json in current dir.
```

### Step 2 — Push the new token to prod

```bash
scp gdrive-token.json apollo@87.99.134.162:/home/apollo/gdrive-token.json
ssh apollo@87.99.134.162 'chmod 600 /home/apollo/gdrive-token.json'

# Verify the upload manually:
ssh apollo@87.99.134.162 'GDRIVE_TOKEN_FILE=/home/apollo/gdrive-token.json GDRIVE_FOLDER_ID=1kXY1LAld1_ZwFa28ZAh3cLVNft7agamb python3 /home/apollo/gdrive_backup.py /home/apollo/backups/apollo-20260524.sql.gz'
# Expect: "Uploaded apollo-20260524.sql.gz → <fileId>"
```

### Step 3 — Move app to Production mode (prevents the 7-day expiry trap)

In Google Cloud Console:

1. Open https://console.cloud.google.com/apis/credentials/consent
2. Under "Publishing status" — switch from **Testing** to **In production**
3. The `drive.file` scope is **non-sensitive** (per [Google's classification](https://developers.google.com/identity/protocols/oauth2/production-readiness#unrestricted)) — does NOT require app verification. The app only writes to its own folder; can't read other user files.
4. Confirm the publishing-status indicator now reads "In production". Refresh token lifetime becomes indefinite (subject to standard 6-month inactivity rule).

If the app is left in Testing mode, you'll have to re-run Step 1 every 7 days. Step 3 is the permanent fix.

## What's been wired around the OAuth fix (autonomous, already deployed)

Shipped 2026-05-23 commit `<filled at commit>`:

- `scripts/backup.sh` (deployed to `/home/apollo/backup.sh`) — rewritten with:
  - Per-step failure detection (pg_dump failure was previously silently masked by `| gzip`)
  - Telegram alert on gdrive upload failure, with OAuth-specific message when the error is `invalid_grant` / `RefreshError`
  - Audit row written to `mi_audit_log` (`gdrive_backup_success` / `gdrive_backup_failed`)
- `agents/market_intelligence/scheduler.py::_backup_health_check_job` — daily 04:33 ET APScheduler job. Telegrams if no `gdrive_backup_success` event in the last 36h. Backstops the case where the host cron itself stops firing (host reboot, cron daemon down).

After Step 2 above, the next 02:00 ET cron run will (a) successfully upload, (b) write `gdrive_backup_success` audit row, (c) the 04:33 health check sees it within 36h, no alert fires. Steady state restored.

## Verification after recovery

```bash
# Check audit row was written:
ssh apollo@87.99.134.162 "docker exec apollo-postgres psql -U apollo -d apollo -c \"SELECT created_at, summary FROM mi_audit_log WHERE event_type='gdrive_backup_success' ORDER BY created_at DESC LIMIT 3;\""

# Check Google Drive folder:
# Open https://drive.google.com/drive/folders/1kXY1LAld1_ZwFa28ZAh3cLVNft7agamb
# Most recent file should be today's date.
```
