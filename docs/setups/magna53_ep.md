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

### Catalyst grading (Claude + Perplexity + SEC EDGAR)

LLM classifier returns one of: `game_changer`, `strong`, `routine`, `mna`, or None.

**Grounded grade (2026-06-04, #187/#190 — catalyst-axis Track A+B; deployed live).** The grade now reasons on a GROUNDED, UNTRUNCATED summary — the authoritative **SEC 8-K body** (`collector.get_sec_recent_filings`, near-real-time `data.sec.gov/submissions` endpoint, error-wrapped) + the Perplexity web synthesis — NOT raw 200-char yfinance headlines. Model upgraded **Haiku → `claude-sonnet-4-6`**. New prompt rule: broad sector-momentum / short-squeeze / non-company-specific technical moves grade `routine` (a gap-up alone is not a catalyst).
- **WHY**: RUM 2026-06-04 traded −1.07R as a false `strong` — the real catalyst (a $270M NVIDIA-Blackwell GPU-cloud **8-K filed 5:04am ET**) reached neither LLM (no EDGAR ingestion existed), so Haiku confabulated `strong` from headlines while the grade truncated the synthesis to 200 chars.
- **EVIDENCE**: 30-case bake-off — grounded summary flips the false-`strong` junk (RUM/PGY/CRSR/DY, short-squeeze/sector-rotation/ticker-mismatch) → `routine`, and Haiku≈Sonnet≈Opus on identical input (so the **input** is the lever, not the model); RUM grounded+8-K → `strong` with the correct $270M rationale; B0 confirmed EDGAR is near-real-time and the 8-K was retrievable ~4.5h pre-scan.
- **SHIP not shadow** (move-fast): fails CONSERVATIVE — the SEC fetch + grade are error-wrapped (→ `routine`), so the worst failure mode is a missed alert, not a bad trade. Watched on the next 7–10am ET scan.
- **REVERSION**: drop the `grounded_text` path + the `claude-sonnet-4-6` model in `_classify_catalyst_claude`, and the `get_sec_recent_filings` gather entry → restores the headline-Haiku grade. Plan: `~/.claude/plans/i-want-to-plan-groovy-horizon.md`.

**Materiality (#189, 2026-06-04 — built + offline-validated; deploys AFTER the grounded-grade scan confirms).** The grade prompt now includes the company **market cap** + a rule: a contract/deal/order is `strong`/`game_changer` ONLY if its value is SIGNIFICANT vs the company's size (a meaningful fraction of market cap / revenue) — "news existence ≠ EP-grade." EVIDENCE: the same RUM $270M 8-K grades `strong` at RUM's ~$2.5B cap but `routine` at a synthetic $600B mega-cap (validated on Sonnet). REVERSION: drop the `Market cap:` prompt line + rule 5 + the `mktcap_str` computation. Change-isolation: deployed one scan-cycle after the grounded-grade re-arch so the two grade changes are verified separately.

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

### 2026-07-04 — #347: LIVE enriched grade corpus + acting re-poll (operator-approved flip)

- **What changed:** premarket EP grades now use the ENRICHED corpus (SEC 400d filings
  + content-bearing primary-subject Benzinga + Perplexity, graded at the 12k window)
  instead of the legacy 6k grounded_text; the catalyst-cache re-poll now ACTS — a valid
  late-source upgrade (the BFLY class) rewrites the grade cache (quality+analysis, boost
  reset to 1.0, filters_cleared=False → the S6 machinery re-filters and proceeds as a
  fresh survivor). In-window (9:30+) first-seen names keep the legacy corpus (the shadow
  never validated in-window grading — latency + fidelity to evidence).
- **Evidence:** 10-day prod shadow — 183 grades; the 32 raw changes collapse to 5 distinct
  events, ALL correct-direction in the operator walkthrough (CMCSA spin-off un-mna'd;
  ZSQR deflated; LBRDK caught; RKLB un-suppressed; APOG = the fail-routine case, see
  guard); dilution suppression 10/10; re-poll fired exactly once, cleanly. Operator
  sign-off 2026-07-04 AM ("flip approved").
- **Guards:** APOG-class — the enriched classify's fail-routine sentinel triggers a
  LEGACY-corpus fallback + `live_enriched_grade_failed` audit (never a silent
  fail-to-routine). The enrichment shadow auto-resumes in reversion mode.
- **Reversion:** runtime toggle `live_enriched_corpus` (mi_safeguard_state row, ≤60s, no
  redeploy — the #400 pattern) with `LIVE_ENRICHED_CORPUS` env fallback; flipping it off
  restores the legacy corpus AND re-arms the validation shadow.
- **Reversion-flag:** none prior — this is the first corpus change since the shadow began.

### 2026-06-20 — Live AUTO-ENTRY for the real-money cutover (operator-signed)

MAGNA53 at `phase=live` + `live_real_enabled=True` now **auto-enters real money** through
the shared `entry_pipeline.submit_trade_entry` funnel (previously every live entry sent a
manual [Confirm] Telegram proposal — auto-entry was never wired for live). START-SMALL =
the **$5,000 account** itself (operator 2026-06-20): `position_size_multiplier=1.0` (full
1% risk/trade) + NO tight count cap (`max_concurrent_positions=NULL` → global 5) for broad
participation on a low-WR strategy (#197). Entry detection/criteria are UNCHANGED — this is
an entry-MECHANIC change only. Full design,
safety envelope, reversion path, and the `/pause` HARD-gate reaffirmation live in
`safeguards.md` change log 2026-06-20 (the portfolio-entry SSoT). Verify-live = first
auto-entry Monday.

### 2026-06-19 — #344 catalyst corpus-completeness — SHADOW (live flip GATED)

**Trigger**: BFLY 6/18 ran +56% with no alert. Graded `routine` because (1) at the
7:00 ET grade its corpus was EMPTY (the Midjourney PR hit Benzinga at 8:12 ET, after the
grade) and the per-day catalyst cache pinned that routine grade all day, and (2) the
6/18 news was an *update to an existing material partnership* — the $74M Midjourney
co-development/license ($15M one-time + $10M/yr + $9M milestones) was disclosed in a
PRIOR 8-K (2025-11-18, item 1.01), never in the grade corpus. Operator labeled BFLY a
real EP (HARD gate); `routine` was wrong. Evidence: `docs/analysis/missed_ep_bfly_2026-06-18.md`,
`docs/analysis/late_source_replay_344_2026-06-19.md`. Cache re-poll ALONE recovers
nothing (the 8:12 PR is headline-only → re-grading it stays routine; proven 0/12 in the
replay) — its value is conditional on the enrichment.

**Change (SHADOW only — live grade UNCHANGED)**:
- `collector.get_alpaca_news(include_content=True)` — stop discarding full Benzinga PR
  bodies (grade path only; default off elsewhere).
- `ep_detector.assemble_grade_corpus` (SSoT; the #344 replay imports it) — anchors the
  grade DATE and appends age-labeled PRIOR item-1.01 agreement + item-2.02 revenue
  context for MATERIALITY sizing, explicitly NOT as today's catalyst (prevents the
  date-confusion that mis-dates stale filings as fresh). **Window budgeting (6/19 fix):**
  the grader slices `grounded_text[:max_chars]`; the appended context would be truncated by
  a long today's-news 8-K, so today's-news is capped to `_GRADE_TODAY_MAX_CHARS=6000` (the
  lean live grader's effective today-window) and the enriched corpus is graded with
  `_GRADE_ENRICH_MAX_CHARS=12000`. The live non-enriched path is unchanged (`max_chars`
  defaults to 6000).
- **#238 dilution feed** (2026-06-19): `assemble_grade_corpus(dilution_filing=)` also appends
  a dated, age-labeled NEGATIVE-context block when a recent 424B5 (priced takedown) or 8-K
  item 3.02 (actual equity sale) is on file — point-in-time (filed ≤ grade), 21-day recency
  window (`recent_dilution_filing`). Framed "weigh AGAINST today's move … but do NOT
  auto-reject — a real EP can coincide with an opportunistic raise": the LLM stays JUDGE (a
  deterministic skip would violate `feedback-catalyst-sourcing-direct-over-llm`). Separate
  tight 424B5/8-K fetch so a prospectus can't crowd the 400d agreement-finder; `has_dilution`
  / `dilution_form` on the shadow rows. Offline canary 6/19 (`docs/analysis/dilution_canary_238_2026-06-19.md`),
  block confirmed IN the grade window (after the truncation fix below): SAFETY direction
  PASSED — 4 names / 6 alerts incl. the false-positive-risk WDC, **0 wrong suppressions**; the
  one change (ELVN game_changer→strong) is a conservative temper that STILL FIRES and matches
  the live grade; SHAZ game_changer + 3.02 unchanged, WDC strong×2 + stale 8-K/A 3.02 unchanged.
  Suppression value (a catalyst-less pump held routine) was unexercised offline → watched on
  the live `has_dilution` rows at the #347 flip.
- `ep_grade_enrich_shadow` (uncached, once/ticker/day): current vs enriched grade,
  web-inclusive. `ep_repoll_shadow` (cached path): re-grade ONCE when a new primary-subject
  source lands after a routine grade in the ORB window (`should_repoll_shadow`; never
  re-polls a firing grade). Flag `ENRICH_SHADOW_ENABLED`; error-wrapped.

**Hot-path safety (advisor 6/19)**: the shadow runs SYNCHRONOUSLY on `run_ep_scan` (the
order-submission path), so it is **PREMARKET-ONLY** (< 9:30 ET) — it never adds SEC GETs /
a Sonnet call inside the 9:30–10:00 ORB entry window, and never contends with the live
grade's EDGAR fetch during entries. The 400d SEC fetch is bounded (`max_filings=8`) and
fetched once/ticker/day (the re-poll reuses it). Latency is logged (`shadow_latency_s`);
Monday verify includes a scan-wall-time check, not just "rows wrote". Cost: grade-path LLM
+ SEC calls roughly double premarket (acceptable for telemetry; killable via the flag).

**Anticipated effect**: ZERO live grade-VALUE change (shadow writes audit rows only). Offline
two-case: BFLY routine→strong (cites today's news sized by the deal), BTQ ATM-dilution
canary stays routine. Offline 60-name cohort: BFLY-rise + AEHR-restore + CASY gc→strong
(conservative, still fires), 0 inflation — BUT the offline baseline is no-web and can't
measure web×enrichment double-counting, so it is NOT the flip gate.

**FLIP GATE (load-bearing — make enriched the live grade)**: requires Monday+ live shadow
data showing production net-correctness (enriched lifts true catalysts, inflates nothing —
read via `scripts/_344_shadow_verify.py`), re-poll fires once with tolerable latency, then
CHANGE_PROCESS + operator sign-off. Until then the live grade is byte-identical to before.
**⚠️ The flip MUST carry the grade window**: the validated shadow grades the enriched corpus
at `max_chars=_GRADE_ENRICH_MAX_CHARS` (12000); the live path defaults to 6000. The flip has
to pass `max_chars=_GRADE_ENRICH_MAX_CHARS` on the live `_classify_catalyst_claude` call, or
the appended dilution/agreement context truncates and the live grade won't reproduce the
measured shadow (the original truncation bug, re-introduced at flip).

**REVERSION**: set `ENRICH_SHADOW_ENABLED=false` (kills the shadow); the live grade path
is unchanged regardless.

### 2026-06-14 — M&A filter: acquirer-direction on the TITLE path (#284) — AWAITING SIGN-OFF

**Trigger**: 6/14 materiality dig (advisor-prompted, off the Sunday weekly review)
found the M&A pin filter suppresses **acquirer-side** names via TITLE match (Path A).
`_ticker_is_acquirer` only inspects per-ticker REASONING, so when reasoning is
absent/ambiguous an acquirer-side title leaks through. Material case: **ONDS 2026-05-28**
graded `strong` on a real Q1 earnings blowout ($50.1M rev), suppressed by the stale
(5/18) title *"Ondas Bets Big On AI Battlefield Software With Omnisys Buyout"* (Ondas is
the BUYER), then ran **+24%** (open-based, 5 sessions). Also **MYRG** (*"MYR Group …to
Acquire Valley Electric"*, +6.5%) and **CECO** (acquirer of THR — but CECO is a
multi-ticker title *bleed*, out of scope here → Path B). This is the residual the
2026-05-13 fix left: that fix only removed bare `"acquire"/"acquisition"` keywords;
`buyout`/`merger`/`definitive agreement`/`takeover` stayed **direction-blind on titles**.

**Fix**: `title_implies_acquirer(title, filing_company_name)` — anchored on the filing
company's POSITION in the headline (a title is not per-ticker, so "BigCo to Acquire
Acme" filed under target Acme must NOT read as acquirer). Target-guard FIRST. Two acquirer
signals, both requiring the filing co to appear BEFORE them: (1) verb form (acquirer verb
after the co — MYRG); (2) object form (acquirer-noun preceded by a capitalized non-filing
entity, after the co — ONDS "Omnisys Buyout"). Wired into Path A after `_ticker_is_acquirer`;
company name fetched lazily + memoized cross-call; emits `mna_acquirer_title_skipped`
(trading-day-deduped) on activation.

**Safety is NOT uniform (corrected 6/14 after /simplify — the original "never converts a
target" claim was WRONG):** the VERB form IS asymmetric-safe (target-guard first +
verb-must-follow-co). The OBJECT form is a BENIGN-FAILURE heuristic, NOT bulletproof — a
Title-Case headline verb/adjective before the noun ("Acme Mulls Buyout", "Acme Spurns
Sweetened Buyout") can be misread as a bought entity and mis-pass a noun-form target (the
`_GENERIC_ACQ_PRECEDERS` stoplist narrows but cannot close this — no NER/name-map).
Operator-signed KEEP 6/14: the failure is benign (a mis-passed target is price-capped ->
small/quick loss, paper-only) and every pass is surfaced for FP review by the recurring
`mna_filter_accuracy_review` (the monitored backstop). Verb-form-alone would be bulletproof
but would re-defer the material ONDS case.

**Evidence**: real title-fires are **N=3 in 120d** (KALV/MYRG/ONDS) — BELOW the N≥10 ship
bar, so flagged augmented-with-synthetic + shadow-validate (per sample-size discipline).
Labeled backtest **N=14 (6 acquirer / 8 target)** incl. the positional trap and CECO
out-of-scope: **14/14** (`scripts/probes/_284_mna_acquirer_backtest.py`). **16/16** unit tests
(`tests/test_ma_filter_direction.py`, incl. updated `test_title_acquirer_*` reflecting the
new behavior + ONDS/MYRG pass + Acme-target still fires + conservative-without-name).

**Anticipated effect**: acquirer-side title-match fires drop (ONDS/MYRG-class pass to
alert/entry); CECO-class title bleed UNCHANGED (still fires — needs Path B subject-relevance,
deferred under `mna_filter_direction_blindness_path_a`). Net ~1–2 fewer acquirer
suppressions/month (rare). Fail-direction is benign: a mis-passed target is price-capped
(small/quick loss, paper-only pre-6/22), vs the +24% winner the leak was costing.

**Reversion-flag**: REFINEMENT of the 2026-05-13 direction fix (adds title-direction
handling for the keywords that fix left direction-blind). Hard revert = drop the
`title_implies_acquirer` block in `polygon_news_has_mna_headline` Path A.

**Status**: OPERATOR-SIGNED 2026-06-14 (filter list reviewed; object-form KEEP after the
safety correction above). Committed `28c4e59` + `/simplify` cleanup (cross-call name memo,
trading-day audit dedup, precompiled object-form regex, honest docstring). Backtest 14/14,
16 unit tests. NOT yet deployed — deploy AFTER the Monday split go-live (intelligence-side
detection; no reason to add a variable to the 6/15 ORB-via-http window), then field-validate
the live wiring (first `mna_acquirer_title_skipped` rows) + the monthly accuracy review.

### 2026-06-12 — Rubric v3: catalyst FRESHNESS clause (judge + fallback grader)

**Trigger**: AKTS 2026-06-12 — the judge's first WRONG live load-bearing promote
(MODERATE→HIGH, `materiality=transformative`), caught same-day by the OPERATOR:
the "$1.1B Lilly partnership" was announced **2024-05-21** (two years pre-gap;
$60M upfront, $1.1B = milestones). The corpus was web-only
(`sources: {web_perplexity: 1}, has_direct_source: false` — no 8-K/wire existed
that day, which was itself the signal); Perplexity surfaced the old deal undated
as "the clearest catalyst"; the judge flagged the verifiability concerns in its
own rationale and promoted anyway. Neither rubric layer required the catalyst to
be NEW.

**Evidence**: single operator-labeled live case (flagged single-case-tune per
CHANGE_PROCESS rule 2) — but the change is a CORRECTNESS rule (freshness is
definitionally part of "a real catalyst" for an *episodic pivot*), not a
threshold tune; same class as the 2026-05-20 gate-inversion precedent. Catalyst
attribution correctness is the stated goal of the program
(`feedback_catalyst_correctness_is_the_goal`).

**Anticipated effect**: undated/stale catalysts can no longer justify HIGH from
either layer; web-only-sourced materiality promotions get explicit skepticism
(prefer floor tier). Expected effect size: rare (first occurrence in 3 days of
load-bearing operation) — but it is exactly the fail-open-to-floor direction:
worst case is a missed alert, never a bad entry.

**Reversion-flag**: REFINEMENT of the judge rubric (v2→v3) + grade prompt.
Prompt-era versioned: `RUBRIC_VERSION/RUBRIC_HASH` + `CATALYST_GRADE_PROMPT_VERSION`
both bumped to `v3-2026-06-12-catalyst-freshness` — every decision row stamps its
era; instant revert = restore the v2 text (hash flips back).

**Status**: shipped 2026-06-12 (operator-signed in-session). Field validation:
AKTS = named regression probe in the eval probe library; watch the next
`has_direct_source=false` promote candidate's `ep_grade_decision`.

### 2026-06-08 — Holistic Grade Judge supersedes the conviction floor (W2c, ADR 0011) — toggle-gated, SHIPPED DORMANT

**Trigger**: Operator directive (2026-06-08, memory `feedback_build_toward_vision_not_piecemeal` + signed ADR 0011): the conviction floor promotes to HIGH on **gap % + a catalyst enum alone** — materiality, theme, narrative, and structure are decorative. By the operator's framing the materiality-less grade is "definitionally incomplete" for the EP method. The North Star is ONE holistic LLM judge over the full rubric that moves the grade **bidirectionally** (promote an under-rated material-small-cap outlier / demote an immaterial big gap) and becomes the live **paper** grade.

**Evidence**: This is a **methodology-completeness** change, not a threshold tune, so it is NOT gated on backtested R-superiority (forward-from-gap is the saturated metric that killed the #189 materiality R-gate, ADR 0010). The operator SIGNED the 5-point rubric (ADR 0011 §Rubric). Field validation = the W1 shadow cohort (judge_tier vs floor delta) + operator review of the promotion/demotion delta lists + the **Unjustified Demotion Sweep** (`scripts/unjustified_demotion_sweep.py` — every judge `demote` whose ticker then ran ≥+18% MFE/5d) BEFORE the toggle is flipped ON. The agent never self-certifies the demotion list (HARD gate).

**Architecture**: the judge runs in the existing **post-loop** concurrent gather (own `_JUDGE_SEMAPHORE`, 15s `wait_for`). When `holistic_judge_enabled` is ON it OVERWRITES the authoritative `score_tier` (the single field the caller reads for alert+entry, and the downstream ORB job reads from the row) and stamps `grade_engine_authority ∈ {judge,fallback}`; `baseline_floor_tier` is preserved as the counterfactual. Judge `none` → suppression (no alert/entry); judge promote MODERATE→HIGH → flows into the ORB path as a floor-HIGH would. **FAIL-OPEN**: judge error/timeout → floor tier kept, authority `fallback` (counted). **FAIL-CLOSED toggle**: any toggle-read error → floor.

**Anticipated effect**: with the toggle OFF (current, SHIPPED DORMANT) — **zero behavior change**, byte-identical to W1 shadow; the judge writes only advisory columns + `ep_grade_decision` audit traces. With the toggle ON (operator-gated, paper-only) — the paper HIGH set is re-graded: gap-only HIGHs with no material catalyst demote out of entry; material-relative-to-size MODERATEs promote into entry. Net HIGH count change unknown until the live cohort accrues (first judge fire 2026-06-09).

**Known limitation**: the judge scope is the **score≥50 cohort** (MODERATE+HIGH results) — it can demote HIGHs and promote MODERATE→HIGH, but cannot rescue a name the floor scored <50 (those never reach the result dict). Sub-50 small-cap rescue is a future widening (cost/scope tradeoff). The cross-strategy allocator shadow-enqueue + scan_log record the floor tier (in-loop, pre-override) — acceptable (allocator is shadow-only #31).

**Reversion-flag**: NEW. Reversion = `docker exec apollo-market python scripts/set_holistic_judge.py off` (instant, no redeploy — the toggle is the kill switch). Hard reversion = drop the `_judge_authority` override block in `run_ep_scan`.

**Status**: SHIPPED DORMANT 2026-06-08 (toggle OFF, byte-identical). The flip to ON is operator-gated on the delta-list + Unjustified-Demotion-Sweep review (ADR 0011 go-live gate); PAPER-only; 6/22 real-money decision stays decoupled.

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
