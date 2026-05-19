# Continuation Flag — VCP / Qullamaggie Tightening

**Phase**: Shadow (telemetry-only). Promotion path: `telemetry_review` per `strategies/registry.py`.
**Origin**: Mark Minervini VCP (Volatility Contraction Pattern) + Qullamaggie tightening flag methodology.
**Code**: `agents/market_intelligence/flag_detector.py`, scheduler 17:25 ET cron `flag_continuation_scan`.

## Definition

A stock makes a strong runup (≥ 50% over weeks), then forms a tight consolidation (range contracting, volume drying up) below the runup high. The base is the bullish rest before the next leg up; the breakout above base high is the entry signal.

This is a long-side continuation pattern — opposite of `parabolic_short.md`. Both share visual surface features (high-volume past activity, structural metrics) but differ on intent and outcome.

## Universe / eligibility

Organic paths (common-gate enforced):
- **Top 200 RS** OR **rs_1m percentile ≥ 80** OR **last_close / 10-session min ≥ 1.25** (burst inclusion)
- Common gates: price ≥ $5, ADV-20 dollar volume ≥ $5M, ≥ 60 sessions of history, security type ∈ (CS, ADRC)
- Sector enriched via `mi_ticker_overrides`

Carryforward paths (bypass common gates — already vetted on prior admission):
- **MAGNA53-failed R3** (P7.2 2026-05-17) — R3-stopped MAGNA53 names in last 7d. Env: `MAGNA53_FLAG_CARRYFORWARD_ENABLED`
- **9M universe-watch** (P7.3b 2026-05-17) — ALL 9M EPs in last 14d. Env: `NINEM_FLAG_CARRYFORWARD_ENABLED`
- **Flag-stage carryforward** (2026-05-19) — tickers that were COILED or TIGHTENING in last 5 trading days. Bridges one-day RS percentile dips that would otherwise drop consolidating leaders from the universe. Env: `FLAG_STAGE_CARRYFORWARD_ENABLED`

## Detection criteria (current)

`compute_flag_metrics` (`flag_detector.py:193`) emits a stage per (ticker, scan_date):

### Pivot anchor

- `_find_pivot_high`: 25-session lookback EXCLUDING today. Anchor = bar with highest VOLUME among bars whose HIGH is within `_PIVOT_HIGH_BAND` (2%) of period max-high.
- High-anchored intent: capture blow-off shooting-star reversal days that close low but had the runup's true volume climax.
- `pivot_high_price` = pivot bar's high; `base_high` = max base bar high; `base_low` = min base bar low; `base_age` = number of bars between pivot and today.

### Qualifying gates

1. `base_age ≥ 3` (`_BASE_AGE_MIN_WATCH`)
2. `base_age ≤ 25` (`_BASE_AGE_MAX`) — older base = stale, INVALIDATED
3. **Runup**: `pivot_high / 60d_low ≥ 1.50` (50%+ prior runup)
4. **Proximity**: `|today_close - pivot_high| / pivot_high ≤ 20%` (close to pivot, not extended past)

### Stage progression

- `unqualified` → `WATCH` → `TIGHTENING` → `COILED` → `TRIGGERED` (or `INVALIDATED`)

Stages depend on:
- `range_contraction_ratio` (recent 5-bar range vs base average)
- `vol_contraction_ratio` (recent 5-bar volume vs ADV20 or recent base avg, whichever is lower per fresh-tightening hybrid)
- `last_body_pct` and `prev_body_pct` (small bodies = tight days)
- `breakout_close > base_high` (TRIGGERED)
- `close < pivot_low` (INVALIDATED)

### Hysteresis

Single-day downward stage flips held one day (`held_from_stage` audit-reviewable). INVALIDATED never holds; upgrades fire immediately. Implemented in `compute_flag_metrics` via `yesterday_stage` parameter.

### Fresh-tightening predicate (alternative COILED path)

