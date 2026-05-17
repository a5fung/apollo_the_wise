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

**Trend gate** (added 2026-05-08): REJECT if all three structural metrics indicate a destroyed name:
- `prev_20d_pct < -10%` (in steep drawdown), AND
- `prev_vs_sma50 < 0.85` (>15% below SMA-50), AND
- `sma50_slope_pct < 0` (downtrending MA)

A virgin 9M needs uptrending or fresh-news context. A destroyed name bouncing on heavy volume is distressed unwinding, not institutional accumulation. ANY one of the three passing keeps the candidate (allows pullback-from-highs / recently-broke-out / long-uptrend shapes through). Missing data → keep (insufficient data to judge as destroyed).

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

### 2026-05-17 — P7.3b 9M universe-watch (Pradeep methodology)

**Trigger**: Methodological reframing of 9M EP role per Pradeep Bonde (memory: `user_pradeep_9m_universe_methodology.md`). Pradeep estimates 9M volume hits ~1% of stocks per day. The event itself is a watchlist trigger — NOT a directional entry signal. Entry comes from the tightness→expansion lifecycle (flag-detector class), which aligns with the continuation flag detector's existing state machine.

This reframing means **every 9M EP** (intraday alert + EOD sugar baby + failed-Day-2 + skipped) should enter the flag detector's universe, where it gets evaluated for runup→base→tightness→expansion over weeks. NOT just failed-Day-2 names. The sugar-baby Day-2 entry mechanism (which DOES exist) is one possible entry path, but the universe-watch carryforward catches the cohort that doesn't fit the Day-2 ORB shape.

**Evidence**:
- P7.3a audit (2026-05-17, `analysis/2026-05-17/ninem_delayed_ep_audit.md`):
  9M failed-Day-2 alpha cohort of 242 names had 54.5% organic capture
  rate via existing downstream paths. Meaningful gap to close, but the
  Pradeep-methodology framing makes the universe-watch scope BROADER
  than failed-Day-2 alone — every 9M EP regardless of Day 2 outcome.
- P7.3a day2_status semantic check: 'pending' rows persist indefinitely
  (100% of 'pending' >1 day old over 60d cohort). Confirms `day2_status`
  is not a reliable filter; the universe-watch query reads
  `mi_9m_ep_alerts` directly, ignoring sugar baby Day 2 disposition.

**Architecture**: 5th universe-pattern added to `db.get_flag_universe`. Query:
```sql
SELECT DISTINCT ticker FROM mi_9m_ep_alerts
WHERE alert_date >= ($1::date - INTERVAL '14 days')
  AND alert_date <= $1::date
```

14-day rolling window — multi-week tightness observation. Tag: `ninem_universe_watch` (added to new `mi_flag_candidates.universe_sources TEXT[]` column from P7.2 ship `370aed1`). Names admitted by both organic AND 9M-watch paths capture BOTH tags (no dedup loss).

Flag detector's `compute_flag_metrics` runs the normal per-ticker eligibility (close ≥ $5, ≥60 sessions, runup ≥50%, etc.) — universe expansion just brings names INTO the scoring queue, doesn't bypass per-ticker gates.

**Env flag**: `NINEM_FLAG_CARRYFORWARD_ENABLED=true` (default). Set false + docker compose restart to revert.

**Telemetry-first ship per user direction** ("monitor this as shadow or some way"): the universe expansion is itself the shadow — we watch how 9M EPs progress through flag stages over weeks before considering automated entry logic. No auto-entry change today.

**Anticipated effect**: ~3-5 9M EPs per day on average → ~40-70 distinct tickers in 14-day rolling window. Most enter as `unqualified` initially (runup not yet ≥50%, or fail other organic gates). Some will progress to WATCH → TIGHTENING → COILED over weeks. The Pradeep delayed-EP class (TRT 4/23 → 5/15) should show up as multi-week basing on a 9M-origin universe-source tag.

**Reversion-flag**: NEW (paired with P7.2 universe-source schema).

**Status**: shipped 2026-05-17 commit `<TBD>`. Stage 1 verification at Day 7-14 (universe pattern firing, looking for ≥30 9M tickers in flag candidates with `universe_sources @> ARRAY['ninem_universe_watch']`). Stage 2 — analyze flag-stage progression of 9M-origin names at Day 21+.

### 2026-05-13 — Sugar baby M&A filter (WEN-class coverage closure)

**Trigger**: WEN 5/12 was logged as a sugar baby and surfaced as a Day-2 ORB candidate on 5/13 — despite an active Trian Fund take-private rumor that filtered the same ticker on the EP path (10× `mna_filter_fired` audit events on 5/13). 9m_day2 entry attempt only failed on `setup:faded_from_orb` shape rejection. If WEN had held the ORB high, the system would have entered a take-private target with no follow-through available (price pins to deal value).

**Evidence**: Symmetry gap. `is_likely_ma` is already applied in `ep_detector.py` (MAGNA53) and `flag_detector.py` (continuation flags). The 9M sugar baby + Day-2 ORB path had zero M&A coverage — code path verified by grep, WEN-on-5/13 confirmed live.

**Anticipated effect**: ~1-2 sugar babies/month filtered as `mna_filter_fired (9m_sugar_baby)`. Polygon-news-only check (9M is pure-quant, no LLM catalyst grading). 21-day lookback (matches flag detector). Same `_MNA_KEYWORDS` SSoT used by every detector — including today's morning fix that dropped direction-blind `"acquire"`/`"acquisition"` and added `"take-private"` / `"private deal for"` (which is exactly the keyword path that catches WEN).

**Reversion-flag**: NEW integration point (the M&A filter itself is unchanged; this just wires it into the 9M sugar baby loop). Fail-open on Polygon outage — don't block sugar baby logging if news fetch raises.

**Status**: shipped 2026-05-13. Intraday 9M scan (`run_9m_scan`) still does NOT run the M&A filter (informational alerts, no trade triggered directly). Filed as future scope if intraday FP becomes an issue.

### 2026-05-08 — Sugar baby destroyed-name trend gate (ATEC 5/07 incident)

**Trigger**: User flagged ATEC 5/07 sugar baby — stock down 70% over months, tanked another -13% on earnings 5/06, then bounced on huge volume 5/07. All sugar baby criteria passed (cirp 0.80, net_up +10.9%, vol 11.9M, dollar_vol $92M) but structurally a dead-cat bounce on a destroyed name, not Pradeep virgin 9M. The trend columns (prev_5d_pct, prev_20d_pct, prev_vs_sma50, sma50_slope_pct) had been captured as telemetry since earlier ship but never promoted to gates.

**Evidence**: 60d historical backtest. Destroyed-name pattern (all 3 trend metrics fail: prev_20d < -10% AND prev_vs_sma50 < 0.85 AND sma50_slope_pct < 0) caught **3 of 51 sugar babies** (5.9%): ATEC 5/07 (pending, would trade 5/08), BRBR 5/06 (skipped), EGO 4/30 (skipped). **Zero historical impact on actually-traded sugar babies** — all 3 had day2_status != 'traded'. Surgical filter. Looser variants tested: `prev_20d < -15%` standalone would also filter CCC 4/30 (which DID trade) — too aggressive.

**Anticipated effect**: ~1-2 fewer sugar babies per month under destroyed-name conditions. ANY one of the three trend metrics passing keeps the candidate (allows the various uptrend / pullback / long-base shapes through).

**Reversion-flag**: NEW. Trend columns existed as telemetry; this is the first time they're enforced as a gate.

**Status**: shipped + ATEC's pending row deleted from prod.

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
