# Monday 6/22 — real-money GO runbook (validated)

**Purpose:** the turnkey execution sequence for the MAGNA53 real-money cutover, with **every
step traced to code** so the flip is pre-checked, not improvised. This is the EXECUTION
surface; the GO/NO-GO DECISION lives in `go-no-go-evidence-2026-06-22.md` (§5 there points
here). Validated 2026-06-20 (#303) against HEAD.

> ⚠️ **The flip is NOT a single switch.** It's: (1) creds + env in `.env`, (2) a
> `mi_strategies` row UPDATE, (3) deploy, (4) preflight, (5) `/pause` confirm. And **three of
> the four strategy-row fields have NO Telegram command** — `live_real_enabled`,
> `position_size_multiplier`, `max_concurrent_positions` are **SQL-only** (deliberately — the
> real-money gate is not a casual `/strategy` action). Do the steps in order; order matters.

> 💰 **Two independent clocks.** The creds + flip + deploy (steps 1–5) is the *fast* clock —
> minutes. **Funding is the *slow* clock — days** (ACH/wire settlement). They are decoupled:
> you can wire creds and stage the flip while money is still in transit. But **real fills
> require settled buying power**, so the funding clock — not the flip — gates the actual
> first trade. **Section F below is a HARD GATE: do not count the launch as armed until it's
> green.** If you flip while funding is pending, the system fails SAFE (every auto-entry →
> `setup:size_too_small` skip, no positions, no errors — see why in F), so an "unfunded live"
> account silently no-ops. Recommended: **hold the step-2 flip until F is green** so "live"
> always means "can actually trade."

---

## F. Funding gate (the SLOW clock — start EARLY; HALT here until settled)

**Why this gates everything (traced to code):** sizing reads the **live, settled equity** at
trade time — `order_manager.py:112` `risk_dollars = equity × risk_pct`, `:124`
`max_position = equity × 0.20`. So:
- **$0 settled** → `risk_dollars = 0` → 0 shares → `setup:size_too_small` skip. Fail-safe (no
  error, no naked risk) but **no real trade fires** — a "launched" but unfunded account is a
  silent no-op.
- **Partially settled** (e.g. $2k of $5k cleared) → it trades, but sized off the *smaller*
  balance (~$20 risk / $400 max position), not your intended $5k.

So real fills require **settled buying power ≥ your intended start size** *before* the 9:31 ET
ORB window. The deposit clock is **days, not minutes** — initiate it as early as Alpaca allows.

**State tracker — mark each as it lands (this is the "what's pending" surface):**
```
[ ] F1 — Live account OPENED + APPROVED (api.alpaca.markets)
[ ] F2 — Transfer INITIATED (ACH/wire) — do this EARLIEST; ACH commonly takes a few
         business days, and a brand-new account may not get instant-deposit buying power
[ ] F3 — Deposit POSTED to the live account (shows in Alpaca dashboard balance)
[ ] F4 — Buying power SETTLED & AVAILABLE ≥ intended start size (~$5,000 for the $5k start)
[ ] F5 — account_blocked = false AND trading_blocked = false (new accounts can carry a hold)
```

**How to check — authoritative source = the Alpaca LIVE dashboard** (`app.alpaca.markets`,
LIVE not paper): the **Cash / Buying Power** figure is the source of truth for F3/F4, and
Account → Status for F5. No code path is needed for this read (and it works *before* creds are
even wired). Apollo's own confirming read comes after deploy (step 4b, `/status`).

> ⏸️ **HALT RULE.** Do **not** treat the GO as armed until **F4 = green** (and F5 clear). If
> F4 is red on Monday morning:
> - **Preferred:** HOLD — leave magna53 at `phase=paper` (skip step 2), keep staging the rest,
>   and resume the flip the day buying power settles. Re-run this whole runbook from step 0 that
>   day (Monday-specific verifies in step 0 re-confirm on the new day).
> - **If you flip anyway:** it's safe — every entry hits `setup:size_too_small` and skips, no
>   real money moves — but understand the day is a **no-op**, not a live launch. Watch
>   `mi_audit_log` for `setup:size_too_small` to confirm that's why nothing fired.

---

## 0. Pre-GO baseline (confirm BEFORE changing anything)

Current state (confirmed 6/19, evidence pack §5) — this is what you're flipping FROM:

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

⚠️ **AUTO-ENTRY AUDIT (added 2026-06-20, advisor):** live auto-entry is now GENERIC —
**any** `phase=live` + `live_real_enabled=True` strategy auto-fires real money (not just
magna53). Before the flip, confirm magna53 is the ONLY one, with **no WHERE filter**:
```bash
docker exec apollo-postgres psql -U apollo -d apollo -c \
  "SELECT strategy_id, phase, live_real_enabled, enabled FROM mi_strategies ORDER BY phase, strategy_id;"
```
**Gate:** nothing other than magna53 may show `phase=live AND live_real_enabled=t`
(9m_day2 must read `phase=shadow`). A second unexpected live+True row would auto-fire
real money on Monday.

**Gate:** only proceed if Monday's verifies are clean (#346 shadow, #275 band job, scan
wall-time unchanged) AND the operator has called GO (#305).

---

## 1. Wire live creds + enable dual-account (`.env`)

**Action** — edit `/home/apollo/apollo_the_wise/.env`:
```
ALPACA_LIVE_API_KEY=<live key>
ALPACA_LIVE_SECRET_KEY=<live secret>
ENABLE_LIVE_MODE=true
```
**What it does / why order matters** (`agent.py::_bootstrap_alpaca_credentials`, ~6871/7037):
`ENABLE_LIVE_MODE=true` **hard-requires** both `ALPACA_LIVE_API_KEY` AND `ALPACA_LIVE_SECRET_KEY`
— boot-blocks if either is missing. So the creds must be in `.env` **before** the deploy in
step 3, or the container won't boot. (This boot-block is the 2026-05-13 outage guard: a
`phase=live` strategy under `ENABLE_LIVE_MODE=false` also boot-blocks.)
**Confirm:** `grep -c "^ALPACA_LIVE_API_KEY=" .env` → 1; `ENABLE_LIVE_MODE=true` present.
**Rollback:** set `ENABLE_LIVE_MODE=false` (paper-only; live creds ignored).

