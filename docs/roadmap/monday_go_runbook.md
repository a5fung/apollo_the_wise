# MAGNA53 real-money launch runbook — TWO-PHASE (Mon 6/22 stage → mid-week go-live)

**Purpose:** the turnkey execution sequence for the MAGNA53 real-money cutover, **every step
traced to code** so nothing is improvised. This is the EXECUTION surface; the GO/NO-GO DECISION
lives in `go-no-go-evidence-2026-06-22.md`. Validated 2026-06-20 (#303); **restructured 2026-06-21
into two phases** once funding timing was known; **advisor-reviewed + code-verified 2026-06-21** —
caught two launch-blockers (the legacy paper-cred boot-block in P1.2; the cached-registry restart in
P2.1) + confirmed `/pause` is cache-independent.

## ⚡ Current situation (2026-06-21) — why this is TWO phases, not one Monday event
- ✅ **Live Alpaca account CREATED** (operator, 6/21) → live API keys can be generated + wired now.
- ⏳ **Funding INITIATED Sat night 2026-06-20** (ACH). Settles in **a few business days — expect
  ~Wed 6/24–Thu 6/25**; gate on the **actual** F4 read (below), NOT the estimate.
- 🔑 **Consequence:** sizing reads **live SETTLED equity** (`order_manager.py:112/124`), so **no
  real trade can fire until the cash clears** — Monday is too early regardless of what we flip.

So we split the launch:

| Phase | When | What happens | Real money at risk? |
|---|---|---|---|
| **PHASE 1 — VALIDATE + STAGE** | **Mon 6/22** | wire live creds · deploy · preflight · `/pause` · `#346` shadow verify — magna53 staged at **`live_real_enabled=FALSE`** (🟡 STAGED-PAPER proposals) | **NO** — zero real-$ exposure, no funding dependency |
| **PHASE 2 — ARM REAL MONEY** | **mid-week, the day F4 funds SETTLE (~Wed 6/24+)** | flip the one real-money switch **`live_real_enabled=TRUE`** · confirm `/status` buying power · first real auto-entry + **stop-leg watch** | **YES** — first real fills |

**Why split:** Phase 1 de-risks the never-run live path (the live-creds boot + `get_account('live')`
preflight — the **2026-05-13 outage class**) with **no money at stake**. Phase 2 arms the real-money
switch **only once the cash is actually there**, so "live" always means "can actually trade."

> ⚠️ **The flip is NOT a single switch.** Full path = (1) creds+env in `.env`, (2) a `mi_strategies`
> UPDATE, (3) deploy, (4) preflight, (5) `/pause`. Three of the four strategy-row fields
> (`live_real_enabled`, `position_size_multiplier`, `max_concurrent_positions`) are **SQL-only** —
> no Telegram command (deliberate: the real-money gate is not a casual `/strategy` action).

---

## F. Funding gate — the clock that sets Phase 2's date

**Why it gates everything (code):** sizing reads **live, settled equity** — `order_manager.py:112`
`risk_dollars = equity × risk_pct`, `:124` `max_position = equity × 0.20`. **$0 settled → 0 shares
→ `setup:size_too_small` skip** (fail-safe, no error, no naked risk, but **no real trade**).
Partially settled → it trades but sized off the smaller balance. So real fills require **settled
buying power ≥ start size** before any ORB window — and that's a days-long ACH clock.

**State tracker — current marks (update as each lands):**
```
[x] F1 — Live account OPENED + APPROVED                         (2026-06-21)
[x] F2 — Transfer INITIATED (ACH)                               (Sat night 2026-06-20)
[ ] F3 — Deposit POSTED to the live account                     (~a few business days)
[ ] F4 — Buying power SETTLED & AVAILABLE >= ~$5,000  <<< THIS DATE = Phase 2's trigger
[ ] F5 — account_blocked = false AND trading_blocked = false    (new accounts can carry a hold)
```

**How to check — authoritative = the Alpaca LIVE dashboard** (`app.alpaca.markets`, LIVE not paper):
the **Cash / Buying Power** figure is the source of truth for F3/F4; Account → Status for F5. After
Phase 1's deploy, Apollo's own confirming read is **`/status`** (the `💰 LIVE-$` block).

> ⏸️ **HARD GATE: Phase 2 does NOT start until F4 is green** (buying power settled ≥ start size)
> **AND F5 clear.** Until then magna53 stays at `live_real_enabled=FALSE` from Phase 1 — staged,
> safe, no real money. Check F4 daily from ~6/24; the day it's green is the day you run Phase 2.

---
---

# ▶ PHASE 1 — Monday 2026-06-22 (VALIDATE + STAGE · no real money)

Goal: prove the live path boots/deploys/preflights cleanly and the panic button works, with
magna53 **staged at `live_real_enabled=FALSE`** so zero real money can move. Do these in order.

## P1.0 — Pre-baseline (confirm BEFORE changing anything)

This is what you're flipping FROM:
```
magna53:  phase=paper · live_real_enabled=f · position_size_multiplier=1.0 · max_concurrent_positions=NULL
env:      ENABLE_LIVE_MODE=false · LIVE_TRADING_ENABLED=true · (no ALPACA_LIVE_* creds wired)
```
Confirm on the server (read-only):
```bash
ssh apollo@87.99.134.162
docker exec apollo-postgres psql -U apollo -d apollo -c \
  "SELECT strategy_id, phase, live_real_enabled, enabled, position_size_multiplier, max_concurrent_positions FROM mi_strategies WHERE strategy_id='magna53';"
grep -E "^ENABLE_LIVE_MODE=|^LIVE_TRADING_ENABLED=" /home/apollo/apollo_the_wise/.env
```
⚠️ **AUTO-ENTRY AUDIT (no WHERE filter):** live auto-entry is GENERIC — **any** `phase=live` +
`live_real_enabled=True` strategy auto-fires real money. Confirm magna53 will be the ONLY one:
```bash
docker exec apollo-postgres psql -U apollo -d apollo -c \
  "SELECT strategy_id, phase, live_real_enabled, enabled FROM mi_strategies ORDER BY phase, strategy_id;"
```
**Gate:** nothing may show `phase=live AND live_real_enabled=t` (9m_day2 must read `phase=shadow`).

## P1.1 — Monday premarket verifies (the GO preconditions)

- **`#346` shadow verify (the #344 HARD-gate condition):** after the premarket EP scans —
  ```bash
  docker exec apollo-market python scripts/_344_shadow_verify.py
  ```
  Confirm: `ep_grade_enrich_shadow` + `ep_repoll_shadow` rows WROTE · re-poll fired **exactly once
  per ticker** (check container uptime first — a restart can dupe) · latency p95 OK · **AND scan
  wall-time unchanged vs the pre-#344 baseline** (the real entry-path risk). **Clean → the #344
  gate holds. Dirty → NO-GO trigger** (per the operator's 6/19 resolution).
- **`#275` band job** fired clean + **`#302`** replay-regression section rendered — both already
  confirmed green in the **Sun 6/21 weekly digest** ✅.
- **`#325`** theme run (~17:00 ET) — first valid test of the discovery fix (read `new_raw_llm`).

## P1.2 — Wire creds + enable dual-account (`.env`)  ⚠ FOUR keys, not two

> 🔴 **CRITICAL — verified 2026-06-21 (advisor review): prod runs on the LEGACY paper-cred names.**
> The server `.env` today has `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` (legacy) and **NOT** the
> canonical `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_SECRET_KEY`. When `ENABLE_LIVE_MODE=true`, the
> boot check (`agent.py:6883-6893`) **hard-requires the CANONICAL `ALPACA_PAPER_*` AND `ALPACA_LIVE_*`,
> then `return`s BEFORE the legacy `ALPACA_API_KEY→paper` remap (line 6896)** — so a legacy-only `.env`
> **BOOT-BLOCKS** (the 2026-05-13 outage class). You MUST add the canonical paper names too, or Phase 1's
> deploy fails at boot.

Edit `/home/apollo/apollo_the_wise/.env` — **four key lines + the flag** (copy the two PAPER values
from the existing legacy lines in the same file; the two LIVE values are new):
```
ALPACA_PAPER_API_KEY=<same value as the existing ALPACA_API_KEY>
ALPACA_PAPER_SECRET_KEY=<same value as the existing ALPACA_SECRET_KEY>
ALPACA_LIVE_API_KEY=<live key>
ALPACA_LIVE_SECRET_KEY=<live secret>
ENABLE_LIVE_MODE=true
```
Leave the legacy `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` in place (harmless + a rollback aid).
**Confirm (names only, no values):**
```bash
grep -oE '^ALPACA_(PAPER|LIVE)_(API_KEY|SECRET_KEY)=' /home/apollo/apollo_the_wise/.env | sort -u
# expect all FOUR; then:
grep -E "^ENABLE_LIVE_MODE=true" /home/apollo/apollo_the_wise/.env
```
> 💡 **Recommended de-risk — add the two `ALPACA_PAPER_*` lines NOW (before Monday).** Copying the
> legacy paper values under the canonical names is **behavior-neutral while `ENABLE_LIVE_MODE=false`**
> (the boot remap already yields the same result), so it changes nothing today but removes the Monday
> boot-block trap. Then Monday's P1.2 is just the two new live keys + `ENABLE_LIVE_MODE=true`.

## P1.3 — Stage the strategy to LIVE but `live_real_enabled=FALSE` (SQL)

```sql
-- PHASE 1: phase=live so preflight exercises the LIVE account path, but live_real_enabled=FALSE
-- so it sends 🟡 STAGED-PAPER proposals (manual [Confirm]) — NO auto-fire, NO real money.
-- Sizing fields are set NOW so Phase 2 only has to flip the one real-money switch.
UPDATE mi_strategies
   SET phase='live', live_real_enabled=false,
       position_size_multiplier=1.0, max_concurrent_positions=NULL
 WHERE strategy_id='magna53';
```
**What each field does (code):**
- `phase='live'` → `resolve_account_mode_for_strategy` (`constants.py:153`) routes to the **live**
  account → preflight (P1.4) exercises `get_account('live')`, the path that 500'd on 2026-05-13.
- `live_real_enabled=false` → **🟡 STAGED-PAPER Telegram proposal**, manual [Confirm], **NO auto-fire**
  (`entry_pipeline._should_auto_enter`). This is the designed ramp. **Phase 2 flips it to `true`.**
- `position_size_multiplier=1.0` → full 1% risk/trade (`entry_pipeline.py:357-371`); the **$5k account
  is the start-small lever** (operator 2026-06-20). Set now, inert until Phase 2.
- `max_concurrent_positions=NULL` → shares the global cap `MAX_CONCURRENT_LIVE_POSITIONS=5` (#65);
  NO tight per-strategy cap — broad participation for the low-WR strategy (#197). Set now, inert until Phase 2.

**Confirm:** re-run the P1.0 SELECT → `phase=live`, `live_real_enabled=f`, `multiplier=1.0`, `cap=NULL`.

## P1.4 — Deploy: EXECUTION FIRST, then both + verify the running image

> 🔴 **ORDER MATTERS — verified LIVE 2026-06-22 (launch-blocker #3).** `deploy.sh both`'s preflight
> routes the creds gate (the `magna53 mode=live` account-fetch) to **apollo-execution**, and `both`
> does NOT recreate execution. So `both`-first checks execution's OLD env (no `ALPACA_LIVE_*`) →
> preflight **FAILS** ("ALPACA_LIVE_API_KEY not set"), and the `&& execution` never runs. Deploy
> **execution FIRST** so it has the live creds (matches the #349 DR "execution-first → both" finding),
> THEN both — whose preflight now finds execution's creds and passes.

```bash
cd /home/apollo/apollo_the_wise
bash scripts/deploy.sh execution   # FIRST — broker side gets the live creds; its preflight then passes
bash scripts/deploy.sh both        # THEN market-agent + orchestrator; their preflight finds execution's creds
```
**Confirm:** both print `DEPLOY OK`; `docker ps` shows **apollo-execution Up <seconds>** (freshly
recreated) + apollo-market Up + healthy.
(Note: this deploy also carries the L2 persistence-dedup `63b116d` — monitoring-only, verified by `#352`.)

## P1.5 — Preflight green on the LIVE path

`deploy.sh` already ran `preflight_check.py` — it walks magna53 (now `mode=live`) through
`_check_safeguards`, exercising `get_account('live')`.
**Confirm:** the preflight block shows `✓ magna53 mode=live PASS` (or a benign `BLOCKED-OK block:*`),
**not** `live_trading_disabled` / `ALPACA_LIVE_API_KEY` / account-fetch failure. A failure here aborts
the deploy.
⚠️ Preflight checks auth + account fetch + safeguards but **NOT `buying_power > 0`** — it PASSES on a
$0 live account. That's fine for Phase 1 (we're not arming real money). Funding is gated in Phase 2.

## P1.6 — Confirm Apollo SEES the live account (`/status`)

Send **`/status`** in Telegram → it now renders the `💰 LIVE-$ (real money)` block (Apollo's own
`get_account('live')` read).
**Confirm:** the `💰 LIVE-$` block renders **without** `⚠️ Account fetch failed` (proves the container
reads the live account — catches wrong-account creds / deposit-to-paper). **Buying power will read $0
or pending — that is EXPECTED in Phase 1** (funds unsettled). Also confirm **F5** here: account not blocked.

## P1.7 — Confirm the panic button

Send `/pause` then `/resume` (well before any window). `/pause` (`agent.py::_handle_pause_command`,
#345) sets the DB halt, cancels resting live brackets, and **reads the state back** (a silent upsert
failure is surfaced, never reported as success).
**Confirm:** `/pause` → "⏸️ Real-money trading PAUSED"; `/resume` → "▶️ …RESUMED". **End RESUMED.**

### ✅ PHASE 1 DONE =
live infra boots + deploys + preflights clean · `/status` reads the live account · panic button
confirmed · `#346` clean. magna53 is **staged-paper** — Monday's signals arrive as 🟡 STAGED-PAPER
proposals (confirm them as paper to watch the flow, or ignore). **No real money has moved.** Now wait
on funding (Section F).

> 🔭 **Phase-1 watch-item (advisor 6/21):** `ENABLE_LIVE_MODE=true` turns on the **full dual-account
> machinery for the first time** — the live `TradingStream`, `sync_positions` iterating `['paper','live']`,
> and the **16:12 ET equity-snapshot job (both modes)** — all against an **UNFUNDED** live account. It
> should handle `$0`/empty fine, but it's the first run ever: **glance at Monday's 16:12/EOD `mi_audit_log`**
> to confirm the per-mode jobs didn't choke on the empty live account (no `account_equity_snapshot` / sync
> errors for `account_mode='live'`).

---
---

# ▶ PHASE 2 — mid-week, the day funds SETTLE (~Wed 6/24+) (ARM REAL MONEY)

Trigger: **F4 green** (Section F). Run this the morning of the first day buying power is settled.

## P2.0 — GATE: confirm funds are actually there

- **Alpaca LIVE dashboard:** Cash / Buying Power ≥ ~$5,000 settled (F4); Account Status not blocked (F5).
- **`/status` in Telegram:** the `💰 LIVE-$` block shows `Buying power: $<settled>` matching the dashboard.
> ⏸️ **Do NOT proceed if buying power is $0 / pending / blocked.** Stay staged; check again next day.

## P2.1 — Flip the ONE real-money switch (SQL) + RESTART to load it

```sql
-- phase / multiplier / cap were already set in Phase 1. This flips ONLY the real-money switch.
UPDATE mi_strategies SET live_real_enabled=true WHERE strategy_id='magna53';
```
> 🔴 **The SQL alone is NOT enough — verified 2026-06-21 (advisor review).** The strategy registry is
> a **process-wide cache** (`registry.py:50,90` — invalidate-only, **NO TTL**); `get_strategy` (called
> per entry) reads the **cache**, not the DB. A raw SQL UPDATE does **not** call `invalidate_cache()`,
> so the running container keeps serving the cached `live_real_enabled=FALSE` and **the flip silently
> does nothing — you'd think you're live and you're not** (the worst failure mode for this step).

**So: after the UPDATE, RESTART the cache-holding containers to reload the registry from the DB —**
```bash
cd /home/apollo/apollo_the_wise
bash scripts/deploy.sh execution   # FIRST (execution-first order, per P1.4) — reloads registry + creds on the broker side
bash scripts/deploy.sh both        # THEN market + orchestrator reload the registry too
```
Mid-week you're not racing the clock, so redeploy and remove all doubt.
**Confirm (after the restart):** `SELECT phase, live_real_enabled FROM mi_strategies WHERE
strategy_id='magna53';` → `live`, `t`; re-run the **no-filter** audit (P1.0) → magna53 is the **ONLY**
`live`+`t` row; preflight prints `✓ magna53 mode=live PASS`.

## P2.2 — Re-confirm the panic button, then it's LIVE

`/pause` → `/resume` (end RESUMED) before the next ORB window. From here, **`/pause` is the only
per-trade kill** — each real fill sends an "AUTO-ENTERED" Telegram.

## P2.3 — FIRST real auto-entry = the integration test (stop-leg watch)

The live auto-entry path has **never executed** before — the auto *mechanism* runs in paper daily,
but `account_mode='live'` routing is first-time. It fails SAFE (rejected order → `AUTO_ENTER_FAILED`
Telegram, no position). The one thing NOT auto-safe is the **stop leg** — with no human in the loop,
the per-trade catastrophic guard IS the OTO bracket's stop leg. **On the FIRST auto-entry, before
anything else, confirm:**
1. the live-account submit landed (an "AUTO-ENTERED" Telegram, not `AUTO_ENTER_FAILED`);
2. `per_strategy_sizing_applied` audit row shows full-1% shares;
3. **the bracket has its stop leg attached** — `/positions` or `mi_live_trades.stop_order_id` non-null;
4. `/pause` is in hand.
**If the stop leg isn't attached → `/pause` immediately and investigate before the day continues.**
- `docker exec apollo-market python scripts/verify_monday_firstfire.py` — the first-fire harness.
- `scripts/evaluate_kill_scale_bands.py` (#275) + `scripts/replay_regression.py` (#302) now read
  `live` — bands/R-dist start accruing real data.
- Watch `mi_audit_log` for any `*_error` / `cross_account_event_rejected` in the first hour.
- **Behavioral note (from the GATE-3 read, 6/21):** the edge is **winner-concentrated** (the +2.18R
  selection delta crosses 0 if you drop the top-4 winners). Expect a string of small reds before the
  first big winner — **that is normal, not failure.** The signed kill/scale bands (#268b/#275) are
  the pre-committed reduce/kill rule; **do not kill on an ordinary early losing streak.**

### ✅ PHASE 2 DONE = real money is live, first auto-entry verified (stop leg attached + full-size + AUTO-ENTERED Telegram).

---

## ⓘ Separate mid-week item — do NOT confuse with Phase 2

**`#347` — the enriched-grade flip (Wed 6/24 earliest):** making the corpus-completeness fix the
LIVE grade is a **different** action — needs ~2 shadow days + **CHANGE_PROCESS + operator sign-off +
a deploy** (carry `max_chars=_GRADE_ENRICH_MAX_CHARS` on the live grade call). It is NOT part of
arming real money. Until #347 lands, BFLY-class names grade on the **pre-fix** grade and won't fire
live. (Nice alignment: real money and the enriched grade both come online ~mid-week, but they are
independent flips with independent gates.)

## Consolidated rollback (any time, fastest → slowest)
1. **`/pause` — THE instant kill (use it first).** Fresh DB read per entry (`db.py:2351` — **no cache**,
   no redeploy, fail-safe to BLOCKED on a read error); blocks new real-money entries + cancels resting
   brackets (open positions keep their broker stops). Verified 6/21 to be cache-independent, unlike the
   strategy row.
2. **SQL** `live_real_enabled=false` / `phase='paper'` — durable, BUT the strategy registry is **cached**
   (invalidate-only), so a raw SQL change does **NOT take effect until the cache-holding containers
   RESTART** (see P2.1). Sequence: **`/pause` first** (instant stop), THEN SQL + a redeploy (durable).
3. **`LIVE_TRADING_ENABLED=false`** in `.env` — boot-read master kill (needs a restart).
4. Full revert: `.env` (creds/ENABLE_LIVE_MODE) + SQL, redeploy execution then both.

---

## One-line checklists

**PHASE 1 (Mon 6/22):** `#346` clean → audit `mi_strategies` (no-filter, nothing else live+t) → `.env`:
add **`ALPACA_PAPER_*` (canonical — copy the legacy values) + `ALPACA_LIVE_*` + `ENABLE_LIVE_MODE=true`**
(FOUR keys — legacy-only BOOT-BLOCKS) → SQL `phase=live`+**`live_real_enabled=false`**+`mult=1.0`+`cap=NULL`
→ **`deploy.sh execution` THEN `both`** (execution-first — both DEPLOY OK) → preflight `magna53 mode=live PASS` →
`/status` 💰 LIVE-$ renders (BP $0 EXPECTED) + not blocked → `/pause`+`/resume`. **No real money.**

**PHASE 2 (the day F4 settles, ~Wed 6/24+):** dashboard + `/status` BP ≥ ~$5k settled & not blocked → SQL
**`live_real_enabled=true`** → **RESTART (`deploy.sh execution` THEN `both`) — the registry is CACHED, SQL alone
is a silent no-op** → re-audit (magna53 ONLY live+t) + preflight PASS → `/pause`+`/resume` → **first
auto-entry: stop leg attached + full-1% + AUTO-ENTERED Telegram** (no stop leg → `/pause` + investigate).