Added 2026-05-04 to catch short-base tight setups that don't fit the early-vs-recent window math. Fires when:
- `base_age ≥ 4`
- `max(2-bar TR%) ≤ 0.6 × ATR-14%`
- `max(2-bar volume) ≤ max(recent_5d_avg_vol, 0.5 × ADV20)` (hybrid ceiling, advisor-flagged 2026-05-05)

## Known limitations / open questions

1. **ATR-relative pivot walk threshold** (filed 2026-05-08): `_PIVOT_WALK_THRESHOLD` is currently a flat 1% for all tickers. For a $5 stock that's a 5¢ beat — could be noise on a high-ATR runup name. Future tune: `max(0.01 × prior_pivot_high, 0.25 × ATR14)`. Ship-then-tune, not flip-blocking.

2. **Trailing-10 burst path** (CLAUDE.md 2026-05-05): currently inert (`rs_1m ≥ 80` carries the burst path on most tickers). Documented in flag_detector docstring; non-action item.

## Change log (newest first)

### 2026-05-19 — Universe path (e): flag-stage carryforward (RVMD-class fix)

**Trigger**: RVMD on 2026-05-19 was COILED for 3 consecutive scans (5/14, 5/15, 5/18) — textbook tight consolidation in a $141-$151 range with rs_composite=92 and rs_3m=94. Today's scan dropped it entirely (not in mi_flag_candidates at all, not even WATCH). Investigation: rs_rank went 321→499 and rs_1m went 85.6→70.3 in a single day (one-day percentile rotation as bigger-mover names entered the 1-month window). All three organic universe gates (rs_top200 ≤200, rs_1m ≥80, momentum_25pct ≥+25%) failed simultaneously despite price action being identical to prior days (RVMD actually +2% on 5/19). Not in MAGNA53-failed or 9M-watch carryforward paths either.

**Evidence**: N=1 case (RVMD). But this is a STRUCTURAL inversion, not a calibration question — the flag detector's whole purpose is catching consolidating leaders before breakout. A 1-day RS percentile dip dropping a 3-day-COILED textbook setup is the gate logic working against the detector's intent. Sample-size discipline doesn't apply to gate inversions, only to threshold tuning.

**Anticipated effect**: tickers that were COILED or TIGHTENING in last 5 trading days stay in the universe. State machine handles correctness — carried-forward tickers either re-establish COILED/TIGHTENING (consolidation continued) or progress to INVALIDATED (base broke). Universe expansion alone doesn't change detection rules. Expected volume: ~20-50 additional carryforward tickers per scan tick (depending on market regime and recent setup density). Most will be the same names already in organic paths; the marginal admit is RVMD-class names on one-day RS dips.

**Architecture**: new SQL in `get_flag_universe`:
```sql
SELECT DISTINCT ticker FROM mi_flag_candidates
WHERE scan_date < $1::date AND scan_date >= ($1::date - INTERVAL '5 days')
  AND stage IN ('COILED', 'TIGHTENING')
```
Tag: `flag_stage_carryforward`. Same source-tag-list pattern as P7.2 / P7.3b carryforward paths. Multi-source admission preserved (a ticker in top-200 RS AND prior COILED captures both tags).

**Env flag**: `FLAG_STAGE_CARRYFORWARD_ENABLED=true` (default). Set false + docker compose restart to revert.

**Reversion-flag**: NEW (introduces 5th universe pattern).

**Status**: shipped 2026-05-19. Stage 1 verification: confirm RVMD appears in 2026-05-20 mi_flag_candidates with `universe_sources @> ARRAY['flag_stage_carryforward']` (and ideally re-enters COILED). Stage 2 telemetry: count carryforward-admitted tickers that progress to TRIGGERED over next 30d — if ≥10 carryforward-admitted tickers fire TRIGGERED, the fix is empirically validated.

### 2026-05-17 — P7.2 universe expansion: MAGNA53-failed carryforward

**Trigger**: R3 (drop Day-1 same-day re-entry) shipped 2026-05-17 morning leaves a known alpha-slip window — Block D audit found 65% of failed-Day-1 MAGNA53 alpha names made +5% within 21d, but only 34% caught by downstream detectors (continuation flag 31.6%, 9M EP 5.3%, sugar baby 0%, next MAGNA53 EP 0%). Sugar baby loosening (P7.1a) confirmed structurally insufficient (most names fail 9M-volume gate). The right hedge: feed R3-stopped MAGNA53 names directly into the flag detector's universe via universe-query expansion.

