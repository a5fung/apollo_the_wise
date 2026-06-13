# Execution / Intelligence split — cutover runbook (#256 W2)

**Status:** the split is BUILT and dormant. Prod runs the single combined
`market-agent` (SERVICE_ROLE unset = `combined`, EXECUTION_MODE=`inprocess`).
This runbook performs the actual cutover to two services. It is **operator-gated**
and must run with **markets CLOSED** (no fills fire off-hours → the #1 risk,
stream double-processing, can't bite during the window).

## What's already in place (no cutover needed)

- `apollo-execution` service defined in `docker-compose.prod.yml` behind
  `profiles: ["split"]` → a bare `docker compose up -d` does **not** start it.
- `execution_client` HTTP transport + `/exec/*` routes (commit 5a), default-off
  (`EXECUTION_MODE=inprocess`). Combined is byte-identical.
- `deploy.sh execution` scope (builds/ups apollo-execution with `--profile split`,
  runs the trade preflights against the `apollo-execution` container).

## Target topology

```
Orchestrator (:8000) ──/task──▶ market-agent  [SERVICE_ROLE=intelligence,
                                               EXECUTION_MODE=http]
                                      │ HTTP /exec/*  (X-Apollo-Secret)
                                      ▼
                                apollo-execution [SERVICE_ROLE=execution]
                                      │  ← the ONLY service with Alpaca creds
                                      ▼
                                Alpaca paper/live
```

`market-agent` KEEPS its name (so the orchestrator `/task` URL
`http://market-agent:8006` stays valid); only its env changes. The execution
container is reached at `http://apollo-execution:8006` (same internal port; the
service name differentiates).

## Cutover steps (markets closed)

### 1. Edit `docker-compose.prod.yml` — flip market-agent to intelligence

Add to the `market-agent` service's `environment:` block (the comment there lists
these verbatim):

```yaml
      SERVICE_ROLE: intelligence
      EXECUTION_MODE: http
      EXECUTION_SERVICE_URL: http://apollo-execution:8006
      ALPACA_PAPER_API_KEY: ""      # creds isolation — overrides .env to blank
      ALPACA_PAPER_SECRET_KEY: ""
      ALPACA_LIVE_API_KEY: ""
      ALPACA_LIVE_SECRET_KEY: ""
```

Commit + push so the prod box can pull (or apply directly on the box if that's
how prod compose drift is handled — see the postgres-ports precedent).

### 2. Run the sequence ON the prod box (order matters — no double execution)

```bash
cd /home/apollo/apollo_the_wise
git pull origin main

# a) Stop combined market-agent FIRST. Now NO service runs execution jobs/streams
#    (safe: markets closed). This is the only moment execution is briefly idle.
docker compose -f docker/docker-compose.prod.yml stop market-agent

# b) Bring up apollo-execution as the SOLE execution owner + full trade preflight.
bash scripts/deploy.sh execution

# c) Recreate market-agent with the new (intelligence) env. It boots creds-free,
#    EXECUTION_MODE=http → reaches apollo-execution (now up).
docker compose -f docker/docker-compose.prod.yml up -d market-agent
```

> Why this order: bringing apollo-execution up **while** market-agent is still
> `combined` would run execution jobs + trade streams in BOTH = double order
> execution / double fill processing. Stopping market-agent first guarantees a
> single execution owner at every instant.

### 3. Verify (the markets-closed soak — reads/boot/reconcile only)

```bash
# both booted, correct roles
docker compose -f docker/docker-compose.prod.yml logs apollo-execution --since 3m | grep -E 'Service role|scheduler started|Execution routes registered'
docker compose -f docker/docker-compose.prod.yml logs market-agent     --since 3m | grep -E 'Service role|scheduler started'
```

Expect: apollo-execution → `SERVICE_ROLE=execution` + `Execution routes registered: 14`;
market-agent → `SERVICE_ROLE=intelligence EXECUTION_MODE=http`.

- intelligence read crossing HTTP: `/positions` or `/status` via Telegram (proxies
  intelligence → execution `/exec/get_all_positions`). A wrong answer that says
  "couldn't reach execution" (ExecutionUnreachable) is the FAIL-LOUD path — never
  a silent flat.
- `order_status_reconcile` + `account_equity_snapshot` run in apollo-execution.
- No `ExecutionUnreachable` in market-agent logs during idle.

**A green soak validates reads / boot / reconcile ONLY.** No fills fire off-hours,
so the handoff/command transport (`trigger_orb_entry`, `submit_9m_day2`,
`execute_partial_exit`) is NOT exercised — that is the Monday smoke.

## Monday live-ORB http flip (SEPARATE operator checkpoint)

The first live ORB session through `EXECUTION_MODE=http` is its own gate. The
handoff path (`ep_scan` on intelligence → `/exec/trigger_orb_entry` → execution's
`_orb_monitor_job`) only runs during market hours. Watch the 9:31 ORB window; if
anything is off, roll back immediately (below). Default-safe pre-Monday state is
to remain split-on-paper or collapse to combined.

## Rollback (instant — collapse to combined)

```bash
docker compose -f docker/docker-compose.prod.yml stop apollo-execution
git revert <cutover commit>   # removes the intelligence env from market-agent
git pull origin main          # on the box
bash scripts/deploy.sh market-agent   # market-agent boots combined/inprocess again
```

Combined/inprocess is byte-identical to pre-split, so rollback restores the exact
prior behavior. Keep this runbook open during the cutover.

## Steady-state footgun (post-cutover)

`apollo-execution` lives behind `profiles: ["split"]`, so once cut over:
- A plain `docker compose up -d` (no `--profile split`) will NOT manage it, and
  `docker compose up -d --remove-orphans` would **kill it**. Always include
  `--profile split` for any compose action that should see it.
- `restart: always` covers a host reboot once the container exists; the risk is a
  muscle-memory `up -d`/`down`. Prefer `bash scripts/deploy.sh execution` for the
  execution service.

## Pre-cutover gate (run locally, free) — DONE 2026-06-13

`python scripts/_w2_role_dryboot.py {execution,intelligence}` dry-boots the real
`start_scheduler()` partition in each split role against real registration:
execution→27, intelligence→42, neither fail-loud guard raises. Re-run if the job
set changes before cutover. (Residual the dry-boot can't cover, left for step 2b
under markets-closed + rollback: real streams starting, the creds bootstrap with
live keys, and intelligence tolerating blanked `ALPACA_*=""`.)

## Open cutover-time items (not yet done)

- Orchestrator `/task` URL: stays `http://market-agent:8006` (service keeps its
  name) — no registry change needed. Confirm prod's `integrations.yaml` override
  still points there post-cutover.
- Telegram confirm-callback routing (plan risk 2): `handle_confirm_callback` is
  still a local shim (deferred from HTTP). Confirm the staged-trade confirm flow
  before the live flip, or keep proposals paused until routed.
- Seam items in the plan BUILD LOG (`ep_scan_start → bar_stream.reset_daily_state`,
  boot-marker `get_account`, `nightly → settle_open_shadows`) — verify on the
  intelligence side during the soak.
