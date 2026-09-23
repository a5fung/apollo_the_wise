# Parabolic Short

**Phase**: Shadow (telemetry-only). Promotion path: `telemetry_review` per `strategies/registry.py`.
**Origin**: Stamatoudis / Quallamaggie methodology — short the climax of a multi-week vertical run, expecting violent mean-reversion.
**Code**: `agents/market_intelligence/parabolic_detector.py`, scheduler 17:15 ET cron `parabolic_scan`.

## Definition

A stock that has gone vertically up over weeks (parabolic) eventually exhausts and reverses. Entry on the first confirmed reversal candle after the blow-off top. Asymmetric R:R when timed: stop above the parabolic high, target is mean-reversion crash (often 50-80%+ retracement).

**The setup is short-side only.** Long-side base/breakout patterns (flag continuation, EP) share visual surface features (gap up, big volume, big range) with a parabolic climax candle but are NOT this setup — they belong in `flag_continuation.md` / `magna53_ep.md`.

## Universe / eligibility

- **Liquidity**: dollar volume ≥ $10M today (so the position can be entered + borrowed)
- **Security type**: CS/ADRC only, or unknown (rejects ETFs/funds via `mi_security_types`) — SQL pre-filter, `db.get_parabolic_universe`
- **Price**: close ≥ $5
- **Cap-tier prior-move thresholds** (Qullamaggie):
  - Large cap (≥ $10B): prior_move ≥ 50%
  - Mid cap ($2-10B): prior_move ≥ 100%
  - Small cap (< $2B): prior_move ≥ 200%
- **History**: ≥ 60 prior sessions (need history for SMA-50 + base anchor walk)
- Universe sourced from daily history via a permissive SQL pre-filter (false positives are fine —
  they hit the per-ticker compute and resolve to `unqualified`); per-ticker compute runs under
  `asyncio.Semaphore(10)` bounded concurrency (`_SCAN_CONCURRENCY`, parabolic_detector.py:37),
  not serial.

### HARD-GATE filter: M&A / one-shot-news exclusion (Perplexity)

Climax/anticipation candidates (not `watch` — no Telegram alert, no API spend justified) are run
through `_apply_exclusions` → `_news_check_for_exclusion` (parabolic_detector.py ~509): a Perplexity
query asks whether the move was driven by a buyout/acquisition/merger/take-private/FDA
approval/lawsuit ruling/earnings surprise in the last 30 days. A positive (`is_event_driven=true`)
verdict excludes the candidate from Telegram/alert (row persists with `excluded_reason` /
`excluded_source` / `excluded_detail` in `mi_parabolic_candidates`, so filtered names are still
reviewable). Verdicts cache in `mi_parabolic_exclusions` with a TTL so a repeat scan short-circuits
without another Perplexity call. Fail-open: any Perplexity error or unparseable verdict → do NOT
exclude (noise reducer, not a safety gate).

## Detection criteria (current)

The compute function (`compute_parabolic_metrics`, `parabolic_detector.py:198`) emits a stage per (ticker, scan_date):

### Qualifying gates (all required to enter watch tier)

1. **Liquidity**: today's `close × volume ≥ $10M`
2. **Prior move from base**: `(today_close / base_low) - 1 ≥ cap_tier_threshold`
   - `base_low` = first close ≤ SMA-20 walking back from today, within 60 sessions; or 60d-ago low if no touch
3. **Extension vs SMAs**: `today_close / SMA-50 ≥ 1.50`
4. **Velocity-delta** (parabolic curve, not linear): daily compound rate over 5d > 1.10× daily compound rate over 20d
   - Daily rates: `(1 + roc_n) ^ (1/n) − 1`
   - Threshold 1.10 holds names through 1-2 day pre-climax consolidation (CAR 4/20 had 1.11)

### Burst checklist (≥ 3 of 4 needed for BOTH anticipation and climax — same `burst_score >= _MIN_ANTICIPATION_SCORE` threshold; climax adds the 2 extra hard gates below, not a stricter burst count)

1. `days_up_streak ≥ 3` — consecutive close > prior close ending today
2. `gap_count_3d ≥ 2` — last 3 sessions where open > prior close × 1.01
3. `range_expansion_count_3d ≥ 2` — bar range > prior bar range
4. `vol_expansion_count_3d ≥ 2` — bar volume > prior bar volume

### Climax tier (final stage promotion)

