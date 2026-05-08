# 9M EP — Virgin 9M, Sugar Baby, Day 2 ORB

**Phase**: Live (paper). Production-active across all three sub-stages.
**Origin**: Pradeep Bonde virgin 9-million-share (9M) day methodology.
**Code**:
- Intraday detection: `agents/market_intelligence/ninem_detector.py`, scheduler every 5 min 9:30-16:00 ET (`9m_ep_scan`)
- EOD sweep: `run_9m_eod_sweep` called from nightly_data_pull → writes `mi_9m_sugar_babies`
- Day 2 ORB execution: `_9m_day2_orb_job` 9:31 ET cron + `submit_9m_day2_trade` via `entry_pipeline.submit_trade_entry`

## Definition

Pradeep Bonde's "virgin" 9M is a stock trading 9M+ shares for the first time in a long period (or first time ever) with directional conviction. The volume anomaly is the signal — institutions are accumulating or distributing aggressively, and price typically continues in the move's direction.

Apollo runs 9M as a **three-stage pipeline**:
1. **Intraday 9M EP** — real-time scan during the trading session detecting either confirmed (9M+ already) or anticipated (projected ≥ 12M) days
2. **Sugar Baby** — EOD confirmation that today met all the going-in shape criteria (confirmed 9M day + close-in-upper-range + green); becomes Day 2 ORB candidate
3. **Day 2 ORB** — next morning's first-minute breakout above prior day's high; entry on stop-limit, stop at prior day's low

This is the **only Apollo strategy that is purely quantitative** — no LLM in the detection loop.

## Universe / eligibility

- **Price**: ≥ $5
- **Dollar volume**: ≥ $50M actual (confirmed) OR ≥ $30M already traded (anticipation)
- **Universe**: full Polygon snapshot (~9700 stocks)
- **Security type**: CS, ADRC only (filter ETFs, REITs, units)
- **Range**: ≥ 2% of current price (rejects merger-arb pins like DBRG)

## Detection criteria (current)

### Stage 1 — Intraday 9M EP (every 5 min 9:30-16:00 ET)

For each ticker in snapshot:

1. Skip if ticker length > 5 or contains `.` (units/foreign)
2. Skip if in SKIP_TICKERS or non-stocks
3. Skip if already alerted today (per-day dedup via `_alerted_today` set)
4. Skip if price < $5
5. Skip if `prev_close ≤ 0`
6. **Directional gate**: `is_9m_directional(prev_close, day_open, current_price)` — gap ≥ 3% OR intraday gain ≥ 4%
7. **Range gate**: intraday range ≥ 2% of current price
8. **Extension gate**: prev_close ≤ 1.20 × MA-10 (filter already-extended chase risk; unknown MA → skip per IPO/Day-1 case)
9. **Confirmed 9M (`is_9m_actual`)**: `today_volume ≥ 8.9M AND dollar_volume ≥ $50M`. Pre-9:30 → False (Polygon snapshot stale)
10. **Anticipation (`is_9m_anticipation`)**: `minutes_since_open ≥ 30 AND today_volume ≥ 3M AND dollar_volume ≥ $30M AND projected_vol ≥ 12M`
11. **ADV anomaly gate**: `effective_vol ≥ 3 × adv_20` (effective = projected for anticipation, today_volume for actual). Unknown ADV → skip (IPO Day 1-2 case)

### Stage 2 — Sugar Baby (EOD sweep)

Mirrors intraday gates against `mi_daily_closes` data (final EOD bars):
- volume ≥ 9M shares
- close ≥ $5
- dollar_volume ≥ $50M
- close > open (green day)
- (close - low) / (high - low) ≥ 0.75 (close in upper 25% of range)
- volume ≥ 3 × adv_20 (or unknown ADV passes)
- net_up ≥ 3% vs prev_close (categorical, NOT just close > open — rejects gap-down wick-fills like WU 4/24)

Confirmed Sugar Babies → `mi_9m_sugar_babies` table. They become Day 2 ORB candidates.

### Stage 3 — Day 2 ORB (next morning)

Pre-market sugar babies → 9:31 ET cron places stop-limit BUY at prior day's high, OTO bracket with stop_loss at **prior day's low** (NOT ORB low, NOT ATR-based).

Routes through `entry_pipeline.submit_trade_entry` (unified pipeline shared with MAGNA53 since 2026-04-24). Strategy-specific differences (stop source, sizing) injected via `spec_builder` callback.

### Anticipation cadence carve-out

Silent anticipations hit DB/audit only; Telegram fires only when `gap ≥ 10% OR proj_vol ≥ 25M`. Tightens noise on borderline anticipations.

