# Monday 2026-06-15 — execution/intelligence split go-live playbook

**Why this exists:** the #256 W2 split was cut over 2026-06-13 (markets closed) and
is live on paper as two services. Everything a closed market can validate is green
(boot, reads, reconcile, streams, orchestrator `/task`). The ONE untested path is
the live ORB handoff during market hours:

```
ep_scan (intelligence)  →  trigger_orb_entry  →  HTTP /exec/trigger_orb_entry
                                                  →  execution._orb_monitor_job  →  bracket order
```

Monday's 9:31 ET ORB window is the first time that fires for real. This playbook is
the pre-open check, what to watch, and the rollback.

**Times (operator is PDT; tape is ET):** ORB window **9:31 ET = 6:31 PDT**. Pre-open
check fires ~**5:57 PDT (8:57 ET)** via the scheduled wake-up.

**Current live topology:** `apollo-market` = intelligence (SERVICE_ROLE=intelligence,
EXECUTION_MODE=http, no creds, 42 jobs) · `apollo-execution` = execution
(SERVICE_ROLE=execution, creds + streams, 27 jobs, profile:split).

---

## A. Pre-open check (~5:57 PDT / 8:57 ET) — runs automatically, ~30 min of buffer

Run these against the prod box (`ssh apollo@87.99.134.162`,
`/home/apollo/apollo_the_wise`). PASS = all green; any red → go to §C (rollback)
with time to spare before 6:31 PDT.

1. **Both services healthy:**
   ```bash
   docker ps --format '{{.Names}} | {{.Status}}' | grep -E 'apollo-market|apollo-execution'
   ```
   PASS: both `Up ... (healthy)`.

2. **HTTP transport live (read-only — no mutation):**
   ```bash
   ssh ... apollo@... 'docker exec -i apollo-market python -' <<'PYEOF'
   import asyncio
   from agents.market_intelligence import execution_client as ec
   r = asyncio.run(ec.get_all_positions())
   print("HTTP get_all_positions ->", type(r).__name__, "len=", len(r))
   s = asyncio.run(ec.get_stream_status())
   print("STREAM healthy=", s.get("healthy"), "modes=", s.get("modes"))
   PYEOF
   ```
   PASS: `get_all_positions` returns a **list** (NOT `ExecutionUnreachable`);
   `STREAM healthy= True`.

3. **Execution role + streams in logs (overnight drift check):**
   ```bash
   docker logs --since 12h apollo-execution 2>&1 | grep -icE 'ExecutionUnreachable|Traceback|CRITICAL|stream.*disconnect'
   docker logs --since 12h apollo-market 2>&1 | grep -icE 'ExecutionUnreachable|Traceback|CRITICAL'
   ```
   PASS: both `0` (or only benign reconnects on execution).

**If all PASS:** report green to the operator and stand by for §B.
**If any RED:** report immediately + recommend §C rollback (≈2 min, well before 6:31 PDT).

---

## B. The 9:31 ET (6:31 PDT) ORB window — watch the handoff

The handoff only fires if an EP HIGH lands in the ORB window. Watch BOTH services:

- **Intelligence side** (`apollo-market`) — the trigger is sent:
  ```bash
  docker logs --since 10m apollo-market 2>&1 | grep -iE 'triggering ORB entry via execution facade|trigger_orb_entry|ExecutionUnreachable'
  ```
  Expect (when a HIGH fires): `Post-open new HIGHs ... — triggering ORB entry via execution facade`.
  If `ExecutionUnreachable` appears here: it means the HTTP call to execution did
  not return cleanly — it does **NOT** by itself mean the order didn't fire.
  `trigger_orb_entry` runs the full `_orb_monitor_job` ON execution (which can place
  the bracket) before responding; the order path has a generous 180s read timeout
  (vs 15s for reads) specifically so a slow-but-successful submit doesn't false-raise.
  So on `ExecutionUnreachable`, **execution's own logs are the authority** — go read
  them (next bullet) before deciding. Connect-refused (execution down) is the only
  variant that is unambiguously "didn't fire" → §C.