**Evidence**: P7.1a analysis on 76 alpha names from 60d Block D cohort — 22.4% recovery at sugar baby 0.50 cutoff (Option C verdict — sugar baby insufficient). MAGNA53-failed names are typically smaller-cap, lower-volume than 9M class. They're flag-candidate-class, not sugar-baby-class.

**Anticipated effect**: 3-10 R3-stopped names enter the flag scan's universe per scan tick (bursty around earnings season; ~1.3/day average). Flag detector evaluates them via the normal `compute_flag_metrics` — most enter as `unqualified` initially (base_age=1, runup not yet ≥50%), progress through WATCH → TIGHTENING → COILED as basing develops over 1-3 weeks. Targets ~60-70% downstream capture vs current 31.6%.

**Architecture**: modified `get_flag_universe` (db.py:2396) to return `dict[str, list[str]]` (ticker → source-tag list). New universe-pattern query: `WHERE alert_date >= scan_date - INTERVAL '7 days' AND status='closed' AND skip_reason='block:r3_reentry_disabled' AND account_mode='paper'`. Multi-source admission preserved — a ticker in top-200 RS AND R3-stopped captures both tags.

New `mi_flag_candidates.universe_sources TEXT[]` column records provenance for telemetry. Tag taxonomy: `rs_top200`, `rs_1m_80`, `momentum_25pct`, `magna53_failed_r3`, `ninem_universe_watch` (P7.3b — Monday). `ALTER TABLE ADD COLUMN IF NOT EXISTS` pattern, idempotent on restart.

**Env flag**: `MAGNA53_FLAG_CARRYFORWARD_ENABLED=true` (default). Set false + docker compose restart to revert.

**Reversion-flag**: NEW (introduces 4th universe pattern + audit-trail column).

**Status**: shipped 2026-05-17 commit `370aed1`. Stage 1 verification at Day 7-14 (universe pattern firing, looking for ≥1 R3-stopped name appearing in `mi_flag_candidates` with `universe_sources @> ARRAY['magna53_failed_r3']`). Stage 2 alpha-capture measurement at Day 21+.

### 2026-05-08 — Stable-anchor pivot (1% walk threshold)

**Trigger**: advisor flag 2026-05-08, deeper structural issue surfaced by VECO 5/06: pivot can walk forward on any new bar that beats prior pivot's high (even by 1¢). For a base making slow higher-highs in tight increments, pivot keeps walking and base_age stays near zero — contraction math never accumulates a window. The 5% → 2% band tightening (commit 42993e1) was a band-aid that addressed the volume-stealing-pivot symptom; this fix addresses the marginal-walk-forward cause.

**Evidence**: replay verification on three known calibration cases — XNDU progression unchanged (pivot stable at 04-16 throughout 4/22-5/01, every stage matches expected); VECO 4/27-5/06 base preserved with pivot at 04-24 (5/07 walks forward correctly after the +25% breakout decisively beats prior pivot); OKLO base at 04-23 preserved through 5/07 with fresh-tightening firing 5/04-5/05 as expected. No regressions on previously-correct stages.

**Anticipated effect**: pivots stay stable across the base regardless of marginal new highs in the lookback. Decisive breakouts (≥1% above prior pivot) still walk the anchor forward as today. Logic is conditional — only applies when prior pivot data is available AND prior pivot bar still falls within the current 25-session lookback. Cold start (no prior data) and aged-out (>25 sessions) cases fall through to the existing fresh-anchor logic. Same shape as the hysteresis pattern: state from yesterday's row carries forward by default, override only on decisive change.

