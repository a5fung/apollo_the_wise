# Apollo disaster recovery runbook

> Server dies. Restore on a fresh box. Resume trading as if nothing happened.
> **RTO target**: ~95 min focused work, 3h with slack.
> **RPO**: ~24h (last 02:00 ET pg_dump + secrets blob).

---

## Pre-recovery checklist

Before starting recovery, confirm you have:

- [ ] **GPG passphrase** from Google Password Manager → entry name "Apollo backup passphrase"
- [ ] **Google account** with access to the gdrive folder `1kXY1LAld1_ZwFa28ZAh3cLVNft7agamb`
- [ ] **Hetzner account credentials** (or alternative VPS provider — Ubuntu 22.04+ works)
- [ ] **ssh private key** (or willingness to generate fresh and re-add to GitHub)
- [ ] **Alpaca account web access** for cross-checking positions post-restore

**RPO expectations — read this before assuming "everything is back"**:
Restore returns you to **the last 02:00 ET state**. Anything that happened after that — intraday trades, EP alerts, audit log entries, theme updates — **is gone**. Reconcile today's activity via Alpaca web UI directly. The DB will be at yesterday's EOD; `sync_positions` reconciles open positions against Alpaca's authoritative state.

---

## Phase 0 — During the outage (BEFORE restore)

The most important decisions happen **before** you start restoring.

### If the host died during market hours

1. **Log into Alpaca web UI directly** to confirm broker-side state. Your stops are on Alpaca's servers — they keep working without Apollo.
2. **Decision** — both options are valid:
   - **Leave existing stops in place**. They're broker-durable and will exit positions on stop-hit. Restore can wait until after market close.
   - **Flatten manually** via Alpaca web UI if you're uncertain or want to remove risk during the outage window.
3. **Do NOT enter new trades manually during the outage.** Apollo's `sync_positions` reconciler will see them as unknown and may misroute. If you need to trade, document the trade externally and reconcile by hand post-restore.

### If the host died outside market hours

No action needed. Proceed to Phase 1.

---

## Phase 1 — Provision fresh Hetzner box (~10 min)