- **Execution side** (`apollo-execution`) — THE authority on what actually happened:
  ```bash
  docker logs --since 10m apollo-execution 2>&1 | grep -iE 'orb_monitor|ORB|bracket|submit|ACTION_AUTO_ENTERED|order placed'
  ```
  Expect: the orb monitor runs + (if a candidate passes) a bracket order is submitted
  on the paper account. If a bracket WAS placed here, the trade is live regardless of
  what the intelligence side logged — confirm it landed once in `mi_live_trades`
  (below) and do NOT roll back on the intelligence-side `ExecutionUnreachable` alone.

**Success criterion:** an EP HIGH in the window produces a bracket submit on the
**execution** side (the order-of-record), reconciled exactly once in `mi_live_trades`.
The intelligence trigger log should accompany it with NO `ExecutionUnreachable`; if
that warning does appear, reconcile against the execution log + `mi_live_trades`
(fired-but-slow vs genuinely-unreachable) before acting. A **quiet** window (no HIGH)
is not a failure — it just doesn't exercise the path; re-check the next session.

**Cross-check (after the window):** the trade lands in `mi_live_trades` exactly once
(not zero, not double — the double-processing guard). The order-status reconcile
(execution, every 15 min) and the EOD recap will surface it.

---

## C. Rollback — collapse to combined (PINNED to the validated SHA)

Run if any pre-open check reds, or the 9:31 handoff misfires. Markets-open rollback
is safe (it returns to the proven single process; do it between ORB attempts if mid-session).

**Why pinned, not `git pull origin main`** (advisor 2026-06-14): `deploy.sh` always
`git pull origin main` ([1/5]), so it would rebuild combined from whatever HEAD is at
rollback time — including any same-day work that was verified in the SPLIT but **never
booted in combined**. The rollback target must be a commit *validated combined-safe*, so we
pin a SHA instead. main can then advance freely without endangering the fallback.

```bash
cd /home/apollo/apollo_the_wise
# 1. PIN to the validated combined-safe commit — do NOT `git pull origin main`.
git fetch origin
git stash    # only if the working tree is dirty
git checkout f116fae    # ⟵ PINNED SHA — 2026-06-14 EOD (command-merge + CLASS B, all
                        #    deployed + verified in the split, combined-safe, boot-path-clean).
                        #    UPDATE this SHA if more combined-safe work ships+verifies before Monday.
# 2. Flip market-agent to combined: remove the intelligence env block
#    (SERVICE_ROLE/EXECUTION_MODE/EXECUTION_SERVICE_URL/ALPACA_* "") from the
#    market-agent service in docker/docker-compose.prod.yml, then stop execution:
docker compose -f docker/docker-compose.prod.yml stop apollo-execution
# 3. Rebuild market-agent as combined (owns everything again) — build the PINNED code,
#    NOT a fresh pull:
docker compose -f docker/docker-compose.prod.yml up -d --build market-agent
# 4. Confirm healthy — the safeguard preflight PASSES on combined (has creds):
docker exec apollo-market python -m scripts.preflight_check
```

Verify: `apollo-market` boots `SERVICE_ROLE=combined`, "all 69 jobs kept", paper equity
prints, healthy, and step 4's preflight PASSES (combined has creds — unlike the creds-less
intelligence role, which false-fails it; `execution_split_cutover.md` "deploy ergonomics" /
#278). Combined-from-the-pinned-SHA = the validated fallback. A clean preflight is the
normal, expected signal that combined is back.

---

## D. After a clean session

- Confirm the ORB trade (if any) reconciled once in `mi_live_trades`.
- Update `docs/ops/execution_split_cutover.md` status → "live-ORB http flip VERIFIED".
- The split's remaining follow-ons (plan): W3 staging, W4 hardening (DR runbook for
  two services, per-service uptime checks, #258 db.py split).