**Reversion-flag**: NEW. Adds `_PIVOT_WALK_THRESHOLD = 0.01` constant and `prior_pivot_date` / `prior_pivot_high` kwargs through `compute_flag_metrics` → `_find_pivot_high`. New `db.get_yesterday_flag_pivots` helper mirrors `get_yesterday_flag_stages` shape (5-day lookback, DISTINCT ON ticker, filters NULL pivot fields).

**Status**: shipped 2026-05-08. Watch for: (a) bases that should reset but don't (look for pivot at age >20 with weak metrics); (b) surprise non-resets near the breakout (compare TRIGGERED rate before/after).

### 2026-05-08 — Tightened `_PIVOT_HIGH_BAND` 5% → 2%

**Trigger**: VECO 5/06 went TIGHTENING → unqualified the day before its +25% breakout. Pivot wrongly reset to 5/05 (high $52.16, 2.4% off period max $53.43 on 4/24) due to 5/05's high volume (3.0M vs 1.5M at 4/24). With pivot reset, `base_age = 0` → unqualified.

**Evidence**: 30d backtest of 6 pivot-shift cases in qualified candidates: COHU, AMSC, CORZ, FROG, TSHA all had new-pivot 2.6-4.9% off period max — all 5 blocked by 2% band. SGML new-pivot 1.2% off max → still moves (legitimate). 5 of 6 cases addressed.

**Anticipated effect**: fewer pivot resets on high-volume non-near-max-high bars; bases accumulate longer.

**Reversion-flag**: NEW.

**Status**: shipped (commit 42993e1), awaiting 5/8+ field validation.

### 2026-05-04 (session 6) — Burst-class universe + fresh-tightening COILED path

**Trigger**: OKLO 5/04 forming a visible flag with no detector hit. Replay surfaced two structural gaps: (a) universe gate excluded post-runup names whose composite RS is dragged down by pre-runup downtrend; (b) contraction math can't fire on short bases (early-vs-recent window overlap).

**Evidence**: OKLO 5/04 replay (`scripts/backfill_flag_xndu.py`); existing path catches XNDU 4/29-30 baseline.

**Anticipated effect**: (a) `get_flag_universe` adds OR-clause `rs_1m_pct ≥ 80 OR (last_close / trailing10_min - 1) ≥ 0.25`; (b) new `_compute_fresh_tightening` predicate creates alternative COILED path on `base_age ≥ 4 AND max(2bar TR%) ≤ 0.6 × ATR14% AND max(2bar vol) ≤ ADV20`.

**Reversion-flag**: NEW (both additions).

**Status**: shipped + validated (XNDU progression unchanged; OKLO 5/04 promotes to TIGHTENING).

### 2026-05-05 (session 5b) — Fresh-tightening dry-volume gate hybrid

**Trigger**: ADV20 climax-inflated for post-parabolic names — OKLO 5/04 hit 14.65M vs ADV20 15M = 0.98 (barely passing). The fresh-tightening predicate's volume gate against ADV20 alone was too lenient.

**Evidence**: OKLO 5/04 ratio 0.98 vs ADV20; 1.93× vs base recent. Same SSoT shape as `breakout_vol_ratio` denominator at flag_detector.py:369.

**Anticipated effect**: switched to hybrid ceiling `max(recent_5d_avg_vol, 0.5 × ADV20)`. Anchors on contraction floor; 0.5×ADV20 fallback prevents one sub-average bar from over-tightening the gate.

**Reversion-flag**: REFINEMENT of 2026-05-04 fresh-tightening ship.

**Status**: shipped + verified ($188 telemetry).

### 2026-05-01 — Initial Stage 1 ship (5-stage state machine, hysteresis, 17:25 ET cron)

**Trigger**: Plan in `~/.claude/plans/shiny-mapping-locket.md`. User-stated need: post-runup VCP / Qullamaggie tightening flags.

**Evidence**: Replay-driven calibration on XNDU 4/16-5/01 progression (WATCH → TIGHTENING → COILED → TRIGGERED → INVALIDATED).

**Status**: shipped (CLAUDE.md 2026-05-01 session 2).

---

Pre-2026-05-01 history is in CLAUDE.md / `CHANGELOG.md`. Backfill incrementally as touched.