### Per-scan digest (Wave C #5, 2026-05-07)

User-facing Telegram is batched per scan tick. Per-ticker DB inserts + audit events unchanged. One digest per scan tick with sections by tier (Actual / Pace).

## Known limitations / open questions

1. **TEVA 4/30 EOD-unfilled cleanup-path anomaly** (task #17): TEVA cancelled with `EOD unfilled` (4:05 PM cleanup) instead of `ORB window unfilled` (10:00 ET cleanup). The 10:00 ET cleanup didn't pick TEVA up. Investigation pending.

2. **9M Day 2 stop discrepancy** (CLAUDE.md 2026-05-01 session 1): the ORIGINAL bug was that order_manager.py read `trade["orb_low"]` for stop, but 9M Day 2 writes `stop_price = prior_day_low`. Fixed; documented for SSoT continuity.

## Change log (newest first)

### 2026-05-07 — Wave C #5: 9M EP per-scan digest

**Trigger**: User reported 5/06 9M Pace had 15+ tickers each in their own Telegram bubble. Single scan tick fired `send_telegram_message` per ticker.

**Evidence**: 30d audit log shows max 19 distinct tickers per single scan tick (5/06 worst case). Old design: 15+ separate Telegrams per tick. New design: 1 digest per tick with sections.

**Anticipated effect**: typical 3-7 digests/day (vs 6-34 individual pings). Hot day (5/06): 11 digests vs 34 pings. Per-ticker DB inserts + audit events unchanged.

**Reversion-flag**: NEW.

**Status**: shipped + validated (5/07 morning showed multiple tickers clustering per scan tick — digest path confirmed).

### 2026-05-06 — Net-up gate categorical fix

**Trigger**: WU 2026-04-24 case study — gap −10%, recovered to net −4.6%, close > open ✓ — but categorically not a breakout. The "green close > open" rule alone admits gap-down wick-fills.

**Evidence**: WU 4/24 case study + the structural argument that gap-down then bounce isn't a 9M breakout shape.

**Anticipated effect**: sugar baby gate now requires `net_up ≥ 3% vs prev_close` (matches intraday `_MIN_GAP_PCT` floor). Rejects wick-fills.

**Reversion-flag**: REFINEMENT.

**Status**: shipped (CLAUDE.md 2026-05-06).

### 2026-05-04 — Cross-ticker open-position guard (TEAM 5/04 near-miss)

**Trigger**: TEAM 5/04 9M Day 2 placed bracket order while a MAGNA53 5/01 fill in TEAM was still open. Same-day dedup at entry_pipeline blocked `(ticker, alert_date)` collisions; safeguards blocked count cap; none checked per-ticker open positions across days/strategies.

**Evidence**: TEAM 5/04 incident.

**Anticipated effect**: new check after same-day dedup — block if `status='filled' AND remaining_shares > 0` for ANY prior alert_date on the same ticker. Skip-reason `BLOCK_TICKER_OPEN_POSITION`.

**Status**: shipped.

### 2026-05-04 — Parallelize 9M Day 2 cron + drop bar-retry delay

**Trigger**: TEAM 5/04 unfilled — root cause was the 9M Day 2 cron's sequential for-loop (SOUN bar-miss at 09:31 slept 60s, TEAM queued behind). MAGNA53 fans out via asyncio.gather; 9M Day 2 ran for-loop.

**Evidence**: Audit log timestamps showed serialized retries.

**Anticipated effect**: switched to `asyncio.gather(*..., return_exceptions=True)` + `Semaphore(5)` mirroring MAGNA53. `BAR_RETRY_DELAY_SEC = 60 → 10`.

**Reversion-flag**: REFINEMENT.

**Status**: shipped + validated.

### 2026-05-01 — 9M Day 2 stop clobber bug (critical)

**Trigger**: GOOGL 9M Day 2 announced stop $365.82 (prev day low), Alpaca received $379.43 (today's ORB low). 0.8% stop vs intended 4.3%.

**Evidence**: GOOGL incident.

**Root cause**: order_manager.py paths hardcoded `stop_loss_price = trade["orb_low"]` from MAGNA53 unification; 9M Day 2 writes `stop_price = prior_day_low ≠ orb_low`.

**Anticipated effect**: every order_manager site reads `trade["stop_price"]` (spec-authored, persisted at INSERT). 9 sites patched.

**Reversion-flag**: BUGFIX (not a tuning change).

**Status**: shipped (CLAUDE.md 2026-05-01).

---

Pre-2026-05-01 history (sugar baby table creation, intraday/EOD filter unification) lives in CLAUDE.md. Backfill as touched.
