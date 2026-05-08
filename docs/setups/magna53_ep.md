# MAGNA53 EP — Episodic Pivot

**Phase**: Live (paper). Production-active.
**Origin**: Pradeep Bonde Episodic Pivot methodology + Marios Stamatoudis adaptation.
**Code**: `agents/market_intelligence/ep_detector.py`, scheduler 7:00–10:00 ET cron every 5 min.

## Definition

A liquid stock gaps significantly on a real catalyst (earnings, FDA, M&A, major news), with confirming volume and structural fitness (not extended, not in cooldown). The gap signals new information has changed the stock's fair value; entry on opening-range breakout (ORB) the same morning, with stop at ORB low.

This is the canonical Apollo entry strategy — the highest-volume, highest-conviction setup type.

## Universe / eligibility

- **Price**: prev_close ≥ $5
- **Liquidity**: pre-market dollar volume sufficient (relative + absolute floor — see PM volume gate)
- **Universe**: ~9,700 stocks via Polygon grouped daily
- **Cooldown**: 60-day cooldown after any prior EP alert, with carve-out for fresh earnings (see below)
- **Extension**: prev_close ≤ 1.50× SMA-10 (stocks already extended pre-gap don't qualify — chase risk)

## Detection criteria (current)

EP detection runs every 5 min from 7:00 AM to 10:00 AM ET. Each scan tick evaluates candidates against:

### Filters (any failure → skip)

1. **Pre-market volume**: relative gate — `pm_rvol ≥ MIN_PM_RVOL` (1.0× session-anchored RVOL@T)
2. **Pre-market shares absolute floor** (with carve-out): `today_volume ≥ MIN_PREMARKET_SHARES` (25,000) UNLESS `pm_rvol ≥ 5×` — relative anomaly trumps absolute count for low-float names
3. **EP cooldown**: skip if alerted within last 60 days, UNLESS `gap_pct ≥ 15% AND is_earnings_day` (fresh earnings catalyst bypasses cooldown)
4. **Extension cap**: prev_close > 1.50× SMA-10 → skip
5. **Already scored today**: dedup within scan day
6. **M&A filter** (`ma_filter.is_likely_ma`): catalyst='mna' OR keyword scan OR Polygon news headlines — skip
7. **Session RVOL@T** (post-9:30): same primitive as pre-market, but session-anchored. Threshold `MIN_SESSION_RVOL = 1.0`

### Catalyst grading (Claude + Perplexity)

LLM classifier returns one of: `game_changer`, `strong`, `routine`, `mna`, or None.

**Earnings-day pre-score boost**: when `is_earnings_day(ticker, today)` returns True (within {yesterday, today}), upgrade catalyst from `routine` or None → `strong` BEFORE score computation. Audit event: `catalyst_earnings_boost`. This handles cases where the news scrape is hedged/hollow but yfinance confirms earnings (DDOG/AAON 5/07 class).

**Hedge-phrase downgrade**: if Perplexity answer contains hedge phrases ("no specific information", "couldn't find", etc.) AND catalyst is `game_changer`/`strong`, downgrade one notch. Audit event: `catalyst_pplx_hedge_downgrade`.

### Score computation (`_score_ep`)

Multi-factor: gap_pct + pm_rvol + catalyst_quality multiplier + regime + RS + extension. Catalyst weights:
- `game_changer`: 1.0×
- `strong`: 0.7×
- `routine`: 0.3×

Score thresholds:
- `< 50` → skip (below MODERATE)
- `50 ≤ score < ep_threshold` → MODERATE (briefing only)
- `≥ ep_threshold` (regime-dependent, typically 65-75) → HIGH (immediate Telegram + ORB submission window)

### Earnings-day MODERATE → HIGH override (legacy override, kept)

If `tier == MODERATE` AND `gap_pct ≥ 10%` AND `is_earnings_day` → promote to HIGH. Audit event: `earnings_override_applied`. This complements the pre-score boost — boost handles `routine` not reaching 50; override handles `strong` reaching 50-65 in non-Bull regimes.

### Submission window

HIGH alerts trigger ORB submission only when `now_et.hour == 9 AND now_et.minute < 45`. HIGHs at 9:45–9:59 → `WINDOW_OUT_OF_ORB`. 10:00 ET cleanup cancels any unfilled `order_placed`.

## Known limitations / open questions

1. ~~`is_earnings_day` fail-soft direction inconsistent~~ — **resolved 2026-05-08 (session 2)**. All four call sites (parabolic, EP boost, EP cooldown bypass, EP MODERATE→HIGH override) now treat yfinance error as `True` (earnings day). Defensive at each site: rather over-boost / over-bypass / over-promote on data outage than miss a real earnings EP.

2. **Earnings-boosted `strong` lacks agreement multiplier**: a fresh classifier-found `strong` gets 1.2× confidence multiplier from Claude+Perplexity agreement. An earnings-boosted `strong` (upgraded from `routine`) has multiplier=1.0 because the agreement step ran with the original `routine`. Boosted strong is structurally weaker than classifier-strong. Probably fine but worth knowing.

3. **FMP earnings-window pre-check** (Track B Layer 3, task #18): when an earnings-day match is known ahead of time, bias the Perplexity prompt toward earnings as the catalyst. Currently the prompt is generic and may surface analyst-rating blurbs instead of the actual earnings beat. Filed pending FMP earnings-calendar coverage research (S&P-500 limit on current tier).

4. **Stop-limit gap-through on fast movers** (FLEX 5/06 class): 0.5% buffer can't span 4%-in-60-seconds moves. Telemetry filed (task #22) before considering wider buffer or stop-market.

## Change log (newest first)

### 2026-05-08 (session 2) — Aligned `is_earnings_day` fail-soft direction across all 4 sites

**Trigger**: Advisor flag — three EP sites (boost, cooldown bypass, MODERATE→HIGH override) plus parabolic detector all handled yfinance errors with `False`, but the operational meaning of `False` differed per site (some permissive, some restrictive). Inconsistent and hard to reason about under outage.

**Evidence**: Logical.

**Anticipated effect**: on yfinance error → `earnings_today = True` everywhere. EP boost fires, cooldown bypasses, MODERATE→HIGH override promotes — all defensive (rather over-allow on data outage than miss a real earnings EP).

**Reversion-flag**: REFINEMENT.

**Status**: shipped.

### 2026-05-08 — Earnings-day pre-score catalyst boost

**Trigger**: DDOG 5/07 scored 30 every tick (gap 19-31%, pm_rvol 30-89×) — blocked by `score < 50 catalyst=routine`. AAON same. Both had earnings catalysts but the LLM classifier returned `routine` on hedged news scrape. Existing earnings-day MODERATE→HIGH override fires too late (requires score ≥ 50 first).

**Evidence**: Single-day case study (DDOG + AAON 5/07). 30d backtest in `mi_ep_scan_log` showed ~75-100 names blocked by `catalyst=routine` with score ≥ 30 + gap ≥ 10%; estimated 50-70% would be earnings-day matches under the boost. Live false-positive rate to be measured via `catalyst_earnings_boost` audit events on 5/8+ sessions.

**Anticipated effect**: ~40-70 boost firings per 30d. DDOG/AAON-class names promoted from score ~30 to ~70+ → cleared 50 threshold.

**Reversion-flag**: NEW.

**Status**: shipped (commit f5d1977). Field validation pending 5/8+ session.

### 2026-05-08 — EP cooldown bypass on fresh earnings catalyst

**Trigger**: HIMX 5/07 every tick blocked by `EP cooldown — alerted within last 60 days`. New earnings catalyst (gap +28%, pm_rvol 65×) doesn't reset cooldown. 60-day cooldown blocks legitimate quarterly re-firings.

**Evidence**: Single-day case study (HIMX 5/07).

**Anticipated effect**: cooldown bypassed when `gap_pct ≥ 15% AND is_earnings_day`. Routine post-news bumps still respect cooldown.

**Reversion-flag**: REFINEMENT of 60-day cooldown (no prior change to bypass logic).

**Status**: shipped (commit f5d1977). Audit event: `ep_cooldown_bypassed_earnings`.

### 2026-05-08 — Pre-market shares floor relative-anomaly carve-out

**Trigger**: AAON 5/07 early ticks blocked by `pre-mkt volume X < 25,000 shares` despite pm_rvol 32-60×. Absolute floor redundant with relative pm_rvol gate; low-float names always trip absolute regardless of relative anomaly.

**Evidence**: Single-day case study (AAON 5/07).

**Anticipated effect**: skip absolute floor when pm_rvol ≥ 5×. Keep absolute as fallback for names with no pm_rvol baseline.

**Reversion-flag**: NEW.

**Status**: shipped (commit f5d1977).

### 2026-05-08 — `is_earnings_day` window tightened ±1 day → {yesterday, today}

**Trigger**: advisor flag — earnings on `scan_date + 1` cannot have produced today's gap; matching them was over-permissive (sector-sympathy + earnings-later-in-week could false-positive).

**Evidence**: Logical (correctness fix, no quantified backtest needed).

**Reversion-flag**: REFINEMENT of CLAUDE.md 2026-05-05 ±1 day window.

**Status**: shipped (commit 035ad85). Affects EP boost + EP cooldown bypass + parabolic earnings exclusion.

### 2026-05-06 — Wave B #2: Unify EP volume gate to RVOL@T (one primitive, two anchors)

**Trigger**: HUT/BLMN/GLW HIGHs detected late at ~09:52 ET on 5/6, missing 9:45 ORB cutoff. Investigation surfaced three structurally distinct volume gates (pre-9:30 RVOL@T, 9:30-9:45 no gate, 9:45+ raw `today_5min_vol / 390min_ADV` ratio).

**Evidence**: Polygon minute aggs discriminator: HUT 9:31 → 7.29× RVOL@T, BLMN 9:31 → 11.84×, GLW 9:31 → 0.72× → 9:35 → 2.41× — all clear ≥1.0× before 9:45 cutoff.

**Anticipated effect**: collapsed three gates to one (RVOL@T with anchor selection — pm pre-9:30, session 9:30+). Threshold 1.0× for both anchors. Names like HUT/BLMN/GLW now qualify within first session minute.

**Reversion-flag**: REVERSAL of the prior three-phase architecture per user mandate ("having something the first 15 min makes no sense").

**Status**: shipped + validated against 5/7 morning session (no 09:52 pile-up; ep_filter_session_rvol firing correctly on SEZL/BLBD/ACVA/DGII at 09:46).

### 2026-05-03 — Catalyst hedge-phrase downgrade

**Trigger**: RDDT 5/01 catalyst pipeline returned "strong" with Evercore-initiation blurb instead of identifying the real driver (Q1 earnings beat). Perplexity returned hedged synthesis → Claude classified hollow news_summary as "strong".

**Evidence**: 1 case study + the structural argument that chained LLM calls hide their own data quality.

**Reversion-flag**: NEW.

**Status**: shipped + validated (CLAUDE.md 2026-05-05 confirmed firing).

### 2026-05-03 — pm_rvol gate universe: top-500 → $5M $-vol floor

**Trigger**: OMCL 4/28 HIGH alert (gap +22%) lost $1506. 30d audit showed 84.2% of HIGH alerts and 97.4% of MODERATE alerts silently bypassed the pm_rvol gate (rank 501+ outside top-500 universe). pm_rvol baseline was structurally non-functional for 85% of EP candidates.

**Evidence**: 30d audit: 32/38 HIGH, 37/38 MODERATE bypassed.

**Anticipated effect**: universe expanded ~5.3× (500 → 2647 tickers). Newly-included tickers warm up over ~10 trading days.

**Reversion-flag**: NEW.

**Status**: shipped (CLAUDE.md 2026-05-03).

---

Pre-2026-05-03 history is in CLAUDE.md "Recent Changes" / `CHANGELOG.md`. Backfill into this file as each section is touched.
