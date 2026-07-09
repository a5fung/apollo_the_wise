# Secrets Rotation Runbook (#423 · FL-5)

**Rotate any Apollo credential from this doc alone.** All secrets live in one file on the prod
host — `/home/apollo/apollo_the_wise/.env` (chmod 600) — and ride the nightly GPG-encrypted
secrets bundle to gdrive for DR (`backup.sh` step 1b). `shared/secrets.py` reads them from the
process environment, injected from `.env` at **container create time**.

---

## The universal 5-step pattern (every credential)

1. **Generate** the new value at the provider (or `openssl rand -hex 32` for internal secrets).
2. **Edit** `/home/apollo/apollo_the_wise/.env` on the prod host — replace the old value. Keep the
   file `chmod 600`.
3. **Recreate** the affected service container(s) so they re-read `.env`:
   ```bash
   cd /home/apollo/apollo_the_wise
   docker compose -f docker/docker-compose.prod.yml up -d <service>   # up -d, NOT restart
   ```
   ⚠️ **`docker compose restart` does NOT reload `.env`** — env is injected only at container
   CREATE. Use `up -d` (recreates with the new env) or `bash scripts/deploy.sh <scope>`.
   If unsure which service reads a credential, `up -d` **all** services — they share one `.env`,
   so recreating extras is harmless (no code change → same image, just re-injected env).
4. **Verify** (per-credential check below) — confirm the new credential works, the old is dead.
5. **Re-back-up the secret** so DR doesn't restore the OLD value:
   ```bash
   bash scripts/backup.sh          # regenerates apollo-secrets-<date>.tar.gz.gpg with the new .env
   ```
   Then confirm `_backup_health_check_job` (04:33 ET) stays quiet (bundle fresh). **Skipping this
   means a host loss recovers the stale credential.**

---

## Per-credential reference

| Credential (env var) | Provider — where to regenerate | Service(s) to `up -d` | Verify |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | @BotFather → `/revoke` → new token | orchestrator, market-agent | any `/status` in Telegram replies |
| `ANTHROPIC_API_KEY` | console.anthropic.com → API keys | orchestrator, market-agent | an EP grade / theme validation runs (check `mi_audit_log` for a fresh grade; no `anthropic_*` error) |
| `POLYGON_API_KEY` | polygon.io dashboard → API keys | market-agent | next 5-min EP scan pulls a snapshot (no `polygon` error in logs) |
| `FMP_API_KEY` | site.financialmodelingprep.com → dashboard | market-agent | an FMP profile fetch succeeds (no `fmp` error) |
| `PERPLEXITY_API_KEY` | perplexity.ai → API settings | market-agent | a catalyst discovery/validation runs (no `perplexity` error) |
| `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_SECRET_KEY` | paper-api.alpaca.markets → API keys (paper) | **execution + market-agent** | boot `dual_account_boot_verified` audit; `get_account('paper')` succeeds |
| `ALPACA_LIVE_API_KEY` / `ALPACA_LIVE_SECRET_KEY` | api.alpaca.markets → API keys (live) | **execution + market-agent** | boot `dual_account_boot_verified`; `get_account('live')` succeeds |
| `POSTGRES_PASSWORD` | self (change in Postgres, see below) | **all** (postgres, market-agent, execution, orchestrator) | every service reconnects; no `password authentication failed` |
| `REDIS_PASSWORD` | self (`redis.conf` / compose) | **all** | services reconnect to Redis |
| `INTERNAL_API_SECRET` | `openssl rand -hex 32` | orchestrator + market-agent (both must match) | orchestrator→market `POST /task` returns 200 (not 401) |
| `TRADINGVIEW_WEBHOOK_SECRET` | `openssl rand -hex 32` | orchestrator | a TradingView test webhook is accepted |
| gdrive OAuth (`gdrive-token.json`) | Google Cloud OAuth | (backup cron only) | **see `docs/ops/gdrive_backup_recovery.md`** — separate flow |

---

## Special cases

### Dual-account Alpaca (both pairs must stay valid)
`ENABLE_LIVE_MODE=true` (prod default) **boot-blocks** the agent if EITHER the paper OR the live
key pair is missing/invalid (`agent.py::_bootstrap_alpaca_credentials`). So:
- Rotate **one pair at a time**; keep the other pair valid.
- After `up -d execution market-agent`, confirm the `dual_account_boot_verified` audit row (not
  `dual_account_boot_failed`) before considering the rotation done.
- `preflight_check.py` (chained in `deploy.sh`) walks every live strategy through `_check_safeguards`
  — a bad key surfaces there as an auth failure, failing the deploy loudly. Deploying via
  `deploy.sh both` + `deploy.sh execution` is the safest way to rotate Alpaca keys.

### POSTGRES_PASSWORD (touches every service + the DB itself)
1. `ALTER USER apollo WITH PASSWORD '<new>';` inside the running postgres (`docker exec apollo-postgres psql -U apollo`).
2. Update `POSTGRES_PASSWORD` in `.env`.
3. `up -d` **postgres first** (it reads the password for healthchecks/init), then market-agent,
   execution, orchestrator.
4. Verify: `docker ps` all healthy; no `password authentication failed` in any service log.

### INTERNAL_API_SECRET (must match on both sides)
Orchestrator sends `X-Apollo-Secret: <INTERNAL_API_SECRET>` on `POST /task`; the market-agent
validates it. Both containers read the SAME env var — recreate **both** in the same rotation or
orchestrator→market calls 401.

---

## After ANY rotation — the checklist
- [ ] `.env` updated (still `chmod 600`).
- [ ] Affected service(s) recreated with `up -d` (not `restart`); `docker ps` all healthy.
- [ ] Per-credential verification passed; the OLD credential is confirmed dead.
- [ ] `bash scripts/backup.sh` re-run so the encrypted bundle carries the new secret.
- [ ] No new `*_error` / auth-failure rows in `mi_audit_log` for that service.

> DR note: the encrypted secrets bundle is the DR source of truth (`infra/restore.sh` Phase reads
> it). A rotated secret that was never re-backed-up is silently lost on a host rebuild — step 5 is
> not optional.