`stage = 'climax'` requires all of:
- Burst score ≥ 3 of 4
- `gapped_today` (today open > yesterday close × 1.02)
- `climax_volume_flag` (today volume = max over last 20 sessions)
- **HARD gate 1**: `days_up_streak >= 3` (parabolic short = vertical multi-day acceleration into climax day; 1-2 up days means flat-base catalyst gap, not exhaustion)
- **HARD gate 2**: `not is_earnings_today` (earnings catalyst is fresh news, not climax exhaustion; AGL/XMTR 5/07 false-climax class)

### Stages

- `unqualified` — any qualifying gate fails. Persisted, no alert.
- `watch` — qualifying gates pass, burst < 3.
- `anticipation` — burst ≥ 3 but climax hard gates fail. Telegram watchlist.
- `climax` — burst ≥ 3 + climax hard gates pass. Telegram trigger candle.

## Stage transitions / hysteresis

None currently. Each scan_date computes stage independently from prior scans. Promotion/demotion fires immediately based on that day's data. (Flag continuation has hysteresis; parabolic doesn't.)

## Known limitations / open questions

1. **Pivot anchoring is unstable** (advisor flag 2026-05-08): pivot can walk forward on any new bar that beats prior pivot's high (even by 1¢). For a base making slow higher-highs in tight increments, pivot keeps moving and base never accumulates. The current band-tightening (5% → 2%) helps but isn't the principled fix. **Stable-anchor approach** (once pivot established, only move on strict break exceeding prior pivot's high by N%) is filed for next session. Note: this is `flag_continuation.md`'s issue too — both share the pivot logic.

2. ~~Earnings-day check has fail-soft inconsistency~~ — **resolved 2026-05-08**. All four sites (parabolic, EP boost, EP cooldown bypass, EP MODERATE→HIGH override) now treat yfinance error as "earnings day = True". Defensive direction at each site: parabolic suppresses climax, EP boost fires, cooldown bypasses, override promotes.

## Change log (newest first)

### 2026-07-24 — FL-5 reconcile: doc synced to code

Four stale items corrected (no code change): (a) the Burst-checklist header claimed "all 4" burst
items needed for climax — code's climax gate uses the SAME `burst_score >= 3` threshold as
anticipation (`_MIN_ANTICIPATION_SCORE=3`) plus 2 SEPARATE hard gates (days_up_streak, earnings);
the doc's own "Climax tier" section already had this right, only the checklist header contradicted
it — header corrected; (b) cron time "17:25" → **17:15** ET (`scheduler.py` line 5370); (c)
"per-ticker compute serially" → `asyncio.Semaphore(10)` bounded concurrency (`_SCAN_CONCURRENCY`);
(d) added the undocumented universe gates (close ≥ $5, CS/ADRC-only, ≥60 prior sessions —
`db.get_parabolic_universe`) and the Perplexity-based M&A/one-shot-news exclusion
(`_news_check_for_exclusion`, parabolic_detector.py ~509) as a documented HARD-GATE filter (was
entirely undocumented, in violation of the CLAUDE.md hard-gate filter-list rule).

### 2026-05-08 (session 2) — Aligned `is_earnings_day` fail-soft direction across all 4 sites

**Trigger**: Advisor flag 2026-05-08 — three sites (parabolic, EP boost, EP cooldown bypass) had different exception-handling directions (False at all three meant: parabolic permissive / EP boost restrictive / EP cooldown restrictive). Inconsistent and harder to reason about under outage.

**Evidence**: Logical (correctness alignment, no quantified backtest needed).

**Anticipated effect**: on yfinance error, all 4 sites now `treat as earnings day = True`. Direction at each site is the most defensive: parabolic SUPPRESSES climax (no false signal on outage), EP boost FIRES (real EP not missed), cooldown BYPASSES (real fresh signal not blocked), MODERATE→HIGH override PROMOTES (real EP reaches HIGH tier).

**Reversion-flag**: REFINEMENT of the four prior earnings-day check ships.

**Status**: shipped.

### 2026-05-08 — Tightened `_PIVOT_HIGH_BAND` 5% → 2%

**Trigger**: VECO 5/6 went TIGHTENING → unqualified the day before its +25% breakout. Investigation surfaced that pivot logic picked a high-volume DOWN day (5/5, high $52.16) over the actual period max-high day (4/24, high $53.43) because 5/5 had 3.0M volume vs 4/24's 1.5M, and 5/5 was within 5% of max ($52.16 / $53.43 = 97.6%, 2.4% below).

**Evidence**: 30d backtest of 6 pivot-shift cases in qualified candidates: COHU, AMSC, CORZ, FROG, TSHA all had new-pivot 2.6-4.9% off period max — all 5 would be blocked by 2% band. SGML new-pivot 1.2% off max — would still move (legitimate). 5 of 6 cases addressed.

**Anticipated effect**: fewer pivot resets on high-volume non-near-max-high bars; bases accumulate longer; some genuine blow-off shooting-stars >2% off max may be missed (rare — typical shooting star is <1% off max).

**Reversion-flag**: NEW (no prior change to `_PIVOT_HIGH_BAND`).

**Status**: shipped (commit 42993e1), awaiting 5/8+ field validation.

### 2026-05-08 — Restored `days_up_streak >= 3` HARD gate (after same-day reversal)

**Trigger**: User clarified VECO is a long flag/EP setup, not a parabolic short. The original gate's intent — block flat-base earnings gaps — is correct. The earlier same-day revert was based on agent misclassifying VECO.

**Evidence**: User's framing: parabolic short methodology requires multi-day vertical acceleration into climax day; 1-2 up days going in is a flat-base catalyst gap by definition. Re-reviewing the 30d backtest filter list (AGL, AMD, ARM, VECO, OGN, INTC) with this lens, all 6 are flat-base catalyst gaps — not false negatives. The 38% filter rate is correct.

**Reversion-flag**: REVERSAL of same-day revert. Prior reasoning was wrong: agent classified VECO as "correctly flagged climax" without trader-judgment ground truth. Lesson logged in CHANGE_PROCESS.md rule #3: HARD gate filter lists require user sign-off.

**Status**: shipped (commit 80f2535).

### 2026-05-08 — (REVERTED same day) Removed `days_up_streak >= 3` HARD gate

**Trigger**: 30d backtest showed 38% climax filter rate (6 of 16). Agent assessed VECO as a false-negative (Pradeep textbook setup wrongly filtered) → softened the gate.

**Evidence**: 30d backtest filter list, agent classification (without user review).

**Reversion-flag**: REVERTED SAME DAY (commit 035ad85 → 80f2535).

**Status**: reverted.

### 2026-05-08 — Tightened `is_earnings_day` window from ±1 day to {yesterday, today}

**Trigger**: Earnings on `scan_date + 1` cannot have produced today's gap; matching them was over-permissive. Sympathy plays + earnings later in the week could trigger false-positive boost candidates.

**Evidence**: Logical (no quantified backtest — pure correctness fix).

**Reversion-flag**: REFINEMENT of the original ±1 day window from CLAUDE.md 2026-05-05.

**Status**: shipped (commit 035ad85). Not parabolic-specific (also affects EP boost + EP cooldown bypass).

### 2026-05-08 — Added `is_earnings_today` HARD gate for climax tier

**Trigger**: AGL 5/7 (560% prior_move, days_up=2) and XMTR 5/7 (113% prior_move, days_up=3) — both gapped on earnings from tight 3-week bases. Structurally not parabolic shorts (catalyst-driven gaps, not exhaustion).

**Evidence**: 2 case studies (AGL + XMTR). Backtest not run pre-deploy (process gap noted). User's framing endorsed the methodological reasoning.

**Anticipated effect**: earnings-day climaxes filtered. ~14 names per 30d are catalyst='routine' with earnings-boost-eligible structure; subset of those that also pass parabolic gates would have been false climaxes. Exact filter rate not measured pre-deploy.

**Reversion-flag**: NEW.

**Status**: shipped (commit f5d1977). Combined with days_up gate above.

### 2026-05-01 — Initial ship (Stage 1 telemetry, 17:15 ET cron)

**Trigger**: TI1 in `project_trading_ideas_backlog.md`. Implementation per `~/.claude/plans/shiny-mapping-locket.md`.

**Evidence**: Backfill against historical CAR 4/2026 (2 climaxes 4/7, 4/21 matching Mario's tweet timing), GME 1/2021 (3 anticipations during squeeze), NVDA 3/2024 (correctly rejected — not parabolic).

**Status**: shipped (commit per CLAUDE.md). Phase=shadow; no entry pipeline.
