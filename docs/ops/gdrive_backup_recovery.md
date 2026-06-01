# Google Drive backup — recovery runbook

## Current state (as of 2026-05-23)

- Local pg_dump runs nightly at 02:00 ET via host cron — **WORKING**. 7 days retained in `/home/apollo/backups/`.
- Off-site Google Drive upload has been **FAILING since 2026-03-29** with `invalid_grant: Bad Request` — OAuth refresh token revoked.
- Root cause: Google's policy that refresh tokens for OAuth apps in **Testing** mode expire after 7 days. The script ran 2026-03-22 → 2026-03-28 (6 days) then died — fits exactly.
- **Update 2026-06-01 — recurred, root-caused, resolved.** The app was *already* "In production" (verified in the new Google Auth Platform UI: **Audience** tab → Publishing status "In production"; project `apollo-assistant-490120`, number `450128935042`, scope `drive.file` non-sensitive). The token *still* died at exactly 7 days (minted 5/23 20:43 → died 5/31). **Cause = token vintage, not app status:** a refresh token inherits the expiry policy in force *when it is minted*; the 5/23 token was generated before the Production publish took effect on it, so it kept the legacy 7-day clock — and publishing does NOT retroactively heal an already-issued token. Fixed by a one-time re-auth *while in Production* (new token = permanent). The ordering trap below is what made the recovery itself mint a doomed token. Off-site upload confirmed working again 2026-06-01 (`apollo-20260601.sql.gz`).

## Recovery — 3 steps (interactive, browser required)

> ⚠️ **ORDER MATTERS — confirm the app is "In production" (Step 3) BEFORE you re-auth (Step 1).** A refresh token inherits the token-expiry policy in force *at the moment it is minted*. Re-authing while the app is still in Testing bakes in the 7-day expiry **even if you publish to Production seconds later** — publishing does not retroactively heal an already-minted token. This is exactly what bit us twice (March, and again 2026-05-31): the recovery token itself was minted pre-publish and died at day 7 despite the app reading "In production." If the app is already in Production, just do Step 1 — the new token is permanent.

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

Two separate commands (don't chain with `+` — that's a literal filename to scp):

```bash
scp gdrive-token.json apollo@87.99.134.162:/home/apollo/gdrive-token.json
ssh apollo@87.99.134.162 "chmod 600 /home/apollo/gdrive-token.json"
```

Then verify the upload manually (single command, all one line):

```bash
ssh apollo@87.99.134.162 "GDRIVE_TOKEN_FILE=/home/apollo/gdrive-token.json GDRIVE_FOLDER_ID=1kXY1LAld1_ZwFa28ZAh3cLVNft7agamb python3 /home/apollo/gdrive_backup.py /home/apollo/backups/apollo-20260524.sql.gz"
```

Expected output: `Uploaded apollo-20260524.sql.gz → <fileId>`. If you see a Google file ID, the OAuth flow worked and tonight's 02:00 ET cron will succeed.

### Step 3 — Publish app to Production (do this FIRST — prevents the 7-day expiry trap)

In Google Cloud Console. NOTE: the old "OAuth consent screen" page is now the **Google Auth Platform** UI, and publishing status moved to the **Audience** tab — this reorg is how the publish slips onto the wrong project / gets missed.

1. Open https://console.cloud.google.com and select the project whose **number** matches the OAuth client: project `apollo-assistant-490120`, number `450128935042`. (Confirm under the **Clients** tab — the OAuth client ID starts with `450128935042`.)
2. Open the **Audience** tab (left sidebar) → **Publishing status**.
3. If it reads **Testing**, click **Publish app** → confirm it flips to **In production**.
4. The `drive.file` scope is **non-sensitive** (per [Google's classification](https://developers.google.com/identity/protocols/oauth2/production-readiness#unrestricted)) — does NOT require app verification. The app only writes to its own folder; can't read other user files.
5. Refresh-token lifetime is now indefinite (subject to the standard 6-month inactivity rule) — **but only for tokens minted from this point on.** Then do Step 1 to mint a fresh permanent token.

If the app is left in Testing mode, every minted token expires after 7 days. Publishing is the permanent fix — but only for tokens minted *after* publishing, so always finish recovery with a re-auth (Step 1). See the ordering warning above.

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
