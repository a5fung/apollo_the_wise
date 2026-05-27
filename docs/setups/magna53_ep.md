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

**Earnings-day pre-score boost**: when `is_earnings_day(ticker, today)` returns True (within {yesterday, today}) AND `is_revenue_stage(ticker)` returns True (yfinance Revenue Average > 0), upgrade catalyst from `routine` or None → `strong` BEFORE score computation. Audit event: `catalyst_earnings_boost`. This handles cases where the news scrape is hedged/hollow but yfinance confirms earnings (DDOG/AAON 5/07 class). **Pre-revenue companies** (clinical-stage biotech, SPAC, blank-check — Revenue Average == 0): boost is SKIPPED with `catalyst_earnings_boost_skipped` audit event. Their "earnings" event is pipeline / trial commentary, not a Q-rev catalyst — applying the boost causes the rubric to engage and produce misleading "Q-rev YoY un-extractable" downgrades. The Q-rev rubric gate ALSO skips for pre-revenue companies (belt-and-suspenders) so Claude's organic catalyst grade stands. Trigger: IMVT 2026-05-20.

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

**Override-respects-downgrade rule (2026-05-27, #132).** If the same-ET-day `catalyst_earnings_revenue_weak_downgrade` event was logged for this ticker — the revenue-growth gate actively classified the earnings as low-quality (e.g. `q_rev_yoy_missing_no_prior_year_comparable`) — the override does NOT fire. Tier stays MODERATE. Audit event: `earnings_override_skipped_post_downgrade`. Origin: BBWI 2026-05-27 fired HIGH at 9:51 ET despite an explicit data-quality downgrade at 7:20 ET. The override is designed for the "news ingest lag" case where catalyst stayed `routine` because no headlines yet; an explicit data-quality downgrade is the opposite signal and must be respected. Fail-open on DB error (preserves news-ingest-lag tolerance).

### Submission window

HIGH alerts trigger ORB submission only when `now_et.hour == 9 AND now_et.minute < 45`. HIGHs at 9:45–9:59 → `WINDOW_OUT_OF_ORB`. 10:00 ET cleanup cancels any unfilled `order_placed`.

## Known limitations / open questions

1. ~~`is_earnings_day` fail-soft direction inconsistent~~ — **resolved 2026-05-08 (session 2)**. All four call sites (parabolic, EP boost, EP cooldown bypass, EP MODERATE→HIGH override) now treat yfinance error as `True` (earnings day). Defensive at each site: rather over-boost / over-bypass / over-promote on data outage than miss a real earnings EP.

2. **Earnings-boosted `strong` lacks agreement multiplier**: a fresh classifier-found `strong` gets 1.2× confidence multiplier from Claude+Perplexity agreement. An earnings-boosted `strong` (upgraded from `routine`) has multiplier=1.0 because the agreement step ran with the original `routine`. Boosted strong is structurally weaker than classifier-strong. Probably fine but worth knowing.

3. **FMP earnings-window pre-check** (Track B Layer 3, task #18): when an earnings-day match is known ahead of time, bias the Perplexity prompt toward earnings as the catalyst. Currently the prompt is generic and may surface analyst-rating blurbs instead of the actual earnings beat. Filed pending FMP earnings-calendar coverage research (S&P-500 limit on current tier).

4. **Stop-limit gap-through on fast movers** (FLEX 5/06 class): 0.5% buffer can't span 4%-in-60-seconds moves. Telemetry filed (task #22) before considering wider buffer or stop-market.

## Change log (newest first)

### 2026-05-27 — M&A filter Part B: sister-ticker possessive proximity check (#119)

**Trigger**: RGTI 2026-05-11 EP alert path still saw Polygon news-tagged M&A interpretation after Part A (#88) shipped. Part A required ticker in `insights` array AND M&A keyword in `sentiment_reasoning`. But the article's `reasoning` for RGTI was "Stock gained 8.29%...following IonQ's merger approval" — keyword present, but the deal belonged to IonQ (a sister-tagged ticker), not RGTI.

**Fix**: `reasoning_other_entity_owns_deal` — sentence-bounded look-back for `[CapitalizedWord]'s` possessive immediately preceding the M&A keyword. Block only when the possessor (case-insensitive) matches a sister ticker symbol from `insight_tickers` (with `.WS` warrant suffix stripped). Narrow by design — does NOT catch arbitrary company-name possessives (no name→ticker map available; e.g., "Hewlett-Packard's deal" on HPQ-tagged article passes through).

**11-case replay verification** (`scripts/_replay_88_mna_filter_fix.py`): 11/11 pass. D + EL TPs kept (zero regression), QBTS/RGTI/MNST/ONDS/INFQ/NBIS/NXT/IREN/FOUR FPs blocked (one via Part B specifically, others via existing Path B keyword-absent gate). PINS = ARTICLE_NOT_FOUND in Polygon (corpus issue, not logic).

**Position in Path B flow**: between the `matches_mna_keywords(reasoning)` check and the existing direction check — additive gate, doesn't restructure Part A. Per advisor 2026-05-27.

### 2026-05-27 — Override respects revenue-weak downgrade + Claude text fallback (#131/#132)

**Trigger**: BBWI 2026-05-27 fired HIGH EP at 9:51 ET despite the revenue-growth gate downgrading it at 7:20 ET (`q_rev_yoy_missing_no_prior_year_comparable`). Override path was unconditional on catalyst quality.

**Fix #132** (override-respects-downgrade): before applying `earnings_override_applied`, query mi_audit_log for a same-ET-day `catalyst_earnings_revenue_weak_downgrade` row for this ticker. If present, skip the override + emit `earnings_override_skipped_post_downgrade`. Tier stays MODERATE. Fail-open on DB error (preserves news-ingest-lag tolerance — the original override design goal).

**Fix #131** (Claude text fallback for extraction + boost): CRSR 2026-05-27 had no rubric block — extraction gated on `earnings_today_match` from yfinance, which missed CRSR's Q1 date. Added `_claude_text_signals_earnings(claude_analysis)` regex (conservative — only matches `Q[1-4] earnings`, `EPS of $X`, `revenue of $XM`, `beat/missed consensus`, `earnings release`). Applied to BOTH the boost gate (line 1229) AND the extraction gate (line 1280) so yfinance ingest-lag doesn't silently kill the rubric OR the catalyst quality lift.

**Override hierarchy after these fixes** (in evaluation order on a MODERATE+gap≥10 alert):
1. `is_earnings_day` via yfinance OR Claude text signal → check
2. If revenue-weak downgrade present today → skip override (tier stays MODERATE), audit `earnings_override_skipped_post_downgrade`
3. Else → fire `earnings_override_applied`, tier=HIGH

**Why these aren't band-aids**: BBWI's downgrade was an active quality decision (no prior-year revenue comparable = can't verify YoY growth = can't grade the earnings). Honoring it preserves the rubric's gating value. CRSR's missing rubric was pure ingest lag at yfinance — Claude's prose had the data the structured-metrics extractor needed.

### 2026-05-23 — M&A filter: Polygon news multi-ticker-tag-bleed fix (#88)

**Trigger**: 2026-05-22 L2 anomaly fired `mna_filter_fired` at 210 events vs 10 median (21× normal). Investigation surfaced 3 of 4 affected tickers (INFQ/QBTS/RGTI — all quantum names in our persistent Sugar Babies cohort) were false positives from a single 2026-05-11 Motley Fool sector roundup tagged with their symbols but only *about* IonQ/SkyWater. QBTS — the Pradeep Sugar Baby example shipped 2026-05-22 #80 — was being silently filtered out of 9M EP alerts. 90d audit walk surfaced ~77% FP rate on this polygon_news layer (3 TPs / 13 cases = 23% TP rate).

**Bug class**: Polygon's `/v2/reference/news` API returns articles tagged with multiple tickers. The previous filter ran `matches_mna_keywords(title) or matches_mna_keywords(description)` on each tagged article without verifying that *this* ticker was the article's M&A subject. Distinct from the closed `perplexity_hallucination_keyword_leak` review (Perplexity disclaimer text leak; that's catalyst_texts path, not polygon_news path) and from the 2026-05-13 NBIS direction-blindness fix (which removed keywords; this preserves keywords but adds an article-subject discriminator).

**Fix** (`ma_filter.polygon_news_has_mna_headline`, two-path acceptance):
- **Path A — title match**: M&A keyword in article TITLE → accept (high specificity, preserves existing behavior for explicit-target articles like EL "Walks Away From Merger Talks").
- **Path B — description-only match**: requires (i) ticker in article's `insights` array (Polygon's per-ticker AI tagging, a proxy for "article is about this ticker"), AND (ii) ticker's `sentiment_reasoning` itself contains an M&A keyword (proxy for "Polygon's AI thinks this ticker's move is M&A-driven").
- Missing `insights` field → SKIP article (conservative; emits `polygon_news_insights_missing` audit event for false-negative quantification).
- Loop semantics: continue past Path-B-rejected articles, don't terminate at first rejection.

Companion change in `collector.get_polygon_news`: expose `tickers` array + `insights` per-ticker structure that the API already returns (previously dropped).

**Evidence (backward-replay against 13 historical mi_audit_log cases via `scripts/_replay_88_mna_filter_fix.py`)**:
- 2/2 TPs preserved (D ×2 Dominion, EL via Path A)
- 8/10 FPs blocked (QBTS, MNST, ONDS, INFQ, NBIS, NXT, IREN, FOUR) — including the QBTS Pradeep-cohort case
- 2 still-FP: RGTI sympathy-merger reasoning bleed (Polygon's AI tagged "IonQ's merger" in RGTI's reasoning); PINS article not found in 21d window (data gap, not logic gap)

**Residual class** filed as #90 (M&A filter direction-blindness through Polygon news description matches) — covers RGTI sympathy-bleed + future cases where reasoning text mentions a competitor's M&A.

**Reversion flag**: REFINEMENT (narrowing FP class without changing detection criteria semantics). No backward action required if reverted — filter would just over-fire as before.

**Status**: shipped 2026-05-23.

### 2026-05-21 PM — REVENUE_STAGE_MIN_USD code default REVERTED to $5M (#68, advisor flagged)

**Trigger**: Today's earlier #63 ship (lower default to $0.01) was based on yesterday's #50 verdict that pre-revenue ($0 Revenue Avg) band had 67% 5d WR. Today's #59 hygiene fix (dedup mi_ep_alerts duplicates) revealed yesterday's cohort was polluted by KOD ×6 + KPTI ×4 + TH ×16 duplicate rows. Clean cohort puts $0 band at 14% WR / -8% avg — a LOSER band, not a winner.

**Decision**: The evidence supporting #63 ($0.01 default) has been retracted. At N=7 clean we don't have evidence supporting EITHER threshold, so the code default reverts to the conservative-block stance ($5M, what the original IMVT/ROIV ratchet aimed at). Prod env override stays at `REVENUE_STAGE_MIN_USD=0.01` as operator-pinned, explicitly provisional pending #55 at 2026-06-20.

**Status**: shipped 2026-05-21 PM (pending).

### 2026-05-21 AM — REVENUE_STAGE_MIN_USD code default lowered to $0.01 (#63, since reverted)

**Trigger**: Advisor review 2026-05-20 PM flagged that the code default ($5M) and prod env-var override ($0.01) had diverged. A fresh prod rebuild without the env-var set would silently regress to the over-blocking $5M value. Backward check (#50, 2026-05-20) showed the $0 Revenue Avg band had 67% 5d WR — $5M would have over-blocked profitable EPs.

**Fix**: changed code default from `5000000` to `0.01`. Documentation, function docstring, and SSoT updated. Operators wanting to TIGHTEN (experiment) override via env var; conservative default protects against rebuild regression.

**Status**: shipped 2026-05-21 commit (pending).

### 2026-05-20 — Pre-revenue gate: skip earnings boost + rubric for clinical-stage / SPAC

**Trigger**: IMVT 2026-05-20 morning. Catalyst classifier graded `routine` (no qualifying news), but `is_earnings_day=True` boosted it to `strong`. Q-rev YoY rubric then engaged, found no revenue data in news (because IMVT is a clinical-stage biotech with $0 expected revenue per yfinance Revenue Average), downgraded back to `routine` with reason `q_rev_yoy_unextractable_quality_low`. Net: same final state (routine) but operator-facing message blamed the wrong cause — implied rubric/extraction problem when the real issue was that the boost shouldn't have fired for a pre-revenue company.

**Bug class**: structural gate inversion (same as 2026-05-19 RVMD flag-universe fix). The earnings boost + Q-rev gate assume revenue-stage business. Pre-revenue companies (clinical-stage biotech, SPAC, blank-check) structurally can't satisfy the gate; applying it produces misleading downgrades. Sample-size discipline doesn't apply to gate inversions — fix is correctness, not threshold tuning.

**Architecture**:
- New helper `is_revenue_stage(ticker)` in `earnings_calendar.py` — reads `yfinance.Ticker.calendar.Revenue Average`. Returns True if ≥ threshold (default $0.01 as of 2026-05-21 — see change log below), False otherwise (pre-revenue / pipeline-driven). Threshold env-tunable via `REVENUE_STAGE_MIN_USD`. Fail-soft to True on any error.
- Earnings boost in `ep_detector.py` now gated on `earnings_today_match AND revenue_stage`. Pre-revenue companies on earnings day get `catalyst_earnings_boost_skipped` audit event (operator visibility — explains why no boost fired).
- Q-rev rubric gate ALSO gated on `revenue_stage` (belt-and-suspenders). Even if Claude graded strong on an organic clinical-stage catalyst (FDA, trial, M&A), the rubric won't engage and produce misleading downgrades. Claude's verdict stands.
- Per-ticker cache `_REV_STAGE_CACHE` (same lifecycle as `_CACHE` in earnings_calendar.py) — single yfinance call per ticker per day.

**Anticipated effect**: clinical-stage biotechs, SPACs, blank-check companies gapping on earnings-day news will no longer get spurious "Q-rev YoY un-extractable" downgrades. Catalyst grade stays at Claude's organic verdict. Final HIGH-alert behavior unchanged for the IMVT-class (catalyst remained routine pre-fix, will remain routine post-fix — just with cleaner audit message).

**Reversion-flag**: NEW (introduces revenue-stage check). To revert: set the gate booleans to `revenue_stage=True` unconditionally.

**Status**: shipped 2026-05-20.

### 2026-05-17 PM — P7.2: MAGNA53→flag carryforward (R3 alpha-slip hedge)

**Trigger**: R3 shipped this morning leaves a known alpha-slip window — 65% of failed-Day-1 alpha names made +5% within 21d, only 34% caught downstream. P7.1a sugar baby analysis confirmed loosening doesn't address the structural gap. Architectural hedge: feed R3-stopped MAGNA53 names into the continuation-flag detector's universe so the basing/tightness state machine catches the delayed-EP breakout.

**Evidence**: Block D audit (60d cohort) + P7.1a sugar baby recovery analysis (22.4% recovery at 0.50 cutoff, mostly fails 9M-volume gate not close_in_range).

**Anticipated effect**: ~1.3 R3-stopped names enter the flag scan's universe per day (bursty around earnings). Flag detector evaluates organically; most enter as `unqualified` initially, progress through stages over 1-3 weeks. Targets ~60-70% downstream capture lift from current 34%.

**Code**: see `docs/setups/flag_continuation.md` 2026-05-17 entry for implementation details. MAGNA53 detector itself unchanged — this is a downstream-detector universe expansion.

**Reversion-flag**: NEW (paired with R3 ship). Env `MAGNA53_FLAG_CARRYFORWARD_ENABLED=false` reverts.

**Status**: shipped 2026-05-17 commit `370aed1`. Verification at Day 7-14 (Stage 1 plumbing) and Day 21+ (Stage 2 alpha capture re-measurement).

### 2026-05-17 — EP Selectivity Phase 2 — five filter ships (R2/R6/R4/R1/R3) + bug fixes

Bundle commit per `~/.claude/plans/i-want-to-plan-groovy-horizon.md`. Phase 1 diagnostic in `docs/decisions/0003-ep-selectivity-overhaul.md`. Phase 2 ships these in risk-ordered sequence as separate commits with feature flags. Each entry below has its own block per CHANGE_PROCESS format.

---

#### P2.0a — Fundamentals fetcher temporal-mismatch fix (commit `68ae8d8`)

**Trigger**: 2026-05-17 user asked "what made VSNT a game_changer, I can't see it?" — VSNT scored composite=32.5 from fabricated 40,000%+ revenue growth via index-based `[i+4]` Y/Y lookup that compared 2026 Q1 ($1.687B) to 2012 Q3 ($3M). Polygon's `sort=filing_date` interleaves late-filed Q4 with current quarters.

**Evidence**: 25 of 97 cohort tickers had temporal-mismatch class: VSNT (14yr gap), ARX (11.5yr), TE (8.7yr), VG (3yr), TTMI (1.5yr), KALV/YSS (1yr), HUT/KYTX/NMAX/ORKA/PACS (out-of-order duplicates), 17 names with annual-only gaps. Affects rubric scoring on the cohort that contains the next NBIS-class winner.

**Anticipated effect**: catalyst rubric scores trustworthy across 100% of cohort. VSNT 32.5 → 17.3 (routine_correct). ARX 24.4 → 17.3. KLAR 0.0 → 17.3 (matches user expected). AEHR contracting -44% now correctly captured (was fabricated). Label distribution: 0/3/14/33 → 0/10/35/52 (gc/strong/RC/weak) — more honest spread.

**Reversion-flag**: REFINEMENT of `fetch_polygon_quarterlies` (no prior version).

**Status**: shipped 2026-05-17. Field validation: re-run rubric scorer on cohort N≥20 next month; verify no fabricated game_changer/strong from temporal mismatch.

---

#### P2.0b — Leveraged ETF universe gap, fail-safe (commit `68dc6da`)

**Trigger**: USAX + USGG admitted as MAGNA53 EP candidates on 2026-04-20 (operator labeled "N/A — leveraged ETF, should not be evaluated"). Root cause: `mi_security_types` weekly Monday refresh hadn't classified them yet; the existing `WHERE security_type NOT IN ('CS', 'ADRC')` filter only catches names ALREADY in the table.

**Evidence**: 2 confirmed cases in 30d label cohort. Polygon issues ETF classification within hours of listing; old weekly refresh leaves a 7-day gap.

**Anticipated effect**: unclassified tickers (not in either `_non_stock_tickers` nor `_known_stock_tickers`) skipped per scan tick. Aggregate counter logged at scan end so we know if the weekly refresh is overdue. Fail-safe direction: prefer to miss a new IPO Day-1 than admit an ETF.

**Reversion-flag**: NEW (no prior unclassified guard).

**Status**: shipped 2026-05-17. Followup filed in BACKLOG: if `_unclassified_skipped` consistently ≥10/scan, bump weekly→daily refresh cadence.

---

#### P2.1a (R2) — Lift gap floor 8% → 10% (commit `9787527`)

**Trigger**: ADR 0003 §3 cohort breakdowns: 8-10% gap bucket had **0/8 win rate** over 60d. 10-15% bucket 51.2% WR. Cleanest single-threshold cut.

**Evidence**: 60d cohort (165 alerts) breakdowns:
- 25%+ : 41.7% WR
- 15-25% : 51.2% WR
- 10-15% : 43.9% WR
- **8-10% : 0.0% WR (n=8)**

**Anticipated effect**: -8 alerts / 165 cohort = -5% direct volume reduction + downstream tightening of top-20-gap filtering.

**Reversion-flag**: NEW. Env override available: `EP_MIN_GAP_PCT=8.0`.

**Status**: shipped 2026-05-17. Field validation: 7-day post-ship HIGH-alert volume drop expected.

---

#### P2.1b (R6) — PM-shares carve-out for high-conviction names (commit `939c314`)

**Trigger**: CPA 5/14 (gap 13.12%, score 67.7, catalyst strong) was held 24 min by pre-catalyst pm-shares floor. Class B miss. Existing carve-out only bypasses on `pm_rvol ≥ 5x` — doesn't catch CPA-class where pm volume hasn't built relative ratio yet despite real catalyst.

**Evidence**: 3 documented cases (CPA + 2 others) in 60d where pm-shares floor blocked clean Class-A entries. Per pre-ship LLM-cost analysis: moving gate post-catalyst adds ~3-10 LLM calls/day (trivial).

**Anticipated effect**: new carve-out admits names with `gap ≥ 10% AND catalyst_quality='strong'`. Original `pm_rvol ≥ 5x` carve-out preserved. Architectural change: pm-shares gate moved from pre-catalyst (line 818) to post-catalyst (after routine-catalyst skip ~993).

**Reversion-flag**: REFINEMENT of 2026-05-08 (original pm_rvol carve-out). Env override: `R6_PMSHARES_CARVEOUT_ENABLED=false` disables NEW carve-out only.

**Status**: shipped 2026-05-17. Field validation: monitor for false-positives (low-pm-volume names admitted that fade).

---

#### P2.1c (R4) — In-theme +10 scoring bonus (telemetry-only) (commit `cf9167c`)

**Trigger**: Catalyst label cross-tab §4: in-theme alerts 67% WR vs uncovered 40% WR. 27pp lift. Theme heat is the single cleanest separator between real-strong and mislabeled-strong (30% in-theme rate for "strong" vs 7.1% for "routine_mislabeled").

**Evidence**: 60d cohort with operator labels.

**Pre-ship verification** (per `feedback_sample_size_discipline`): SQL check found **0 MODERATE-in-theme alerts would have crossed ep_threshold=70 with +10 bonus** in 60d cohort. R4 is decorative under current thresholds; shipped for telemetry/visibility only.

**Anticipated effect**: zero immediate selectivity change. Score breakdown captures theme context in `mi_ep_alerts.breakdown` JSON. Phase 5 meta-rubric will compose theme_context as separate input with calibrated weights. Paired-data signal for Phase 5 regression.

**Reversion-flag**: NEW. Env override: `R4_THEME_BONUS_ENABLED=false`.

**Status**: shipped 2026-05-17 as telemetry. Phase 5 calibration will determine production weighting.

---

#### P2.1d (R1) — Drop MODERATE auto-actions (investigated, NO CODE CHANGE)

**Trigger**: ADR 0003 R1 recommendation based on observed 28% WR for MODERATE vs 52% for HIGH.

**Investigation finding**: every entry pipeline already filters `score_tier = 'HIGH'`:
- `live_tracker.py:324`, `backtester/tracker.py:251`, `backtester/engine.py:534`
- `broker/shadow_orb_tracker.py:346`, `audit_invariants.py:387/404`
- `scheduler.py:1621`, `system_audit.py:188/196/354`

Data confirmation: **0 MODERATE alerts in mi_live_trades over 60d** (paper account, entry_price NOT NULL). Cross-strategy allocator enqueues MODERATE but is shadow-only.

The earnings-boost MODERATE→HIGH promotion path (line 1276) is preserved as methodologically correct per CLAUDE.md B12.

**Anticipated effect**: none — current architecture already enforces R1.

**Reversion-flag**: n/a (no change shipped). Defensive env-flagged guard filed in BACKLOG as low-priority follow-up.

**Status**: verified 2026-05-17 — no code change required.

---

#### P2.1e (R3) — Drop Day-1 same-day re-entry (commit `643a577`)

**Trigger**: ADR 0003 §3 — 0/6 re-entry win rate over 60d cohort. Methodology: failed first breakout invalidates the setup; same-day re-entry chases the failure.

**Evidence**: 6 re-entry attempts in 60d, all losers, avg ret -6.0%.

**Implementation**: env-flagged early gate in `attempt_day1_reentry()` (broker/order_manager.py:430). When R3 active (default): record stop_hit exit, close trade with `skip_reason='block:r3_reentry_disabled'`, emit `r3_day1_reentry_blocked` audit event.

**⚠ Known alpha-slip risk window** (per Block D audit):
- 112 MAGNA53 HIGH alerts failed Day 1 in 60d (97.4%)
- 76 of those (69%) made +5% within 21d
- Only 34% captured by downstream detectors (continuation flag 31.6%, sugar baby 0%, next MAGNA53 EP 0%)
- 66% of alpha slips through entirely
- Back-of-envelope: ~$625/day expected uncaptured alpha at typical position size

**⚠ PAIRED PHASE 7 WORK BUMPED TO NEXT-UP** (target completion 2026-05-24):
- P7.1 Sugar baby filter audit (0% capture is structurally broken)
- P7.2 MAGNA53 → continuation-flag carryforward (lift 31.6% → ~60-70%)
- P7.3 9M cohort delayed-EP audit

**If Phase 7 slips beyond 2026-05-24**: reconsider R3 reversion (set `R3_DAY1_REENTRY_ENABLED=true`) until paired work closes the gap.

**Reversion-flag**: NEW. Env override: `R3_DAY1_REENTRY_ENABLED=true` re-enables re-entry.

**Status**: shipped 2026-05-17 with paired-Phase-7 dependency. Field validation: monitor `r3_day1_reentry_blocked` audit events + Phase 7 Block D re-run after P7.2 ships.

---

### 2026-05-13 — M&A filter: drop direction-blind keywords (NBIS class)

**Trigger**: NBIS 5/13 was filtered as `M&A/buyout catalyst — no momentum trade` despite being the **acquirer** (bought Eigen AI for $643M). The keyword scanner in `ma_filter._MNA_KEYWORDS` matched bare `"acquire"` / `"acquisition"` regardless of which side of the deal the ticker was on — direction-blind substring scan. NBIS gapped +15.79%, pm_rvol 6.4× — clean EP setup lost.

**Evidence**: 90d audit-log backtest (`mna_filter_fired` events, 2026-02-12 → 2026-05-13). 16 distinct tickers caught by bare `"acquire"`/`"acquisition"`:
- **13 false positives** (acquirer or unrelated keyword mention): NBIS, WAT, MNST, FOUR, RKLB, IREN, VEEV, KGS, NXT, PINS, QBTS, QUBT, RAL.
- **3 nominal true positives**: EBAY (still caught via Claude `catalyst_quality='mna'`), WEN (recovered by adding `"take-private"`), GLIBK (the keyword matched accidentally in unrelated biotech chatter — Perplexity returned "no info"; structurally a FP that happened to land on a real target).

Other keywords spot-checked (90d): `buyout` (GBTG, WEN — both TP), `halper sadeh` (OGN — TP), `takeover` (WEN — TP), `merger` (KALV TP, RAL FP), `strategic transaction` (P FP, N=1). Retained — true-positive yield holds.

**Anticipated effect**: ~13 false positives / 90d eliminated (~1 per week). Zero genuine M&A targets lost — EBAY-class caught by Claude classifier branch; WEN-class caught by new `"take-private"` / `"private deal for"` phrasings. The 2 minor non-`acquire` FPs (RAL/P) are Perplexity-hallucination leaks (separate bug class).

**Reversion-flag**: REFINEMENT of `is_likely_ma` (no prior change to keyword direction-handling).

**Status**: shipped 2026-05-13. Field validation: monitor `mna_filter_fired` events for residual acquirer-side hits.

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