1. Log into [console.hetzner.cloud](https://console.hetzner.cloud).
2. **Project** → existing project or new one.
3. **Add server** → CPX21 minimum (4 GB RAM, 2 vCPU, 80 GB SSD).
4. **Image**: Ubuntu 22.04 LTS.
5. **Location**: Ashburn, Virginia (current prod — low-latency to Alpaca/Polygon US-east). Verify with `curl ipinfo.io/<prod-ip>` if uncertain.
   - **Capacity fallback**: Hetzner CPX21 is not always available in Ashburn (caught 2026-05-25 during DR drill). If Ashburn shows the type as locked, pick **Hillsboro, OR** (US-West) instead. Restore mechanics are identical; latency to Alpaca/Polygon (~70-80ms added cross-coast) is acceptable for emergency continuity — flip to Ashburn at next migration window when capacity returns.
6. **SSH key**: upload your laptop's public key. Note: this is the operator key for the restore session.
7. Create server. Note the new **public IPv4** (e.g., `1.2.3.4`).
8. Optional: assign a Floating IP if you want to preserve the old IP — saves the TradingView-webhook-URL-update step.

---

## Phase 2 — Download recovery artifacts (~10 min)

From your laptop:

1. Open https://drive.google.com/drive/folders/1kXY1LAld1_ZwFa28ZAh3cLVNft7agamb
2. Download the **newest** `apollo-YYYYMMDD.sql.gz` (~100 MB).
3. Download the **newest** `apollo-secrets-YYYYMMDD.tar.gz.gpg` (~5 KB).
4. `scp` both to the new box:
   ```bash
   scp apollo-20260524.sql.gz root@<new-ip>:/tmp/
   scp apollo-secrets-20260524.tar.gz.gpg root@<new-ip>:/tmp/
   ```

---

## Phase 3 — Run restore.sh (~40 min, mostly automated)

`ssh root@<new-ip>` then:

```bash
curl -fsSL https://raw.githubusercontent.com/a5fung/apollo_the_wise/main/infra/restore.sh -o /root/restore.sh
chmod +x /root/restore.sh
bash /root/restore.sh
```

At the Phase 4 prompts inside the script:
- **GPG passphrase**: paste from Google Password Manager (no echo).
- **Secrets blob path**: `/tmp/apollo-secrets-YYYYMMDD.tar.gz.gpg`
- **SQL dump path**: `/tmp/apollo-YYYYMMDD.sql.gz`

The script runs 11 idempotent phases:
1. apt install (docker, git, nginx, gnupg, postgresql-client, …)
2. Create `apollo` user (uid 1000)
3. Clone repo from `https://github.com/a5fung/apollo_the_wise.git`
4. Collect operator inputs (passphrase, file paths)
5. Decrypt secrets bundle → place `.env`, `gdrive-token.json`, `apollo.conf`, crontab
6. Reload nginx
7. Bring up postgres + redis (300s pg_isready timeout)
8. Drop+recreate apollo DB, restore from sql.gz
9. Run `scripts/deploy.sh both` — full 5-gate preflight chain
10. Run validation: `readiness_check.py`, `preflight_check.py`, `docker compose ps`
11. Print operator followup checklist

**If a phase fails**: fix the underlying issue (read the error), then re-run. Idempotent — completed phases skip. To force a phase to re-run: `bash /root/restore.sh --force phase_clone` (or any phase name).

---

## Phase 4 — Validation (~10 min)

The script runs `phase_validate` automatically. Cross-check these manually too:

### Automated (already done by restore.sh)

- [x] `readiness_check.py --verbose` exits 0 — no naked positions, no missing reasons, no stale orders
- [x] `preflight_check.py` exits 0 — Alpaca creds valid for both paper and live
- [x] `docker compose ps` — postgres, redis, market-agent, orchestrator, nginx all healthy

### Manual eyeball

- [ ] **Telegram `/status`** — bot responds within 5s; per-mode equity matches Alpaca web UI within $1
- [ ] **Telegram `/trades`** — open position list matches Alpaca portfolio page exactly (symbol + qty)
- [ ] **Telegram `/account`** — daytrade_count and drawdown_breaker state plausible
- [ ] **Manual sync_positions trigger** (iterates both paper + live modes internally):
   ```bash
   docker exec apollo-market python -c "import asyncio; from agents.market_intelligence.broker.order_manager import sync_positions; print(asyncio.run(sync_positions()))"
   ```
   Verify no discrepancy in resulting Telegram alert.
- [ ] **Recent audit log** — no `*_failed` or `*_error` events after restore start:
   ```bash
   docker exec apollo-postgres psql -U apollo -d apollo -c "SELECT event_type, created_at FROM mi_audit_log WHERE created_at > NOW() - INTERVAL '1 hour' ORDER BY created_at DESC LIMIT 20;"
   ```

---

## Phase 5 — External re-wiring (~15 min)

### TradingView webhook URL

If the new server has a **different public IP** (skip if you assigned a Floating IP in Phase 1):

1. Open https://tradingview.com → your alert templates.
2. For each alert that targets Apollo, update the webhook URL from `http://<old-ip>/tradingview/` to `http://<new-ip>/tradingview/`.
3. The `TRADINGVIEW_WEBHOOK_SECRET` from `.env` survives — no secret rotation needed.

### GitHub deploy key (optional)

The repo is public, so `git clone` works without auth. **Only needed if** the repo goes private in the future or you want to push from prod.

### DNS update (optional)

If you have a DNS A record pointing to the old IP, update it to the new IP.

---

## Phase 6 — Recreate backup-passphrase file (CRITICAL, ~2 min)

The encrypted secrets bundle **deliberately excludes** the backup passphrase (it would defeat the purpose). On the new box, recreate it from Google Password Manager:

```bash
ssh apollo@<new-ip>
umask 077
printf '%s' '<paste passphrase from Google PW Manager>' > /home/apollo/.backup-passphrase
chmod 400 /home/apollo/.backup-passphrase
chown apollo:apollo /home/apollo/.backup-passphrase
```

Note: `printf '%s'` (no `-n` needed) avoids a trailing newline.

**Without this step**: tomorrow's 02:00 ET secrets backup will Telegram `⚠️ Apollo secrets backup SKIPPED — BACKUP_PASSPHRASE_FILE unset or unreadable` and the 04:33 ET health-check will alert STALE within 36h.

Verify the crontab line includes the env var:
```bash
crontab -u apollo -l | grep backup.sh
# Expect: 0 2 * * * BACKUP_PASSPHRASE_FILE=/home/apollo/.backup-passphrase /home/apollo/backup.sh
```

---

## First-night verification (next day)

At ~02:05 ET the day after restore:

```bash
docker exec apollo-postgres psql -U apollo -d apollo -c "
SELECT event_type, summary, created_at
  FROM mi_audit_log
 WHERE event_type LIKE 'gdrive%'
   AND created_at > NOW() - INTERVAL '4 hours'
 ORDER BY created_at DESC;"
```

Expect **two** rows:
- `gdrive_backup_success` — pg_dump uploaded
- `gdrive_secrets_success` — encrypted secrets bundle uploaded

If both present and the 04:33 ET `_backup_health_check_job` did not Telegram, the system is fully back to steady state.

---

## Time budget

| Phase | Time |
|---|---|
| 0. During outage (decision + Alpaca check) | 5 min |
| 1. Provision Hetzner box | 10 min |
| 2. Download recovery artifacts | 10 min |
| 3. Run restore.sh | 40 min |
| 4. Validation (manual eyeball) | 10 min |
| 5. External rewiring | 15 min |
| 6. Recreate backup-passphrase file | 2 min |
| **Total focused work** | **~95 min** |
| **Slack for surprises** | ~85 min |
| **Wall-clock budget** | **~3 hours** |

---

## Initial setup (one-time, on existing prod host)

Sequence to enable the encrypted-secrets backup going forward. **Do this once** before relying on disaster recovery.

### Step 1 — Generate passphrase

In Google Password Manager → generate a strong 40+ character passphrase → save under "Apollo backup passphrase". Make sure Chrome sync is enabled so you have it on other devices.

### Step 2 — Install passphrase file on prod

```bash
ssh apollo@87.99.134.162
umask 077
printf '%s' '<paste passphrase>' > /home/apollo/.backup-passphrase
chmod 400 /home/apollo/.backup-passphrase
chown apollo:apollo /home/apollo/.backup-passphrase
ls -la /home/apollo/.backup-passphrase
# Expect: -r-------- 1 apollo apollo  <NN>  ...
```

### Step 3 — Update crontab to pass the env var

```bash
crontab -e -u apollo
```

Change the backup line from:
```
0 2 * * * /home/apollo/backup.sh
```

to:
```
0 2 * * * BACKUP_PASSPHRASE_FILE=/home/apollo/.backup-passphrase /home/apollo/backup.sh
```

Why this placement (not bashrc, not inside backup.sh): minimal exposure surface — only the cron-launched backup.sh sees the variable.

### Step 4 — Push the updated backup.sh to prod

From your laptop:
```bash
scp scripts/backup.sh apollo@87.99.134.162:/home/apollo/backup.sh
ssh apollo@87.99.134.162 "chmod +x /home/apollo/backup.sh && bash -n /home/apollo/backup.sh && echo OK"
```

### Step 5 — Manual test run

```bash
ssh apollo@87.99.134.162
sudo -u apollo BACKUP_PASSPHRASE_FILE=/home/apollo/.backup-passphrase /home/apollo/backup.sh
# Expect: ~30s. No errors.
```

Verify both files land in gdrive:
- https://drive.google.com/drive/folders/1kXY1LAld1_ZwFa28ZAh3cLVNft7agamb
- Should see today's `apollo-YYYYMMDD.sql.gz` AND `apollo-secrets-YYYYMMDD.tar.gz.gpg`.

### Step 6 — HARD GATE: end-to-end decryption roundtrip on laptop

**Do NOT skip this.** Apply `feedback_ground_truth_verification.md` discipline — prove recoverability against the actual encrypted bytes before depending on them.

Download the new secrets blob from gdrive to laptop, then:
```bash
gpg --decrypt apollo-secrets-YYYYMMDD.tar.gz.gpg | tar -tzf -
# Enter passphrase when prompted.
# Expect output listing: ./.env  ./gdrive-token.json  ./apollo.conf  ./crontab.txt  ./MANIFEST.txt
```

If decryption fails:
- Wrong passphrase? Try again from Google PW Manager.
- Corrupted upload? Re-run backup.sh, re-download, re-test.
- GPG version mismatch? Unlikely with AES256 symmetric — verify your gpg version supports it.

**Do not proceed to rely on the nightly backup until this passes.** Without verification, the encrypted blob might be unrecoverable.

---

## Related docs

- [`gdrive_backup_recovery.md`](gdrive_backup_recovery.md) — OAuth token recovery if `gdrive_backup_failed` events surface with `invalid_grant`
- [`CLAUDE.md`](../../CLAUDE.md) — broader project context, deploy procedure