## 2. Flip the strategy row to real money (SQL — no command exists)

> ⏸️ **Precondition: Section F (funding) must be green** — `F4` buying power settled ≥ start
> size, `F5` not blocked. This is the real-money switch; flipping it on an unfunded account
> just produces silent `size_too_small` skips (safe, but a no-op). HOLD here if funding is
> still pending.

**Action** — one UPDATE on `mi_strategies` (START-SMALL sizing; pick the multiplier/cap):
```sql
-- START-SMALL = the $5,000 account itself (operator decision 2026-06-20). Full size:
-- position_size_multiplier=1.0 (1% risk/trade ≈ $50, often less under the 20% capital cap);
-- NO tight count cap (max_concurrent_positions=NULL → shares the global 5) — a low-WR
-- winner-driven strategy needs broad participation (#197: the cap-blocked names were the
-- winners). Risk bounded by per-trade size + the $5k account + 2% daily-loss + drawdown
-- breaker, NOT by count. Worst correlated day ≈ (positions open) × 1% (rarely >3 fire in
-- the ORB window) — small absolute $ on $5k, the point of starting here.
UPDATE mi_strategies
   SET phase='live', live_real_enabled=true,
       position_size_multiplier=1.0, max_concurrent_positions=NULL
 WHERE strategy_id='magna53';
```
**What each field does (traced to code):**
- `phase='live'` → `resolve_account_mode_for_strategy` (`constants.py:153`) routes submits to the **live** Alpaca account.
- `live_real_enabled=true` → **AUTO-ENTERS real money** at the ORB window — no manual confirm (wired 2026-06-20, `entry_pipeline._should_auto_enter`, operator-signed); `=false` → 🟡 STAGED-PAPER Telegram proposal (manual [Confirm], the ramp). **This is THE real-money switch — and as of 6/20 it means AUTO-FIRE, not a proposal.** Each fill sends an "AUTO-ENTERED" Telegram; `/pause` is now the only per-trade kill.
- `position_size_multiplier=1.0` → `entry_pipeline.py:357-371`: `new_shares = floor(shares × strategy_mult × drawdown_mult)`, then **recomputes** `position_size` + `risk_dollars`; a `<1` result skips `setup:size_too_small`; emits `per_strategy_sizing_applied`. **This is the number real money rides on** — at 1.0 the trade runs full 1% risk; the $5k account is the start-small lever (operator 2026-06-20).
- `max_concurrent_positions=NULL` → shares the global cap (`MAX_CONCURRENT_LIVE_POSITIONS=5`) in `_check_safeguards` (`block:strategy_position_cap`, #65). NO tight per-strategy cap — broad participation for the low-WR strategy (operator 2026-06-20, #197 evidence); 5 is a runaway ceiling that rarely binds.

**Why SQL not `/strategy promote`:** `promote` (strategies/telegram.py) only advances `phase`
along the ladder AND is gated on `check_promotion_eligibility` (refuses if the registry verdict
has blocking reasons) — it does **not** touch the other three fields. The GO is a deliberate
operator decision, so set all four explicitly in one UPDATE.
**Confirm:** re-run the step-0 SELECT → all four fields as set.
**Rollback:** `UPDATE mi_strategies SET phase='paper', live_real_enabled=false WHERE strategy_id='magna53';` (instant, read per-entry — no redeploy).

## 3. Deploy (both + execution) + verify the running image

**Action:**
```bash
cd /home/apollo/apollo_the_wise
bash scripts/deploy.sh both        # market-agent + orchestrator
bash scripts/deploy.sh execution   # apollo-execution (the broker side — feedback_deploy_both_excludes_execution)
```
**What it does:** rebuilds + recreates services on the new `.env` (live creds, ENABLE_LIVE_MODE).
`both` does NOT recreate apollo-execution (the broker side that actually submits) — so the second
deploy is **required** or the live-account submit path stays on the old image.
**Confirm:** both print `DEPLOY OK` (all preflight gates); `docker ps` shows `apollo-execution`
**Up <seconds>** (freshly recreated) + `apollo-market` Up + healthy.
**Rollback:** revert `.env` (step 1) + the SQL (step 2), redeploy.

## 4. Preflight green on the LIVE path

**What `deploy.sh` already ran** (`preflight_check.py`): walks every enabled non-shadow strategy
through `_check_safeguards` — now `magna53` resolves `mode=live` → exercises `get_account('live')`
(the exact path that 500'd in the 2026-05-13 outage). A `setup:*`/`infra:*` reason fails the
deploy; only `block:*` passes through.
**Confirm:** the deploy's preflight block shows `✓ magna53 mode=live PASS` (or a benign
`BLOCKED-OK block:*`), **not** a `live_trading_disabled` / `ALPACA_LIVE_API_KEY` / account-fetch
failure. If it failed here, the deploy already aborted — **do not** consider the GO done.
⚠️ Preflight checks auth + account fetch + safeguards but **NOT** `buying_power > 0` — it will
print PASS against a $0 live account. Funding is verified separately, in 4b.

## 4b. Confirm Apollo SEES the funds (closes the funding loop)

**Action:** send **`/status`** in Telegram (now that live creds + `ENABLE_LIVE_MODE=true` are
deployed, it renders the `💰 LIVE-$ (real money)` block).
**What it does:** Apollo's own read of `get_account('live')` — `Equity` + `Buying power` for the
live account. This is the confirmation that the *container* sees the funded account, not just
the dashboard (catches a wrong-account-keyed creds mistake, or a deposit that posted to paper).
**Confirm:** the `💰 LIVE-$` block shows `Buying power: ${settled amount}` matching the Alpaca
dashboard (Section F4) — **not** `$0.00` and **not** `⚠️ Account fetch failed`.
> ⏸️ **HALT** if `/status` shows live buying power `$0.00` (or a fetch error) — the auto-entry
> would `size_too_small`-skip all day. Roll back to `phase=paper` (step-2 rollback) and resume
> once funds settle, OR knowingly accept a no-op day.

## 5. Confirm the panic button BEFORE the first ORB window

**Action:** send `/pause` then `/resume` in Telegram (well before 9:31 ET).
**What it does** (`agent.py::_handle_pause_command`, #345): `/pause` sets the DB halt
(read per-entry by `_check_safeguards`, highest-priority gate), cancels resting live entry
brackets, and **reads the state back** — it reports the ACTUAL stored value (a silent upsert
failure is surfaced, never reported as success). `/resume` lifts it.
**Confirm:** `/pause` → "⏸️ Real-money trading PAUSED"; `/resume` → "▶️ …RESUMED". End in the
RESUMED state. This is the one-keystroke kill switch for the live day.

---

## Consolidated rollback (any time, fastest → slowest)
1. **`/pause`** — instant, runtime, blocks all new real-money entries + cancels resting brackets (open positions keep their broker stops).
2. **SQL** `phase='paper'` / `live_real_enabled=false` — per-strategy, read per-entry, no redeploy.
3. **`LIVE_TRADING_ENABLED=false`** in `.env` — boot-read master kill (needs a restart).
4. Full revert: `.env` (creds/ENABLE_LIVE_MODE) + SQL, redeploy both+execution.

## Post-GO first-fire watch (read-only; verdicts are the operator's)
- `docker exec apollo-market python scripts/verify_monday_firstfire.py` — the shadow/grade/judge/detector first-fire harness.
- **First real-money ORB = the integration test** (advisor 2026-06-20): the live auto-entry path has NEVER executed before — the auto *mechanism* is exercised by paper daily, but `account_mode='live'` routing is first-time Monday. It fails SAFE (a rejected order → `AUTO_ENTER_FAILED` Telegram, no position). The one thing that is NOT auto-safe is the **stop leg**: with no human-in-loop, the per-trade catastrophic guard IS the OTO bracket's stop leg. So on the FIRST auto-entry, BEFORE anything else: confirm (a) the live-account submit landed, (b) `per_strategy_sizing_applied` audit row shows full-1% shares, (c) **the bracket has its stop leg attached** (`/positions` or `mi_live_trades.stop_order_id` non-null), and (d) `/pause` is in hand. No cap to raise (broad participation by design) — but the first fire is still the live-path validation: if its stop leg isn't attached, `/pause` and investigate before the day continues.
- `scripts/evaluate_kill_scale_bands.py` (#275) + `scripts/replay_regression.py` (#302) — both read `live` now; the bands/R-dist start accruing real data.
- Watch `mi_audit_log` for any `*_error` / `cross_account_event_rejected` in the first hour.

---

*One-line GO checklist:* **[F] funding settled — Alpaca dashboard buying power ≥ start size + not blocked (HALT if pending)** → audit `mi_strategies` (no filter) → magna53 is the ONLY `live`+`live_real_enabled=t` → env creds+`ENABLE_LIVE_MODE=true` → SQL `phase=live`+`live_real_enabled=true`+`multiplier=1.0`+`max_concurrent_positions=NULL` → `deploy.sh both` then `execution` (both DEPLOY OK, execution Up) → preflight `magna53 mode=live PASS` → **`/status` 💰 LIVE-$ buying power matches the dashboard (HALT if $0)** → `/pause`+`/resume` confirmed → first auto-entry: verify stop leg + full-size + the AUTO-ENTERED Telegram.
