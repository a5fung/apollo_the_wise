# MAGNA53 EP — Episodic Pivot

> 📜 **THE PRINCIPLES (P1-P10) + THE GOAL live in `docs/roadmap/ep_profitability_program.md` § THE PRINCIPLES.** Read them before any analysis, card or proposal here — they are the operator's own rules, in precedence order, and they govern this document. Cite by name (P1, P2…). ⚖ THE LINE sits above all of them.


**Phase**: Live (paper). Production-active.
**Origin**: Pradeep Bonde Episodic Pivot methodology + Marios Stamatoudis adaptation.
**Code**: `agents/market_intelligence/ep_detector.py`, scheduler 7:00–10:00 ET cron every 5 min.

## Definition

A liquid stock gaps significantly on a real catalyst (earnings, FDA, M&A, major news), with confirming volume and structural fitness (not extended, not in cooldown). The gap signals new information has changed the stock's fair value; entry on opening-range breakout (ORB) the same morning.

**Stop and sizing (operator-signed 2026-08-16 — see change log):** the protective stop sits at
**`entry − 2R`, where `R = entry − ORB low`** (equivalently `2·ORB_low − ORB_high`). The ORB low
still **defines R**; it is no longer the exit. Position size **halves by the sizing formula itself**
(`shares = risk_dollars / stop_distance` — the distance doubled), so **dollar risk per trade is
unchanged**. 🔴 The +2R partial target does **not** move: 1/3 still comes off at the ORIGINAL
`entry + 2·(entry − ORB_low)` price (`order_manager.profit_target_r_per_share` pins the frame).
Pre-2026-08-16 the stop was the ORB low itself.
✅ **LIVE.** Confirmed in production 2026-08-23 (the line above said "not yet deployed" for a
week after it already was — a stale caveat is a hidden rule, P15). Live behaviour observed from
2026-08-18: AMLX's placed stop equals `2·ORB_low − ORB_high` in prod trade data.

**🛑 THE GAP IS NOT OPTIONAL — operator ruling 2026-09-05, recorded here because it was asked and
will be asked again.** His words: *"if there's just vol, but no gap that is no EP. It's just churning
volume where ever it is. It's not an EP."*

**So a name showing extreme volume with no gap is NOT an EP candidate and must not be seeded into the
EP funnel from any side door.** This closes a question raised while scoping #297: the delayed-entry
lane seeds only from names that became EP alerts, so a high-volume/no-gap name is structurally
invisible to it — and that is CORRECT, not a coverage gap.

⚠ Note where this places every piece of volume work: the gap floor cuts at `ep_detector.py:3189` and
volume is scored at `:3399`, **after** it. Volume ranks and filters names that already gapped; it
never admits one that did not. That ordering is the ruling above, expressed in code.

This is the canonical Apollo entry strategy — the highest-volume, highest-conviction setup type.

## Universe / eligibility

- **Price**: prev_close ≥ $5
- **Liquidity**: pre-market dollar volume sufficient (relative + absolute floor — see PM volume gate)
- **Universe**: ~9,700 stocks via Polygon grouped daily
- **Cooldown**: 60-day cooldown after any prior EP alert, with carve-out for fresh earnings (see below)
- **Extension**: skip if prev_close is ≥ 50% above the MIN(close) of the last ~5 trading days (already extended pre-gap → chase risk). `MAX_EXTENSION_PCT=50.0` (ep_detector.py:234 — raised to 75.0 on 2026-08-22, **REVERTED to 50.0 on 2026-08-29** when the evidence for the raise was found to rest on a corrupt table, #595); MIN, not a single 5-days-ago point. [Corrected 2026-07-18 — was mis-transcribed at doc creation as "≤ 1.50× SMA-10", a rule that has never existed in code (see #481 + change log); the live criterion is unchanged.]

## Detection criteria (current)

EP detection runs every 5 min from 7:00 AM to 10:00 AM ET. Each scan tick evaluates candidates against:

### Filters (any failure → skip)

**Pre-grade** (candidate scan, before catalyst classification runs):
1. **Gap floor**: `gap_pct ≥ MIN_GAP_PCT` (9.0% hard floor, env `EP_MIN_GAP_PCT`; was 10.0% — see 2026-08-19 change log entry) — applied building the candidate list itself (ep_detector.py ~1567). No regime-dependent variant exists in code — ADR 0003's Phase-1 recommendation of "10% (or 12% in elevated regimes)" only ever shipped as a flat number; that regime branch was never built.
2. **Pre-market volume**: relative gate — `pm_rvol ≥ MIN_PM_RVOL` (1.0× session-anchored RVOL@T)
3. **EP cooldown**: skip if alerted within last 60 days, UNLESS `gap_pct ≥ 15% AND is_earnings_day` (fresh earnings catalyst bypasses cooldown)
4. **Extension cap**: `(prev_close − min5) / min5 ≥ 50%` → skip, where `min5 = MIN(close)` over the last ~5 trading days (`MAX_EXTENSION_PCT=50.0`, ep_detector.py:234; raised to 75.0 on 2026-08-22 and **REVERTED to 50.0 on 2026-08-29** — the raise rested on corrupt evidence, #595). [Corrected 2026-07-18 — was "> 1.50× SMA-10", never in code; see #481.]
5. **Already scored today**: dedup within scan day
6. **Session RVOL@T** (post-9:30): same primitive as pre-market, but session-anchored. Threshold `MIN_SESSION_RVOL = 1.0`

**Post-grade** (`_post_grade_filters`, ep_detector.py ~1260 — run AFTER catalyst
classification so they can condition on the catalyst grade; moved here #405,
2026-07-03, "so we can use catalyst_quality in the carve-out condition").
⚖ **Since 2026-08-22 these filters read the ACTING grade** — the lattice-corrected tier,
the same one the score reads (one grade everywhere; `catalyst_tier_lattice` toggle OFF =
raw LLM grade everywhere, byte-identical pre-flip). Plain words: **a filter and the score
never disagree about what the same news is worth.**
7. **M&A filter** (`ma_filter.is_likely_ma`): catalyst='mna' OR keyword scan OR Polygon news headlines — skip. (Grade-invariant under the lattice: `mna` is passthrough-only, so acting == raw here by construction.)
8. **Routine + low gap** — plain words: *a routine-news name gapping under 12% is skipped, where "routine" is the CORRECTED grade.* Code: acting `catalyst_quality == "routine" AND gap_pct < 12%` → skip. A real EP the LLM mis-grades routine (4 of the 7 graded labelled real EPs — ARM class) is no longer binned before the correction can act; the lattice never demotes a non-routine grade to routine, so this filter can only admit MORE than the raw read, never less.
9. **Pre-market shares absolute floor** (with carve-out) — plain words: *under 25,000 pre-market shares is skipped, unless volume is exploding (5× pm RVOL) or the gap is 10%+ with a strong-or-better catalyst.* Code: `today_volume ≥ MIN_PREMARKET_SHARES` (25,000) UNLESS `pm_rvol ≥ 5×` OR (R6 carve-out) `gap_pct ≥ 10% AND` acting grade in {`strong`, `game_changer`}. The `game_changer` arm exists on the acting side only (2026-08-22): a lattice PROMOTION must never strip a name of the bypass its old grade earned; with the toggle OFF the historical strong-only carve-out applies exactly.

### Grading shortlist — who gets graded at all (pre-score ranked since 2026-08-22)

Each tick, only the top `SHORTLIST_SIZE` (20) by the shortlist pre-score are graded (the
LLM/FMP call budget); every candidate past the cap is logged
(`outside top-20 shortlist (prescore rank N, gap X%)`) but never graded. **Sort key since
2026-08-22 (operator-directed): the three-term pre-score `ep_rubric.SHORTLIST_WEIGHTS`, NOT
gap size** — gap size runs backwards on real EPs (AUC 0.34) and was deleted from the score the
same day; the operator caught it still deciding who gets looked at ("how are we still using it
after all this work").

- **Pre-score** (0–65, free inputs only, computed for EVERY candidate at the sort):
  `liquidity` (max 15, **weight 3** — 20-day ADV$ tiers 15/12/10/7 at $500M/$250M/$100M/$50M;
  45 of 65 by construction, AUC 0.72) + `gap` (max 10, weight 1 — **FLAT**: any qualifying gap
  earns full points; presence, not magnitude) + `theme_bonus` (max 10, weight 1 — in an
  Accelerating/Mainstream theme). Missing-input rescaling per
  `catalyst_rubric.composite_with_scaling`'s shape: unknown ADV (`adv_source='pending'`) ⇒ the
  liquidity axis is missing and the composite rescales from gap + theme — a data gap never
  silently sinks a candidate (P1). Deliberately NOT scored: `extension` / `prior_3m` /
  `adv_trend` / `cooldown_proximity` (unmeasured or measured-noise — see change log) and
  everything that costs money per name (float, mcap, pm_rvol, catalyst).
- **Tie-break** (required — Stage 0 measured a 9-way tie at the rank-20 cut on the 04-08 flood
  board): composite desc → **continuous ADV$ desc** (the same measured axis at full
  resolution, tick-stable, never gap) → ticker asc (total-order determinism).
  `ep_rubric.shortlist_sort_key`.
- **Revert flag**: `ep_shortlist_prescore` runtime toggle / `EP_SHORTLIST_PRESCORE_ENABLED`
  env, default ON — OFF restores gap-descending ordering **exactly** (~60s, no redeploy;
  pinned by `tests/test_ep_shortlist_prescore.py`).
- **Counterfactual record**: `mi_ep_shortlist_shadow` — every candidate, every tick: raw
  inputs only (never computed points — the #583 stale-derived-value class), both ranks, both
  would-be-shortlisted flags, and `acting_key` stamping which ordering acted.
- The next ranks up to `ADV_BACKFILL_LIMIT` (50) get ADV backfilled for telemetry only
  (unchanged behaviour, constant named the same day).

### Catalyst grading (Claude + Perplexity + SEC EDGAR)

LLM classifier returns one of: `game_changer`, `strong`, `routine`, `mna`, or None.

**⚖ Catalyst-tier LATTICE — LIVE since 2026-08-22 (operator-signed; see change log).** The raw
LLM grade is no longer the acting tier: after every raw-grade mutation (earnings boost, #72
prose downgrade) and before `_score_ep`, the deterministic surprise-anchored lattice
(`catalyst_tier_shadow.shadow_retier`, $0 — no LLM call) moves the grade at most ONE step on
mechanical evidence (#568 expectedness axes, rule-4 demotion markers + concrete-event regex,
sector follow-through):
- `game_changer` KEPT only with content-surprise evidence — scheduled: beat AND
  forward-changing content (the PEG signature); unscheduled: a concrete forward event;
  unknown calendar: kept (fail-open). Else demoted one step to `strong` (floors intact — a
  10-point haircut, not a skip).
- `strong` → `game_changer` only on unscheduled + forward + sector-confirm (the MRNA class:
  own concrete unscheduled forward event AND the group repriced with it). Never demoted.
- `routine` → `strong` when the live analysis carries rule-4 sector/sympathy markers AND a
  concrete company event (the prompt's auto-demotion reversed). Never straight to the top.
- `mna` passthrough — the M&A hard filter is untouched.
Recomputed every scan tick (the MRNA 07:05 grade-pinning fix). **⚖ ONE GRADE EVERYWHERE
(2026-08-22 consistency fix, same day, operator-directed — REVERSES the flip-day scope
line):** `_post_grade_filters` (M&A / routine-gap<12 / R6 pm-shares carve-out), the earnings
boost, the revenue gate, the #72 prose downgrade, the score, the tier — EVERY consumer reads
the acting (lattice-resolved) grade, resolved at grade-settle and re-resolved after each
raw-grade mutation (`ep_detector._resolve_acting_catalyst_quality`). The raw LLM grade
survives only as the lattice's input, the cache contents, and the record's `live_quality`
column (pinned by `tests/test_lattice_admission_consistency.py`). **ONE revert flag:**
`catalyst_tier_lattice` runtime toggle /
`CATALYST_TIER_LATTICE_ENABLED` env, default ON — OFF restores the raw-grade behaviour with no
other edit (exact revert SQL in the change log). Both sides + a `live_side` acting-marker are
recorded per (scan_date, ticker) in `mi_catalyst_tier_shadow`; the nightly flip monitor
(`health_checks.run_catalyst_lattice_monitor`) owns the three revert triggers.

**WHAT THE GRADER SAW AND WHY, PERSISTED (#593, 2026-08-24 — capture + display only; NO
grading rule, prompt, threshold or score changed).** The grader returns `analysis` — its own
"2-3 sentences on the specific catalyst and classification rationale" — and reasons over a news
corpus; `ep_detector._tier_shadow_base` already handed BOTH to the tier recorder, which bound
neither: it stored `grounded_len`, a LENGTH. So for every graded name that did NOT alert, the
reasoning was computed and thrown away. An ALERTING name kept it in `mi_ep_alerts.claude_analysis`;
a name that died under the score bar or on a post-grade filter has no `mi_ep_alerts` row at all,
which is why "what did the system see and why did it decide that" was unanswerable for exactly
the cohort the operator asks about (NSSC 2026-08-24: graded `strong` on a scheduled earnings
release with an 11% revenue increase, no record of whether "beat + guidance raise" or just "beat"
was being applied). Three nullable columns now persist it at the SAME single write site:
`claude_analysis`, `news_summary`, and `grounded_head` — a BOUNDED prefix of the corpus at the
LEAN grader's own window (`_classify_catalyst_claude`'s default `max_chars=6000`), defensible
because `build_grounded_text` is ordered primary-first (SEC filing → Benzinga wires → web
summary), so the prefix keeps the direct sources and drops the web/context tail. ⚠ It is NOT
always the whole graded text: the #344 ENRICHED-corpus path grades with
`_GRADE_ENRICH_MAX_CHARS` (12000), so an enriched grade can have read past the stored prefix.
`grounded_len` still records the FULL length, so that truncation is always detectable rather
than silent. Rows stay one per
(scan_date, ticker), so this is ~20-40 names/day, not per tick. Surfaced by **`/why TICKER
[DATE]`** (and therefore `/setup TICKER DATE`) as a CATALYST GRADE section — grade, which
grader acted, the rationale verbatim, the news sources read, the expectedness read, plus an
explicit agree/disagree line against the deterministic methodology rubric. `/why` with no date
now also resolves to the last day the name was GRADED, since a graded-not-alerted name appears
in no alert/trade/audit row. Read by NO grading / entry / sizing / safeguard path; pinned by
`tests/test_catalyst_tier_shadow.py::test_catalyst_grade_record_reader_is_display_only`.

**Grounded grade (2026-06-04, #187/#190 — catalyst-axis Track A+B; deployed live).** The grade now reasons on a GROUNDED, UNTRUNCATED summary — the authoritative **SEC 8-K body** (`collector.get_sec_recent_filings`, near-real-time `data.sec.gov/submissions` endpoint, error-wrapped) + the Perplexity web synthesis — NOT raw 200-char yfinance headlines. Model upgraded **Haiku → `claude-sonnet-4-6`**. New prompt rule: broad sector-momentum / short-squeeze / non-company-specific technical moves grade `routine` (a gap-up alone is not a catalyst).
- **WHY**: RUM 2026-06-04 traded −1.07R as a false `strong` — the real catalyst (a $270M NVIDIA-Blackwell GPU-cloud **8-K filed 5:04am ET**) reached neither LLM (no EDGAR ingestion existed), so Haiku confabulated `strong` from headlines while the grade truncated the synthesis to 200 chars.
- **EVIDENCE**: 30-case bake-off — grounded summary flips the false-`strong` junk (RUM/PGY/CRSR/DY, short-squeeze/sector-rotation/ticker-mismatch) → `routine`, and Haiku≈Sonnet≈Opus on identical input (so the **input** is the lever, not the model); RUM grounded+8-K → `strong` with the correct $270M rationale; B0 confirmed EDGAR is near-real-time and the 8-K was retrievable ~4.5h pre-scan.
- **SHIP not shadow** (move-fast): fails CONSERVATIVE — the SEC fetch + grade are error-wrapped (→ `routine`), so the worst failure mode is a missed alert, not a bad trade. Watched on the next 7–10am ET scan.
- **REVERSION**: drop the `grounded_text` path + the `claude-sonnet-4-6` model in `_classify_catalyst_claude`, and the `get_sec_recent_filings` gather entry → restores the headline-Haiku grade. Plan: `~/.claude/plans/i-want-to-plan-groovy-horizon.md`.

**Materiality (#189, 2026-06-04 — built + offline-validated; deploys AFTER the grounded-grade scan confirms).** The grade prompt now includes the company **market cap** + a rule: a contract/deal/order is `strong`/`game_changer` ONLY if its value is SIGNIFICANT vs the company's size (a meaningful fraction of market cap / revenue) — "news existence ≠ EP-grade." EVIDENCE: the same RUM $270M 8-K grades `strong` at RUM's ~$2.5B cap but `routine` at a synthetic $600B mega-cap (validated on Sonnet). REVERSION: drop the `Market cap:` prompt line + rule 5 + the `mktcap_str` computation. Change-isolation: deployed one scan-cycle after the grounded-grade re-arch so the two grade changes are verified separately.

**Earnings-day pre-score boost**: when `is_earnings_day(ticker, today)` returns True (within {yesterday, today}) AND `is_revenue_stage(ticker)` returns True (yfinance Revenue Average > 0), upgrade catalyst from `routine` or None → `strong` BEFORE score computation. Audit event: `catalyst_earnings_boost`. This handles cases where the news scrape is hedged/hollow but yfinance confirms earnings (DDOG/AAON 5/07 class). **Pre-revenue companies** (clinical-stage biotech, SPAC, blank-check — Revenue Average == 0): boost is SKIPPED with `catalyst_earnings_boost_skipped` audit event. Their "earnings" event is pipeline / trial commentary, not a Q-rev catalyst — applying the boost causes the rubric to engage and produce misleading "Q-rev YoY un-extractable" downgrades. The Q-rev rubric gate ALSO skips for pre-revenue companies (belt-and-suspenders) so Claude's organic catalyst grade stands. Trigger: IMVT 2026-05-20.

**Hedge-phrase downgrade**: if Perplexity answer contains hedge phrases ("no specific information", "couldn't find", etc.) AND catalyst is `game_changer`/`strong`, downgrade one notch. Audit event: `catalyst_pplx_hedge_downgrade`.

### Score computation (`_score_ep`)

`catalyst_quality` entering `_score_ep` (component AND conviction floors) is the LATTICE
tier since 2026-08-22 (see Catalyst grading above), not the raw LLM grade.

Multi-factor, table-driven (`ep_rubric.SCORE_WEIGHTS`; the `ep_score_separation` runtime flag
picks the acting table — see the 2026-08-22 SEPARATION change-log entry). Components:
- **Gap: FLAT +10 for every qualifying gap ≥8%** (#533 separation change, 2026-08-22,
  operator-signed). Gap SIZE is no longer paid — the old 25/20/15/10-by-size ladder ran
  BACKWARDS on real EPs (AUC 0.34; real EPs' median gap 9.9% vs ordinary gappers' 12%+). The
  8% qualifying cut is unchanged: WHAT qualifies did not move, what a bigger gap PAYS did.
- Catalyst — ADDITIVE component (not a multiplier): `game_changer` +25 / `strong` +15 /
  `routine` (or anything else) +0.
- Liquidity (20-day ADV$ tiers 15/12/10/7), float bonus (+5 under 50M), vol_conviction (5/3),
  theme_bonus (+10) — unchanged by the separation change, shared by both flag sides.
- (`prior_momentum` and `neglect` were DELETED 2026-08-22 — see that change-log entry. Doc-sync
  note: this paragraph previously still described the prior-momentum penalty.)

**Conviction floor — SINGLE branch since 2026-08-22**: gap ≥10% + `game_changer` → floor 60
(the 2026-04-14 dead-zone fix FOR a real EP (BE); it is what fires MRNA HIGH at its 10% read —
kept BY DESIGN, pinned by `tests/test_533_separation_flip.py`). Branches 1-3 (15%+gc→80,
20%+strong→80, 15%+strong→70) DELETED — the back door that kept paying gap size after the
ladder flattened. Flag OFF restores all four (`SCORE_WEIGHTS_LEGACY`).

`_score_ep`'s full `breakdown` component list (current, 2026-07-18): `gap` (magnitude), `liquidity` (20-day ADV$ tiers — REPLACED `rel_volume` 2026-08-22, operator-signed; see change log), `catalyst` (quality tier), `float` (low-float bonus), `vol_conviction` (pre-market volume percentile), `theme_bonus` (R4 in-theme, 2026-05-17), `conviction_floor` (gap+quality floor overrides). **`analyst` (analyst-upgrades bonus) REMOVED 2026-07-18** — see change log below; it is no longer a scored factor.

**Score scale (#533 RESCALE, 2026-08-22 — presentation only, alerting set proven identical):**
while the `ep_score_separation` flag is ON, `_score_ep` presents its final score through ONE
strictly-increasing transform — `presented = 1.25 × raw + 15` (`ep_rubric.apply_output_scale`,
`SCORE_WEIGHTS["output_scale"]`), applied LAST, after the conviction floor and the regime
multiplier. The bar is expressed through the same function (65 = raw 40), so `score ≥ bar` is
decided identically on either scale — no name, day, or tier can flip (proof:
`tests/test_533_rescale_invariant.py`, three cohorts + an exhaustive boundary sweep). On the
measured #533 corpus the presented scale reads: real EPs at their known grades ≈ 67-105 (the
four alerting members: 67.5 / 67.5 / 90 / 105; MRNA 105 Bull / 90 non-Bull), routine-graded
ordinary gappers ≈ 30-52 (median 40.5), scale floor (a qualifying gap and nothing else) 27.5.
Score `breakdown` stays RAW components (the component diagnosis; it already excluded the
regime multiplier). Flag OFF → no transform: the legacy side presents the old raw scale
byte-identically.

Score thresholds (the HIGH decision outranks any cutline — a bar-clearing score never dies on
one; with the legacy bars 65-80 that is byte-identical to the old order):
- **Flag ON (separation, default): `≥ 65` presented → HIGH** (immediate Telegram + ORB
  submission window), **below 65 → skip.** The bar is `ep_rubric.SEPARATION_BAR` (65 = raw
  `SEPARATION_BAR_RAW` 40 through the transform — raw-40 remains the volume-neutral
  operator-signed policy; the raw 45/50 fewer-alert rows present as 71.25/77.5).
  `ep_rubric.resolve_moderate_cutline` still returns **None** on this side — **there is no
  MODERATE *tier*.** A score in `[50, 65)` never gets `score_tier="MODERATE"`, never reaches
  the earnings-day MODERATE→HIGH override, never reaches the cross-strategy allocator enqueue,
  and never reaches the entry pipeline — that decision is untouched by the change below.
  **#533 follow-on (2026-08-22, operator-directed — visibility only, not a criteria change):**
  a `[50, 65)` **near-miss band is now RECORDED in the morning briefing** ("EP ALERTS" section,
  `👀 Near-miss (50-65, recorded only — not tradeable)`), operator's own words: *"we don't need
  separate alerts but we have a section for close but misses, or moderates, can we put them
  there? I want them recorded in case we miss real EPs there."* This is a pure READ of the
  `mi_ep_scan_log` skip rows the scorer already writes (`score_tier` stays NULL on them) — no
  new storage, no new Telegram surface, no scoring/tiering change. See
  `agents/market_intelligence/briefing.py::_format_ep_section` (`near_miss_band`),
  `tests/test_ep_near_miss_band.py` (the promotion-proof: a near-miss score with a
  gap≥10%/earnings-day shape structurally cannot reach `tier == "MODERATE"`, so the
  earnings-override guard is unreachable for it). Re-arming the actual MODERATE **tier**
  (i.e. making these names entry/allocator-eligible, which WOULD also re-arm the earnings
  override) remains a criteria change and stays operator-only — nothing here does that.
  Measured volume: attempted, inconclusive rather than a correction — see the change-log
  entry below for the full readout, including a harness-faithfulness check that failed
  (median −6 pts vs stored historical scores) and why that keeps the ~2.3/day figure standing
  as "order 1–3/day, not shown wrong" rather than replaced by a lower number.
- **Flag OFF (revert): unchanged** — `< 50` → skip; `50 ≤ score < ep_threshold` → MODERATE
  (briefing only); `≥ ep_threshold` → HIGH at the per-regime bar from the stored regime row
  (`regime.py`: Bull=65, Choppy=70, Correcting=75, Crisis=80), all on the old raw scale.
- ⚠ Known seam (unchanged from the separation entry): surfaces that DISPLAY the stored regime
  row's `ep_threshold` (briefing regime line, agent.py why-no-alert prose, the allocator's
  advisory `legacy_eligible` label) still show the per-regime raw number — under Bull it now
  coincidentally reads 65 like the presented bar, but they are different scales. `regime.py`
  and stored rows deliberately untouched so the revert side survives intact; the alerting
  decision uses the flag-gated bar.

**Holistic Grade Judge overwrite**: when `holistic_judge_enabled` is ON (toggle,
ADR 0011/W2c — SHIPPED DORMANT, see 2026-06-08 change-log entry below), the
judge OVERWRITES the authoritative `score_tier` computed above — the field the
caller/ORB job actually reads. `baseline_floor_tier` is preserved as the
counterfactual and `grade_engine_authority` stamps which engine (`judge` vs
`fallback`) decided. Toggle OFF (current default) → floor score_tier stands,
byte-identical to the thresholds above.

### Earnings-day MODERATE → HIGH override (legacy override, kept)

If `tier == MODERATE` AND `gap_pct ≥ 10%` AND `is_earnings_day` → promote to HIGH. Audit event: `earnings_override_applied`. This complements the pre-score boost — boost handles `routine` not reaching 50; override handles `strong` reaching 50-65 in non-Bull regimes.

**Override-respects-downgrade rule (2026-05-27, #132).** If the same-ET-day `catalyst_earnings_revenue_weak_downgrade` event was logged for this ticker — the revenue-growth gate actively classified the earnings as low-quality (e.g. `q_rev_yoy_missing_no_prior_year_comparable`) — the override does NOT fire. Tier stays MODERATE. Audit event: `earnings_override_skipped_post_downgrade`. Origin: BBWI 2026-05-27 fired HIGH at 9:51 ET despite an explicit data-quality downgrade at 7:20 ET. The override is designed for the "news ingest lag" case where catalyst stayed `routine` because no headlines yet; an explicit data-quality downgrade is the opposite signal and must be respected. Fail-open on DB error (preserves news-ingest-lag tolerance).

### Submission window

HIGH alerts trigger ORB submission only when `now_et.hour == 9 AND now_et.minute < 45` — combined with the market-open gate (`now_et.hour > 9 OR (now_et.hour == 9 AND now_et.minute >= 31)`), the effective window is **9:31–9:44** ET (`scheduler.py` ~891-897), not the full 9:00 hour. HIGHs at 9:45–9:59 → `WINDOW_OUT_OF_ORB`. 10:00 ET cleanup cancels any unfilled `order_placed`.

### Within-day slot ranking — which HIGH alerts get the five slots (2026-08-30, operator-signed)

On a multi-alert morning `live_tracker.process_new_alerts_live` processes the board in a
DELIBERATE order that is the slot priority under the 5-position cap: **prior-day
`rs_composite` DESC, `ep_score` DESC tiebreak, ticker ASC** (`ep_slot_rank_shadow.
slot_rank_key`). Pre-#533 the order was ALPHABETICAL by accident — `DISTINCT ON (ticker)`
forces the SQL sort to start with ticker, so `ep_score DESC` only broke ties within one
ticker. Mechanics + policy:

- **RS source**: `mi_stock_scores` at the latest **COMPLETE** score date strictly before
  the alert day (`db.latest_complete_score_date`, the #554 guard — a stray one-row
  Saturday run can never rank the board). No complete date at all → the legacy order
  acts, loudly.
- **Missing RS row** (universe drift; 0 of 141 in the evidence window): the name is
  ranked AFTER every RS-scored name — no evidence of strength buys no priority — but is
  **never dropped**; it competes for whatever slots remain, ordered by ep_score among its
  peers. Logged as a warning naming the tickers.
- **Revert**: runtime toggle `ep_slot_rank_rs` / env `EP_SLOT_RANK_RS_ENABLED`, default
  ON. OFF → the legacy query's own order acts, byte-identical (the SELECT never changed —
  the re-sort is Python and simply never runs; pinned by `tests/test_533_slot_ranking.py`).
  Revert SQL on `ep_slot_rank_shadow.py`'s docstring. **Fail direction on any ranking
  error: the legacy order acts, loudly (`slot_rank_fallback` audit row) — never a dead
  selection.**
- **Priority, not a serial guarantee**: alerts process under a 5-way semaphore, so the
  ranking sets who STARTS first (and therefore who reaches the insert-time cap recount
  first in the typical case); a top pick stalled on its bar fetch does not block lower
  picks — deliberate, one stall must not eat the 09:45 window.
- **The watch (the ruling's other half)**: every invocation records what EACH of six
  rankings (RS / ep_score / briefing composite / ADV$ / alphabetical-the-control /
  volume percentile — the sixth added 2026-09-04, #624, records only, no change to
  admission/scoring; SCHEMA PENDING a `mi_ep_slot_rank_shadow` column addition in
  db.py — see `ep_slot_rank_shadow.py`'s docstring) would have picked — raw inputs +
  ranks + `acting_key` into `mi_ep_slot_rank_shadow`, on BOTH toggle sides, SILENT.
  Outcomes join at read time from `mi_daily_closes`. Review `ep_slot_ranking_watch_533`
  (data_gated_reviews.yaml) fires at 10 settled multi-alert mornings with explicit
  revert/switch bands.

## Low-cap lane — SHADOW ONLY (#624, operator-approved 2026-09-04)

A **LANE of MAGNA53, not a setup** (operator ruling, all four fixed: shadow now with exit work
in parallel · its own slot allocation · a lane, not a new setup — no new `docs/setups/` file,
no SSoT-router row · sizing 1.0). Buy point, stop, target and harvest are MAGNA53's, unchanged:
stop-limit buy at the first 1-minute bar's high 09:31–09:44 ET, stop at `entry − 2R`, +2R partial
pinned to the ORB R, breakeven, SMA trail. Only the universe differs.

**The recording rule, one sentence (P15):** *A $5+ stock under $500M market cap that gaps 15% or
more and whose volume by the 09:31 tick already ranks in the top 10% of its own trailing history
is a lane candidate; every other MAGNA53 gate it failed is stamped on its row.*

- **Terms, and where each reads:** cap `< MIN_MARKET_CAP` ($500M, `backtester/filters.py` — the
  floor the live filter enforces, imported never restated) · gap `≥ 15%` (`c["gap_pct"]`, the
  acting gap at the tick) · volume percentile `≥ 90` = `_volume_percentile(today_volume,
  history)` where history is the rolling-20-trading-day-mean series from `mi_daily_closes`
  (`db.get_volume_history_daily_closes`, the same map the scan already fetches for every
  candidate) · price `≥ MIN_PREV_CLOSE` ($5, the universe floor). **"Record volume" (the
  operator's phrase) is NOT the trigger** — it is an end-of-day fact (CHPT itself had traded
  969k at 09:31 against a 3.9M prior 400-day max); the rolling percentile is what is computable
  when the decision is made. The three lane thresholds are STAMPED on every row (`lane_*`).
- **Evaluated at POST-OPEN ticks only, over the FULL candidate list before the shortlist cut**
  (`ep_detector.run_ep_scan`, the `#624` block): the graded loop sees only the top-20, the
  liquidity-led pre-score sorts small caps LAST, and the $500M floor kills the rest — so every
  one of the 46 evidence rows had reached the top-20, and the lane's real population has never
  been seen by any study. The FIRST qualifying tick is the record; its wall-clock is what the
  walker submits from (never a fixed 09:31 — #622: the sign flips at 09:36).
- **Acting volume reading = the DELAYED snapshot** (`acting_volume_source='delayed'`) — what
  nearly all 46 evidence rows used; the real-time Alpaca cumulative is stored ALONGSIDE
  (`today_volume_rt`). Switching which one acts is a later, separate fork.
- **What the row carries:** `market_cap` (yfinance profile via a lane-local cache — never
  `filters._mcap_cache`, see below), `extension_pct`, `quality_adv_dollar`, `atr_pct`,
  `blocking_filters` (extended / cooldown / adv / atr / shortlist_cap / mna / pm_shares_floor —
  each with its compared value and threshold; the RVOL@T gate and the score bar need the
  graded path and are NOT reconstructed), **`quoted_spread_bps`, `bid_size`, `ask_size`** at the
  tick (the operator's fillability requirement — the one thing four studies never measured),
  `ma_flag` (`ma_filter.is_likely_ma`, keyword + Polygon headlines, no LLM — the score-free
  lane's only catalyst check), `days_since_prior_lane_signal`, `admission_era`, `regime`.
- **Nightly walker** `lowcap_lane_replay.py` (18:15 ET): fetches + persists day-0 minutes for
  never-alerted names, reconstructs the entry from the row's own tick (`submit_time_and_window`
  — a tick at/after 09:45 is `window_out_of_orb`, never simulated), walks the SAME live ladder
  under `rule_eras.exit_rules_as_of(today)`, and records `stop_pct_of_entry` (the two-cent-stop
  class), **`next_open_gap_pct` + `offering_flag`** (SEC 8-K Item 3.02 / 424B inside the hold —
  the UNCY −9.97R overnight-collapse class n=46 cannot see), `meets_3r` (tail events).
- **The evidence, honestly** (`_623_master.jsonl`, clean settled, cap<$500M): the rule cell is
  n=46 at +0.527R — but **two trades** (WETO +12.08R, FBRX +10.71R) are +22.8R of +24.2R (94%);
  ex-both n=44 **+0.03R**; both thresholds sit just under those two trades' own coordinates
  (gap ≥15 is the highest cut keeping WETO at 18.2%, vol ≥90 the highest keeping FBRX at 91.8);
  across a 7×5 grid the ex-top-2 mean never exceeds +0.10R. That is the shape of a tail strategy
  (4/46 ≥3R = 8.7% vs 13% in the healthy reference year), and n=46 cannot pin the tail rate to
  better than 5×. **Resolving it is the shadow's only job.** Only nine of the 46 rows are on the
  current selection stack; 29 unique tickers in 46 rows (WETO/JLHL/DFNS/ADVB serial at
  100–1,000% extension — the shape of a pump); CHPT ($134M) sits in the $100–200M band that
  averages −0.23R and its own replayed outcome is +0.33R — **the lane rescues CHPT's admission,
  not CHPT's P&L.**
- **Registry + gate:** `mi_strategies.magna53_lowcap` (`phase='shadow'`, `min_median_r: null` on
  both rungs — `_eval_unpaired_r` gates on the median, and with 37% of outcomes at +0.33 and 35%
  at −1.00 a 0.0 bar would pass a losing lane while 0.5 would block a winning tail lane). The
  real gate is `lowcap_lane_graduation_624` (`data_gated_reviews.yaml`): tail events, ex-top-2
  mean, ticker concentration, fillability, and the **#545 ENTRY/EXIT TACTICS PROGRAM** exit
  precondition (37% of the lane's outcomes ARE the +2R-partial scratch — an exit change
  re-prices the lane; every row is re-walked under the new era, $0, before it counts).
- ⛔ **Do NOT waive the extension guard, or propose it.** 19 of the 46 were blocked by it;
  waiving it reverses the 2026-08-29 signed revert and the group ex-WETO is −0.014R. Only 7 of 46
  were rejected by the cap floor ALONE — the paper flip needs a waiver set that is the
  operator's pick, one CHANGE_PROCESS entry per waiver with N≥10.
- 🛑 **THE LINE:** the lane RECORDS. It never submits, scores, alerts or touches slot
  allocation; the tick hook snapshots the board and detaches a task (never on the ORB critical
  path), sets no key on any candidate, adds no `continue`; MAGNA53's alert set, scan-log rows
  and tiers are byte-identical with the hook on / off / raising (`tests/test_624_lowcap_lane.py`
  runs `run_ep_scan` end to end — the first test in the repo to do so). The lane reads the cap
  through its OWN cache because `filters._check_market_cap` pins `None`=pass on any yfinance
  error, and a lane read for an out-of-shortlist name must never let it clear the $500M gate
  without a retry if it later enters the top-20. `should_run('magna53_lowcap')` is the switch.
  **No `rule_eras.ADMISSION_SWITCHES` row at shadow** — the lane changes nothing about who
  MAGNA53 admits (a row would split the #482 era segmentation for nothing); the row lands with
  the paper flip. Supersedes nothing yet: the `ep_tinycap_observed` briefing surface (2026-06-11)
  keeps its population until the operator chooses the lane's narrower one.

## Known limitations / open questions

1. ~~`is_earnings_day` fail-soft direction inconsistent~~ — **resolved 2026-05-08 (session 2)**. All four call sites (parabolic, EP boost, EP cooldown bypass, EP MODERATE→HIGH override) now treat yfinance error as `True` (earnings day). Defensive at each site: rather over-boost / over-bypass / over-promote on data outage than miss a real earnings EP.

2. **Earnings-boosted `strong` lacks agreement multiplier**: a fresh classifier-found `strong` gets 1.2× confidence multiplier from Claude+Perplexity agreement. An earnings-boosted `strong` (upgraded from `routine`) has multiplier=1.0 because the agreement step ran with the original `routine`. Boosted strong is structurally weaker than classifier-strong. Probably fine but worth knowing.

3. **FMP earnings-window pre-check** (Track B Layer 3, task #18): when an earnings-day match is known ahead of time, bias the Perplexity prompt toward earnings as the catalyst. Currently the prompt is generic and may surface analyst-rating blurbs instead of the actual earnings beat. Filed pending FMP earnings-calendar coverage research (S&P-500 limit on current tier).

4. **Stop-limit gap-through on fast movers** (FLEX 5/06 class): 0.5% buffer can't span 4%-in-60-seconds moves. Telemetry filed (task #22) before considering wider buffer or stop-market.

5. **`vol_conviction` is a hardcoded neutral post-open (0 points) for every candidate, and one adjacent comment in `ep_detector.py` was wrong** (found 2026-09-04, CHPT 2026-09-03 — traded 42,975,618 shares vs a prior 400-day max of 3,913,348, an 11x all-time-high day, and scored the SAME 0 points as a dead stock). `vol_percentile` genuinely can't compare a partial-day cumulative to a full-day ADV distribution fairly pre-9:45, so the code returns 50.0 (default tier bucket = 0 pts) rather than publish a wrong number — that half of the design is fine. The comment claiming "post-open conviction is captured via `projected_vol_multiple` (rel_volume slot)" is **false**: `projected_vol_multiple` only feeds the LIQUIDITY component's fallback tier, which fires ONLY when `adv_dollar is None` (new/thin-history listings). Any candidate with a known ADV — the normal case, and true of CHPT (adv_dollar known, `projected_vol_multiple`=392.1x, liquidity scored 0 from the ADV$ tiers, never touched by proj_vol) — never reads `projected_vol_multiple` anywhere else. Two more gaps found building the fix: (a) the live percentile mechanism (`get_volume_history`/`mi_stock_scores.adv_20`) only covers the top ~2,400 RS-ranked names — CHPT had zero rows there — so even a naive "stop hardcoding 50" fix would still return 50 for most off-universe EP candidates; (b) `mi_intraday_bars` (the obvious source for a true same-time-of-day-vs-prior-sessions comparison) is populated ONLY for ticker-days that alerted or traded, not broadly, so a first-time candidate has no per-ticker intraday history to rank against there either — building the same-time-T design on it would silently return "no history → neutral" for almost everyone, the identical defect in a new shape.
   **What shipped (2026-09-04, SHADOW ONLY, telemetry — no live scoring value, weight, threshold or admission rule changed; CHANGE_PROCESS "when not to log" applies, no formal change-log entry below):** `db.get_volume_history_daily_closes()` builds the same rolling-20-trading-day-mean history `_volume_percentile` expects, sourced from `mi_daily_closes` (always populated, not gated by RS-universe rank) instead of `mi_stock_scores.adv_20`. `ep_detector.py` computes `c["vol_percentile_shadow"]` from TODAY's actual cumulative volume (no lookahead — the same number the pre-open branch already trusts) against that history, at every post-open tick, and logs one `vol_conviction_shadow` audit event per ticker/day recording the live score, the shadow score, and whether the shadow WOULD have crossed the alert bar. `vol_pct` / `_score_ep`'s live input is untouched.
   **Measured impact (offline, no DB access in the analysis sandbox — see limitation below): the fix is real but small and mostly moot.** The tier table only pays points at the 70th/90th percentile (`ep_rubric.SCORE_WEIGHTS["vol_conviction"]`, max +5 raw), so it can only ever ADD points relative to today's hardcoded 50 (which already sits in the zero-point default bucket) — never subtract. CHPT's honest point-in-time percentile at the 09:31 tick was 100 (true no-lookahead reading, `today_volume`=969,501 shares, 2.45x its 20-day mean); the fix alone moves its score 52.5 → 58.8 — real, but 6.2 points short of the 65 bar, so it categorically cannot admit CHPT on its own (the axis's own ceiling is +6.25 presented at regime×1.0, +7.5 at Bull). Across the 109 settled mcap-excluded ticker-days from the #622 study (the population most likely to show extreme volume, since these are all large qualifying gaps) only 1 of 109 would cross the score bar solely from this fix (FF, 2026-08-11 — a realized loser, -1.0R); the other 6 names whose true percentile was ≥90 were not already close enough to the bar to flip. That cohort never reaches live scoring anyway (a different, untouched gate excludes it), so this counts as evidence about the AXIS's size, not a live admission change. **The genuinely live-scored "control" population (ep_score IS NOT NULL, 90d, 418 ticker-days) could not be measured with the same fidelity in this pass**: the only offline capture available is SESSION-ONLY minute bars (09:30 start, no premarket), and calibrating that reconstruction against the 154-name cohort (where both readings exist) showed session-only volume understates the true point-in-time figure by a median ~42% and by far more for some names (ratio as low as 0.01), with high variance — not reliable enough to report a whole-book admission count. A ready pull for the control population's true point-in-time `today_volume`/`adv`/`rel_volume` (mirroring `scripts/probes/_622sweep_driver.py`'s tick-selection method) is the next step and needs DB access this analysis pass did not have.
   **No path to any open or closed trade**: `vol_percentile`/`vol_conviction` feeds only `_score_ep` → `ep_score`/tier (the alert/admission decision). Stops, targets and the exit ladder (`stop_limit_buy_price`, `profit_target_r_per_share`, `seed_exit_state`, `apply_daily_exit_step`) are ORB-high/low and ATR/R-multiple driven and take no score or volume-percentile input — verified by reading their signatures, not assumed.

## Change log (newest first)

### 2026-09-04 — #624: the low-cap lane ships as a SHADOW RECORDER (NO criteria, floor, stop, target, size or admission change)

**Trigger**: CHPT 2026-09-03 — a $134M name that gapped 33%, ran 46% and closed on the highest
volume in its history — was dropped by the $500M market-cap floor before it was ever scored
(`filter:mcap_too_small: $134M < $500M`, every tick). Operator: *"I'd like to look into this
filter to see if there's an edge to trade smaller caps, perhaps there's a separate lane for
it."* #622 asked the question; #623 put the volume rule on the universe we already trade; this
is the lane, approved 2026-09-04 with four rulings (shadow now with exit work in parallel · own
slot allocation · a LANE not a setup · sizing 1.0).

**The change**: nothing in this setup moves. `lowcap_lane.py` records, at every post-open scan
tick over the full candidate list, every sub-$500M name meeting the rule sentence in §"Low-cap
lane" (with every other gate it failed stamped, plus quoted spread and bid/ask size);
`lowcap_lane_replay.py` walks each one nightly under the CURRENT bracket from its own tick.
Registry row `magna53_lowcap` (shadow, median gate nulled), adapter, nightly job, liveness +
deploy-gate registrations, accrual review `lowcap_lane_graduation_624` bound to the **#545
ENTRY/EXIT TACTICS PROGRAM**.

**Evidence**: `_623_master.jsonl` — n=46 +0.527R, two carriers = 94% of the sum, ex-top-2 +0.03R,
4/46 ≥3R; full read in §"Low-cap lane" and `~/.claude/plans/unified-soaring-cascade.md`. The
evidence supports a SHADOW to resolve the tail rate; it does not support a paper flip (nine rows
on the current stack; two carriers at the thresholds' own coordinates).

**Anticipated effect**: none on production behaviour. ~0.7 lane rows a session on the evidence
(max 2/day); per tick ≤6 names enriched (yfinance profile — **not FMP**, `get_fmp_profile` is
yfinance under the name — one Polygon news read, one batched Alpaca minute-bar read, one batched
Alpaca NBBO read), deduped per (ticker, day). Nightly: one Alpaca minute-bar fetch per new lane
name, one SEC submissions read per filled walk.

**Reversion-flag**: NEW — a recorder. Off switch: `mi_strategies.magna53_lowcap.enabled=false`
(`should_run`). No `rule_eras.ADMISSION_SWITCHES` row: not an admission change (see the note in
that table; the row lands with the paper flip).

**Status**: shipped, awaiting field validation (verify-live: the nightly job in `mi_job_runs` and
the first `mi_lowcap_lane_signals` row on the next session with a qualifying name).

### 2026-09-03 — #482: the stop conflict (08-16 read vs Phase 3) now settles on live fills by ACCRUAL, not another re-slice (RECORD ONLY — no criteria, stop, target, size or admission change)

**Trigger**: Phase 3 (`docs/analysis/545p3_day1_stop_target_runner_sweep_2026-09-03.md`) found
the ORB low and entry − 0.5×ADR beat the live `entry − 2R` stop on the population the current
selector admits (bounds +3.9R / +0.5R) — a direct conflict with the 2026-08-16 entry below,
which was signed on 43 reconstructed April–May trades. Two populations, two answers, and
nothing said so. Operator 2026-09-03: *"After every analysis you just give the opposite rec, I
don't trust any of this."*

**The change**: nothing in this setup moves. A recorder
(`agents/market_intelligence/live_fill_counterfactuals.py`) now writes, beside every MAGNA53
fill, what ORB low / entry − 0.5×ADR / entry − 0.75×ADR would have produced under the live
ladder with the +2R target pinned exactly as §Stop-and-sizing states, and what three harvest
variants would have produced at the live stop — settled on the same stored bars through the
same exit ladder. **Every row is stamped with the ADMISSION ERA that produced the trade**
(`rule_eras.ADMISSION_SWITCHES`, each dated by the FIRST SESSION whose ORB admission ran
under the rule — the 08-19 gap floor was committed 15:37 ET and the 08-25 / 08-27 real-time
flips were 11:02–13:55 ET, so those days' fills were admitted by the OLD stack: 08-20 gap
floor 9% · 08-24 lattice/separation/shortlist · 08-26 RT universe · 08-28 rubric v4 + RT gap
authority · 08-31 extension cap 50 + RS slot rank, plus the alert row's own `rubric_version` / `score_tier` / `judge_grade` /
`grade_engine_authority`), because the operator will keep updating the filters as live EPs
are observed and the population under the recorder will move — the rows are read apart, never
pooled. ⚠ **SAME-COMMIT RULE for THIS file**: an admission-criterion change entered below
must also add its row to `rule_eras.ADMISSION_SWITCHES` (test-pinned in the forward
direction). Full entry, arms, THE-LINE proof and the gate: `docs/setups/exit_discipline.md`
change log 2026-09-03; review `live_fill_counterfactuals_first_read_482` fires at 20 live
era-C fills with the stop arms settled. **The 08-16 stop stays as signed** until that read
(THE LINE: sign-off + N≥10 + the harness).

### 2026-08-30 — #533: within-day slot ranking flips from accidental ALPHABETICAL to prior-day RS (OPERATOR-SIGNED, ONE-FLAG REVERTIBLE, watch lane shipped)

**Trigger**: operator 2026-08-05 ("does it capture the main goal of selecting best EPs in a given
day when there's many?") and 2026-08-11 on SE ("the ranking within same day EP is important").
The #533 analysis then found `process_new_alerts_live`'s `DISTINCT ON (ticker) … ORDER BY ticker,
ep_score DESC` leaves the across-ticker order ALPHABETICAL — ticker name was deciding which alerts
got the five position slots. **Operator ruling, verbatim: "switch to RS rank, but observe going
forward if it deteriorates or other ranking starts to do better."**

**Evidence** (`docs/analysis/533_within_day_ranking_2026-08-30.md` — 15 settled multi-alert
mornings, top-2 vs the same morning's rest, ret5 from day-0 open):

| ranking | median edge | mornings positive | sum of top-2 |
|---|---|---|---|
| alphabetical (incumbent) | +1.6% | 8/15 | −22.9% |
| ep_score alone | +1.6% | 8/15 | −5.3% |
| **prior-day RS composite** | **+8.4%** | **10/15** | **+55.1%** |

Robust to best-day removal (+8.1%) and to excluding 08-11, the in-sample day that inspired it
(+11.8%). Both directions (P14): RS's top-2 misses 4 day-best movers in 15 days — the SAME 4-count
as the incumbent, so the edge is not bought with recall; ranking reorders the board and can neither
add nor drop a name (pinned by test).

**⚠ THE HONEST LIMITS — carried here so they cannot be buried:**
- **~15 mornings is a small n; the error bars include zero for every challenger.** They do not
  include anything positive for alphabetical — the claim is "alphabetical is indefensible and RS is
  the best-evidenced replacement," not "RS is proven." Hence the watch lane below IS half the ruling.
- **Not tested by market condition** — too few days to split.
- **The ep_score row describes the OLD score** (pre-2026-08-22 rework); zero settled multi-alert
  days existed since. The watch's `rank_ep_score` column is how the new score gets its read.
- **Ranking chooses which orders get placed; it does not decide fills** — on 08-04 the top RS pick
  (LIFE) never broke its ORB high and cancelled unfilled.

**Anticipated effect**: no change to WHO alerts or HOW MANY orders go out — only the order they
compete for the 5 slots. Binds only on mornings with more board names than free slots (3 such
cap-blocked days in the 63-day evidence window); single-alert mornings are byte-identical. Expect
the LIFE/ZBRA-over-BTDR shape on the next 08-04-like morning, and `mi_ep_slot_rank_shadow` rows on
every ORB invocation with ≥1 HIGH alert.

**Mechanics**: dedup SQL untouched (byte-pinned); ordering applied in Python
(`ep_slot_rank_shadow.slot_rank_key`: RS DESC → ep_score DESC → ticker ASC); RS from
`latest_complete_score_date` strictly before the alert day (#554 guard); missing-RS names ranked
last, never dropped, logged. Toggle `ep_slot_rank_rs` (default ON; OFF = legacy order exactly);
fail direction = legacy order acts loudly (`slot_rank_fallback` audit row). Watch: 5 candidate
rankings recorded per invocation (raw inputs only, #583 class), both toggle sides, SILENT; review
`ep_slot_ranking_watch_533` fires at 10 settled multi-alert mornings with pre-registered
revert/switch bands (RS median edge ≤ 0 → revert; a challenger +5 points and leave-one-out-positive
→ switch proposal). Tests + 4 killed mutations: `tests/test_533_slot_ranking.py`.

**Reversion-flag**: NEW (this ordering was never a decision before — it was an accident of
`DISTINCT ON`; no prior change-log entry governs it).

**Status**: built + tested in tree 2026-08-30; acts on the next deploy with no flip needed —
`ep_slot_rank_rs` defaults ON (operator runs the deploy; scopes `market-agent` AND `execution`,
since `broker/live_tracker.py` runs on apollo-execution). Then "shipped, awaiting field
validation"; verify-live = `mi_ep_slot_rank_shadow` rows exist after the next morning with a
HIGH alert.

### 2026-08-29 — MAX_EXTENSION_PCT REVERTED 75% → 50% (OPERATOR-SIGNED; the 08-22 loosening rested on corrupt evidence)

**Trigger**: #595 found `mi_ep_missed_outcomes` was crediting names whose PRE-MARKET spike faded
before the open — days that were never tradeable setups — as "winners this gate cost us". The
2026-08-22 loosening was built on exactly that table. Operator, on the corrected read: *"go with
rec, and we'll review this again in future when we have more samples; also if/when we miss a real
strong EP because of this."*

**Evidence** (`docs/analysis/577_extension_cap_recheck_2026-08-29.md`):

| | 08-22 claim | corrected |
|---|---|---|
| winners the gate cost us | 21 | **12** |
| of those, inside the 50–75% band the change admits | (not asked) | **3** |
| the other nine | — | had run **128%–2,264%**, still blocked at 75 |

Replayed the band through the LIVE bracket on minute bars fetched from Alpaca (entry = stop-buy
at the 9:30 bar's high, stop = that bar's low, walked in sequence):

| replay | n | winners | expectancy |
|---|---|---|---|
| **the bracket as it was** | 15 | **0** | **−1.00R** |
| with the +2R half-off rule applied retrospectively | 15 | 3 (constructed) | −0.60R |

⚠ **THE CAP IS NOT THE BINDING CONSTRAINT — THE STOP IS.** Five band names ran **2.9R to 15.2R**
(AKTX +15.2R, HCAI +5.3R, WYHG +3.4R, ERNA +3.3R, BRUNW +2.9R) and every one still paid −1R,
because the 9:30 bar's low was taken out first. Reverting stops us paying −1R to discover that;
it does not make the cohort tradeable. **The lever is bracket geometry (#482), not admission.**

**Anticipated effect**: ~18 names blocked over 5 months that 75% admitted — 3 of which reached
+20% on paper and all of which stopped out. No other criterion changes.

**Reversion-flag**: **REVERSAL** of the 2026-08-22 loosening. Why the prior reasoning was wrong,
not merely incomplete: it counted missed winners off a table that scored pre-market fades as
setups, so its "5 names that ran ≥50% against 1 loser" was not measuring the band's tradeable
population at all.

🔭 **RE-OPEN ON EITHER OPERATOR-NAMED TRIGGER** — (a) the band accrues materially more than 15
scoreable names, or (b) **any single real strong EP is blocked by this gate**. Both are watched
nightly by `missed_outcomes.check_extension_cap_revisit`; (b) Telegrams per-name, because a
review he has to remember to call is one that does not happen.

**Status**: shipped, awaiting field validation. Verify-live = the next scan logs
`already up X% in prior 5 days` for a name in the 50–75% range.

### 2026-08-28 — #593: the sustain rule's revert condition is re-stated as a RATE on TRADEABLE misses (OPERATOR-SIGNED)

**Trigger**: the 2026-08-02 pre-registration — *"a rejected name running ≥+20% once is a review,
twice a revert"* — was literally met at 20 names while the reading was an artifact. The operator
ruled the fix and then twice sharpened it, in his own words:
- *"yes, it's more accurate"* — measure the run from **the level the rule declined**, not the open.
- *"those stocks that we turned away has to be theoretically traded before we count them vs just
  admitted in that stage."*
- *"2nd eval check is ratio, if it's 1 of 100 then it's small vs 1 of 5."* → **X = 10%**, and
  *"aligned with your conditions"* on the two guards below.

**Evidence** (`docs/analysis/sustain_revert_rebased_2026-08-28.md`): 128 `ep_rt_sustain_reject`
ticker-days, 2026-08-03→08-28, 19 trading days, 65 scoreable.

| measured how | breaches |
|---|---|
| ≥+20% from the day's OPEN (the original, unnamed baseline) | 39 |
| ≥+20% from the DECLINED LEVEL (`prev_close × (1+rt_gap/100)`) | 13 |
| …that still held the 9% gap floor at the d0 close | 13 |
| …**and** cleared the $50M dollar-volume floor | **2** |
| …**and** traded above the declined level on d0, so an entry was reachable | **2** |

**Eleven of the thirteen were too illiquid to trade** — never a cost whatever the rule did.
**2 of 65 = a 3% tradeable-miss rate.**

**THE AMENDED CONDITION** (supersedes the ≥+20% arm of the 2026-08-02 pre-registration; the
"first 30 live catches vs the replay" arm is unchanged):

> **REVIEW** when *tradeable misses* exceed **10%** of *scoreable declined names* over a rolling
> **30 trading days**, evaluated only when that window holds **≥30 scoreable declined names**.
> A review raises it to the operator. **It never reverts on its own.**
>
> - *tradeable miss* = a declined name that (a) traded ≥+20% above the price the rule declined
>   (`prev_close × (1+rt_gap/100)`, recorded on every `ep_rt_sustain_reject`), (b) still held the
>   9% gap floor at the d0 close, (c) cleared the $50M dollar-volume floor, and (d) traded above
>   the declined level on d0 so an entry was reachable.
> - *scoreable declined name* = a rejection with a `prev_close` and forward bars. **This is the
>   denominator and it is stated deliberately** — "all rejections" would drift silently as data
>   coverage changes.

**Why each guard exists.** (1) **A rate, not a count**: "twice a revert" across 128 rejections is
not a threshold but a certainty — any gate that declines anything accumulates two counter-examples
eventually, so as written it could only ever fire and never clear. (2) **≥30 minimum**: in a quiet
week with 3 declines a single miss reads 33%; the news-source-quality check has 11 `low_n` firings
of 14 for exactly this reason. (3) **Review, never auto-revert**: this governs a live admission
gate — mechanically reverting trade discipline on a metric is precisely what THE LINE forbids.

**Anticipated effect**: no behaviour change today. The rate reads **3%** against a 10% trigger, so
the condition does not fire; the rule stands on honest evidence rather than a bad yardstick. It
now takes a ~3× worsening — about one tradeable miss every three days against one every ten — to
raise a review.

**Reversion-flag**: **REFINEMENT** of the 2026-08-02 pre-registration. The prior form was not
wrong in intent; it was unfalsifiable in practice because it named no baseline, no denominator and
no window. Nothing about the rule itself changed.

**Status**: condition amended, operator-signed 2026-08-28. **Wired 2026-09-03** as a standing
predicate — `sustain_reject_tradeable_miss_rate_593` in `data_gated_reviews.yaml` — so it
self-evaluates weekly instead of requiring a by-hand re-derivation. **Not yet verified-live**: the
predicate has never executed against prod (verify with `scripts/probes/_593_predicate_verify_2026-09-03.sql`
— read-only, $0). Trigger basis is MFE (max forward high), the looser of the two readings and the
one both prior signed reads used; the settled-close reading (~2.3x lower) is surfaced alongside
whenever the review fires, per the entry's `action_when_ready`, but is NOT the trigger — that swap
is a separate operator decision, not made here. Hand-derived reading (docs/analysis/593_sustain_revert_2026-09-01.md):
4/87 = 4.6% (MFE) / 1/87 = 1.1% (settled), both well under the 10% trigger.

### 2026-09-03 — #593: the "tradeable miss" definition is REWIRED from a price-move test to a bracket replay (OPERATOR-DIRECTED)

**Why**: his own framing — *"the two key things to know is 1) did it turn away real EPs, those
that would've made us 4R+ or 2) to a lesser extent those that would've made us positive return at
all."* A price move is not a trade outcome. Two of the four names the ≥+20%-price-move test (leg
(a) of the 2026-08-28 definition above) flagged — IPST (declined level $9.25 → 5th-session close
$4.71) and WETO ($22.74 → $11.50) — both spiked for minutes and closed **~49% below the level they
were declined at**. They would have been STOPPED OUT by our own bracket; turning them away was
correct, and the price-move test counted them as mistakes.

**THE CHANGE**: leg (a) of the "tradeable miss" definition — *"traded ≥+20% above the price the
rule declined"* — is REPLACED by an actual bracket walk. A nightly recorder
(`agents/market_intelligence/sustain_reject_replay.py`) reconstructs the CURRENT-era MAGNA53 entry
(ORB, the admission ATR gate, the stop-limit-buy trigger in the submission window — submitted at
the reject's OWN tick, never a fixed 09:31) for every net-declined `ep_rt_sustain_reject` name,
and — if it would have filled — walks the SAME live exit ladder
(`live_fill_counterfactuals.walk_arm`, reused). A *tradeable miss* is now: (a) the replayed bracket
realized ≥4R (settled) or is currently marked ≥4R (still open — a running winner must never make
the trigger under-fire), OR to a lesser extent any positive return, (b) still held the 9% gap
floor at the d0 close, (c) cleared the $50M dollar-volume floor. Legs (b) and (c) are UNCHANGED.
The retired price-move legs (peak-high MFE and settled-close, both vs. the declined level ×1.20)
are still stored on every row (`breach_mfe_20`, `breach_settled_20`) for a side-by-side report —
retired as the TRIGGER, not deleted as a measurement.

**THE 10%/30-TRADING-DAY/≥30-MINIMUM MECHANICS ARE UNCHANGED** — only what counts as a miss moved.
`sustain_reject_tradeable_miss_rate_593` in `data_gated_reviews.yaml` was rewired in the same
commit to read the recorder's stored columns.

**⚠ THE THRESHOLD QUESTION THIS RAISES, OPEN, NOT DECIDED HERE**: 10% was calibrated against the
price-move definition (4.4% MFE / 1.1% settled, measured 2026-09-01). A ≥4R replay test is a
strictly narrower bar than "ran +20% at any point," so it will trip far less readily than either
retired basis at the same 10% line — the rate this predicate now reports is **not directly
comparable** to that 4.4%/1.1% history. Whether 10% is still the right number for the ≥4R
definition is the operator's call, to be put to him once the predicate has a real reading (THE
LINE — a revert-review threshold on a live admission gate).

**Reversion-flag**: REFINEMENT of the 2026-08-28 rate mechanics (which stand); REPLACEMENT of the
2026-08-28 breach TEST specifically. Nothing about the sustain rule's own admission logic changed.

**Status**: rewired 2026-09-03, code-complete + suite green (`tests/test_sustain_reject_replay.py`,
28 tests). **Not yet deployed / not yet verified-live** — built with no prod DB access from this
session; the table and job ship on the next market-agent (+ execution, since `db.py`/`scheduler.py`
are on the execution-loaded-module list) deploy, and the first real reading lands after the first
nightly run (job `sustain_reject_replay`, 18:13 ET) backfills the standing 40-trading-day window.

### 2026-08-28 — STATUS RECORD: two real-time toggles went live and the SSoT never said so

**Trigger**: `live_rules.py --drift-only` at OPEN, 2026-08-28. It flagged that every mention of
`ep_rt_volume_authoritative` and `ep_rt_universe_authoritative` in this file still reads OFF/dark
while both are ON in `mi_safeguard_state`. The change-log entries below are accurate *as of their
own dates* — nothing there is being rewritten — but no entry ever recorded the flips, so the
current state was only discoverable from the database. That is the stale-SSoT failure this
project treats as worse than no SSoT.

**Current state, read from `mi_safeguard_state` (all `global`):**

(Each row states the flip on the toggle's own line — `live_rules.py`'s unrecorded-flip check
reads evidence per-line, so a status split across table cells reads as no evidence at all.)

| toggle | status |
|---|---|
| `ep_rt_universe_authoritative` | **went live 2026-08-25 11:02 ET** |
| `ep_rt_gap_down_authoritative` | went live 2026-08-02 |
| `ep_rt_entry_gap_recheck` | went live 2026-08-02 |
| `ep_rt_sustain_enabled` | went live 2026-08-02 |
| `ep_rt_volume_authoritative` | **went live 2026-08-27 11:19 ET** |
| `ep_rt_gap_authoritative` | **went live 2026-08-27 13:55 ET** — see the #559 entry |

**Anticipated effect**: none — this entry changes no behaviour. It records state that was
already live so the document stops contradicting production.

**Reversion-flag**: n/a (a record, not a change).

**Status**: recorded 2026-08-28. Each toggle reverts independently in ~60s via
`mi_safeguard_state`, no deploy.

### 2026-08-27 — #233: the Perplexity agreement boost is RETIRED; the DISAGREEMENT goes to the judge instead (OPERATOR-SIGNED, rubric rule 7)

**Trigger**: operator reframed the question — *"i'm not too concerned about boost giving us
better winrate, where i see potential value is perplexity or any 2nd model giving us
validation vs catching potential errors, can it do that?"* — then *"let's do both and capture
the results going forward, especially the double counting by judge potential."*

**Evidence** (`docs/analysis/pplx_agreement_boost_233_2026-08-27.md`, two measurements):

*The boost, over 419 alerts with the field populated (373 with a forward window).* Boosted
alerts ran a **smaller** 5-day max move than unboosted — **9.17% vs 11.20%**; HIGH-only 9.70 vs
11.14; agreement alone 8.97 vs 11.53. ⚠ Most of that is a **confound**: the boosted group gaps
15.5% against 18.8%, and the metric scales with gap. Controlling for it (same score band):
6.3 vs 9.8 · 10.1 vs 12.4 · 11.4 vs 11.6 · 12.7 vs 10.5 — worse in two, level in one, better
in one. **Within band there is no signal.** So the boost was a 20% score increase whose only
visible effect was lifting smaller movers over the bar.

*The disagreement, n=174 alerts carrying all three reads of one catalyst* (possible only
because `judge_grade` was persisted and backfilled the same day). The judge disagrees with the
grader's label on 45 of 174 = **26% base rate**. Given Perplexity also disagrees: **33%**.
Given it agrees: **18%**. Recall 29/45 = **64%**, precision 29/87 = **33%**. **When both flag
the same alert they agree on direction 25 times out of 29 (86%)**, and both lean the same way —
label too generous.

⚠ **N-honesty**: 174 alerts, and the judge is **not ground truth** — this is model-vs-model.
No claim is made that either critic is right, only that they co-occur.

**Anticipated effect**: (1) every alert's `confidence_multiplier` is now 1.0, so scores fall
~17% for the ~40% of alerts that were being boosted — expect fewer of those to clear the bar,
which is the intended correction, not a regression. (2) On alerts where the second model
disagrees (about half), the judge sees one extra block. Agreement renders **nothing**, so those
prompts are byte-identical to before. `MIN_GAP_PCT`, the tier logic, safeguards, sizing and the
ORB window are untouched.

🔁 **THE DOUBLE-COUNTING WATCH — the operator asked for this by name.** The judge already reads
Perplexity's `[Web summary]` TEXT, so its grade is **not** an independent witness; treating it
as a vote counts one source twice. Two defences shipped: **rubric rule 7** tells the judge to
use a disagreement as a prompt to re-read the evidence and to keep its own read if unmoved; and
the **monthly judge review now reports `sided_with_second_opinion` split on the ship date** —
how often the judge landed on the second model's grade before it was told, versus after. Flat
across that boundary = the instruction is holding. A jump = the judge is voting, and rule 7
needs revisiting. Cohorts under 20 print as "not yet readable".

**Reversion-flag**: NEW for the second-opinion block. **REVERSAL** of the agreement boost, live
since the Perplexity integration — it was shipped on the assumption that two models concurring
is evidence about the catalyst. That was never measured, and the measurement above does not
support it. Reversion = restore `confidence_multiplier = 1.2` on the agreement branch; it is a
code change, not a toggle.

**Status**: shipped, awaiting field validation. Rides the SAME `RUBRIC_VERSION` bump and the
SAME robustness-eval rerun as the #602 axis split rather than paying for a second one
(batch-judge-regrades discipline). Verify-live = the next alert where Perplexity disagrees
shows the block in the judge's prompt, and the monthly review prints both cohorts.

### 2026-08-27 — #559: the real-time gap decides the 9% floor in BOTH directions — `ep_rt_gap_authoritative` ON (OPERATOR-SIGNED, LIVE, one-flag revertible)

**Trigger**: operator, on being told the delayed price still decides the floor for names
already on the morning list — *"justify using a delayed data, i don't get it"*, then
*"bugs need to be fixed, if there's other consequences of the fix, then fix those too."*
The held reason was never data quality; it was grading cost. So the cost got measured.

**Evidence** (`docs/analysis/rt_gap_up_authority_559_2026-08-27.md`): the 2026-08-01 entry
below priced the up-half at **+25.0 candidates/day** and held it on the LLM-latency budget
before the 09:45 cutoff. That counted `ep_rt_floor_flip_up` EVENTS — undeduped across
5-minute ticks, including ticks after 09:45, and without checking whether the name was
already in the funnel. Deduped to ticker-days, in-window only, 40 days to 08-27:

| what the flip-up actually was | ticker-days | per day |
|---|---|---|
| already evaluated, died downstream anyway | 301 | 10.8 |
| alerted anyway (delayed caught up in time) | 49 | 1.8 |
| **never evaluated — the true new admits** | **70** | **2.5** |

**The new grading load is 2.5 names/day, not 25 — the objection was wrong by 10×.** Nine in
ten flip-ups are names already looked at; for those the switch changes WHEN they are seen,
not WHETHER. What the 2.5/day are worth (`mi_daily_closes`, 61 scoreable): hold-to-day-5 is
−0.9%, 28 up / 33 down — a coin flip; but 26 of 61 (43%) traded ≥10% above the day-0 close
within five days (BRUN +26.0, ENTG +21.8, CECO +19.6, TTMI +18.0, BCRX +16.8, PI +16.6).
⚠ Baseline is the day-0 CLOSE, not the ORB entry, and carries no stop — an upper bound on
what the switch can add, NOT a forecast, and the 70 were never graded so an unknown share
would die at the catalyst/score/ADV gates anyway.

**Anticipated effect**: ~2.5 additional graded candidates per day, and earlier evaluation
for ~10.8/day that are currently seen only once the delayed feed catches up — the TWST
2026-08-19 failure mode (admitted 09:45:11, eleven seconds after the ORB window shut). No
threshold moved: `MIN_GAP_PCT` stays 9.0%, scoring, safeguards, sizing and the ORB window
are untouched. Polygon `prevDay.c` remains the sole gap denominator.

📌 **OPERATOR'S STANDING RULE FOR WHAT TO DO IF VOLUME BECOMES A PROBLEM (2026-08-27,
verbatim)**: *"If and when the volume becomes an issue, it means either 1) we need stricter
filters because we're admitting garbage or 2) they aren't garbage and we have genuinely good
potential winners (not that they must win), and that is a good thing but may mean we need to
adjust our holding cap, etc."* — i.e. rising volume is a signal to diagnose WHICH of those
two it is, never a reason to revert the switch. Reverting on volume alone would restore
deciding on a price we know is stale.

**Reversion-flag**: NEW for the flip-UP half. The REMOVE half went live 2026-08-01 (entry
below); this completes the toggle it was split out of. Reversion = set
`ep_rt_gap_authoritative` back off in `mi_safeguard_state` — ~60s, no code change, no deploy.

**Status**: **LIVE — operator signed off 2026-08-27 ("flip it"), flipped 13:55 ET.** Toggle
set in `mi_safeguard_state` (`ep_rt_gap_authoritative` / `global` / `on`); both containers
confirmed reading `full=True down=True universe=True` (apollo-market and apollo-execution).
Awaiting field validation. **Watch, both already instrumented**: (1) latency against the
09:45 cutoff (`ep_rt_admit` + scan-tick timings) — 2.5 extra candidates at 27s median is
well inside budget, but this is the number that would invalidate the decision; (2) whether
the extra 2.5 dilute the 5 entry slots on a ranker not validated out-of-sample — the P9
concern raised 2026-08-19, which the pricing analysis does NOT answer.

### 2026-08-27 — #602: the judge's two decisions get two separate vocabularies, and each states its own one-line reason (OPERATOR-SIGNED, rubric v3 → v4)

**Trigger**: an operator triage of the OKTA 2026-08-27 alert, which said *"demoted from
gamechanger to high"* while nothing had been demoted. Tracing it exposed a naming collision in
the judge's own instructions AND a claim we had been making in five places that was simply
wrong ("the judge's view of the catalyst is advisory"). His words after the fourth confusing
answer: *"every question you answer contradicts itself."* Full account:
`docs/analysis/judge_authority_2026-08-27.md`.

**Evidence**: source-level, not statistical — this is a BUG FIX in a prompt, not a criteria
change, so no N≥10 threshold backtest applies (the classification rule: enforcing a spec the
prompt already states needs no new evidence).
  - `_RUBRIC` rule 2 taught PROMOTES / DEMOTES as verbs about the **grade** ("a catalyst that
    is immaterial for a large company DEMOTES it"), while its closing line specified
    `direction_vs_floor` as *"compares your tier to the floor tier given"* — a **tier** field.
    One vocabulary, two axes.
  - OKTA 2026-08-27 is the reproduction: `judge_tier=HIGH`, `baseline_floor_tier=HIGH` (so the
    tier held), `judge_direction=demote`, and a rationale arguing the **grade** down. The model
    answered the tier field on the grade axis, exactly as taught.
  - Prod, 60 days to 2026-08-27: `grade_engine_authority='judge'` on **145 of 147** alerts, and
    the judge's tier differed from our score's on **43**. This field is on a load-bearing path,
    which is why the fix is sign-off gated rather than a wording tidy.
  - Separately measured while tracing: the judge's own catalyst read differs from the stored
    label on **37 of 145** alerts — that disagreement had never been visible on any surface.

**Anticipated effect**: **no change to any grade or tier by construction** — nothing in the
scoring, the thresholds or the tier logic is touched. Two changes only. (1) `direction_vs_floor`
should now agree with the tier movement instead of sometimes reporting the grade axis; the
display-side note that flags the contradiction should stop firing (it fired on OKTA today).
(2) Two new REQUIRED output fields, `grade_reason` and `tier_reason`, render as a one-line
*why* on the alert's `⚖️ Judge:` and `✅ Decision:` lines. Both are display; a model omission
degrades to the previous rendering and never fails a verdict. Watch for: any drift in the
distribution of `grade`/`tier` after the flip, which would mean the reword moved the judge and
not just its reporting — the robustness eval below is the gate for exactly that.

**Reversion-flag**: NEW. No prior change has touched `direction_vs_floor`'s specification. The
2026-08-27 display-side pass earlier the same day is a separate, already-shipped change that
made the alert say what acted; this one fixes the cause rather than the symptom.

**Status**: shipped, awaiting field validation. Gated on a passing
`scripts/evals/run_judge_robustness_eval.py` run against rubric v4 (~36 calls, ~$1.50) —
deploy gate `[5m/7]` hard-fails until the pass record is regenerated, so no rubric edit can
ship ungraded. Verify-live = the next EP alert carries a `⚖️ Judge:` line with its own reason
and a `direction` that agrees with its tier.

### 2026-08-27 — #490 §6.1: the real-time volume read can no longer reject a name on data that does not exist yet (BUG FIX, DARK — no criteria change, toggle NOT flipped)

**The rule, in plain words:** *a volume bucket that contains zero minute BARS has not been
measured; it is not a reading of zero volume. When the bucket the pace gate is about to use has
no bars in it yet, the real-time number is set aside and the old delayed number decides —
exactly as it does today. Bars that are present and happen to carry zero volume are a real
measurement and keep counting.*

**Trigger**: VEEV gapped 10.7% on 2026-08-27 and was rejected `session_rvol_too_low`
(0.27×) while actually trading ~5× its normal pace. The remedy (`ep_rt_volume_authoritative`,
RT-5) was about to be considered — and would have introduced a NEW false-reject in the other
direction on its first tick of every session.

**Root cause (established from data, not assumed)**: the EP scan's 09:30 tick fires 5–25 s
after the bell. Alpaca has published no minute bar timestamped ≥ 09:30 yet (the 09:30 bar only
closes at 09:31:00), so `get_alpaca_minute_cum_volumes` sums **zero bars** into the session
bucket → 0, while the pm bucket from the SAME successful call is full and correct.
`compute_rvol_at_time` then divides 0 by a healthy baseline → 0.00×.
Evidence, 678 recorded `ep_rt_volume_shadow` / `ep_rt_rvol_gate_flip` rows (2026-07-27→08-27):
- 155/155 rt=0.00× rows are at the 09:30 tick, session anchor, `session_vol == 0`, `pm_vol` large.
- 0/523 rows at every other tick (07:00→09:55, **including 09:31**) have a zero acting bucket.
- 0/678 rows have BOTH buckets zero.
Rivals ruled out: a failed batch returns `{}` and the symbol is then absent from the map, so no
shadow row would exist at all (all 155 exist, carrying real pm volume) — not a call failure, not
a feed gap (prod runs `ALPACA_DATA_FEED=sip`). Not an off-by-one on the bar window: the request
passes **no `end`**, the split constant maps a 09:30 bar to the session bucket, and the 09:31
tick never reads zero — dropping the newest bar would make it. Not a timezone error: `tick_et`
(rendered from `now_et`) spans 07:00–09:55 ET and sits 0–9 min before each row's `created_at`
in ET; a UTC `now_et` would render 11:00–13:55.

**Shipped** (`collector.get_alpaca_minute_cum_volumes`, `ep_detector._rt_anchor_measured` /
`_apply_rt_volume`): the collector now returns `pm_bars` / `session_bars` alongside the volumes.
The authoritative substitution is ALL-OR-NOTHING on the acting anchor having ≥1 bar — anchors,
`today_volume`, `rel_volume`, `projected_vol_multiple` and `volume_source` all move together or
none do (half-enabling it would leave a premarket-only sum silently undercounting `rel_volume`
and the open-intensity projection). Absent symbol, empty bar list, missing count key, or an
unparseable count all fail to the delayed read — never a reject.

**Shadow telemetry is ADDITIVE ONLY**: `would_rvol_gate_flip`, the event type and the message
are byte-identical. Two new fields ride alongside — `rt_vol_state`
(`measured` / `no_bars_for_anchor`) and `would_rvol_gate_flip_measured` (the verdict once the
fallback is honoured). Reclassifying the recorded flip list is the operator's call
(CHANGE_PROCESS rule 3), so the code records both readings and decides neither.

**Measured on the recorded flip list** (247 flips): the real-time read would ADMIT **87** rows /
83 ticker-days that the delayed read rejected (VEEV, MBUU, OOMA, CHRN, …), and would REJECT
**160** that the delayed read admitted — of which **153 are the 09:30 artefact this fix
removes**. (153, not 155: all 155 rt=0.00× readings sit at that tick, but on 2 of them — ECG
08-05, EHC 08-06 — the delayed read failed the gate too, so nothing flipped.)
The 7 genuine under-admissions are CDNA 07-31, PAYC · CAI 08-06, PSIX 08-07, ATRO
08-12 (all pm anchor, 100–13k premarket shares, delayed 1.06–3.41× vs rt 0.31–0.99× against a
1.0× bar) and FTK 08-05 09:31 · WPP 08-06 09:35 (session anchor).

**⚠ Separate finding, NOT fixed — admission criteria, operator's call.** The *delayed* side of
the 09:30 flip is also a non-measurement. `c["today_volume"]` is `snap["day"]["v"]`, the
full-day cumulative INCLUDING premarket, and `ep_detector` charges 100% of it to the **session**
bucket once the clock passes 09:30. At the 09:30 tick that number IS the premarket total
(median 0.86× the real-time premarket sum, n=155), so OKTA's "15.14× session pace" is premarket
volume divided by a session baseline. FTK and WPP above are the same inflation one and five
minutes later — there the real-time read is the correct one. Reading the real-time volume at
09:31 instead of 09:30 would also remove the artefact, but that changes WHEN the scan measures
and is likewise the operator's call; the fallback is the correct dark-ship fix.

**NOT changed**: `ep_rt_volume_authoritative` stays OFF (no override row; env unset). No
threshold moved — `MIN_SESSION_RVOL` / `MIN_PM_RVOL` are still 1.0×, `MIN_BASELINE_N_FOR_GATE`
still 10. With the toggle OFF the live gate is byte-identical, freeze-tested by AST (the sole
call to `_apply_rt_volume` is nested inside `if _rt_vol_authoritative:`).

**RT-5 precondition**: the design says flip RT-5 ≥3 market days after the gap flip.
`ep_rt_universe_authoritative` went on **2026-08-25 11:02 ET** (mid-session, so 08-25 is not a
full market day under it). Market days after: 08-26, 08-27, **08-28** → the earliest date the
precondition is met is **Friday 2026-08-28**. Today (08-27) is the 2nd.

**Reversion-flag**: none — this is a bug fix to a dark mechanism, not a reversal. Rollback =
revert the two functions; the toggle was never on.

**Evidence**: `scripts/probes/_490rt_shadow_rows.psv` (all 678 rows, captured once, read many).
14 unit tests in `tests/test_490_rt_volume_nodata_fallback.py` including the load-bearing case —
bars present carrying zero volume MUST keep acting, which is what separates this fix from a
blanket "fall back whenever the volume is zero".

**Deploy scope**: both `collector.py` and `ep_detector.py` are in
`scripts/exec_loaded_modules.txt` → `deploy.sh market-agent` (or `both`) **then**
`deploy.sh execution`, two-step, or the running execution container stays stale.

**Status**: in the working tree, uncommitted, undeployed. Toggle NOT flipped.

### 2026-08-22 — ONE GRADE EVERYWHERE: the admission filters read the corrected (lattice) grade (OPERATOR-DIRECTED, REVERSAL of the same-day flip's scope line)

**The rule, in plain words a trader can repeat back:** *every decision about a candidate —
filter, score, tier — uses ONE catalyst grade: the corrected one. A routine-news name gapping
under 12% is skipped, but "routine" means the corrected grade, so a real EP the news grader
mis-labels routine is no longer thrown away before the correction can save it. Under 25,000
pre-market shares is skipped unless volume is exploding (5× pm RVOL) or the gap is 10%+ with a
strong-or-better catalyst.*

**Trigger**: Operator, mid-review of the flip (verbatim): *"why you think it's ok that we
change grading that it's ok to have places to use old grading, if we change something we
change it everywhere, consistency at all times, no forks"* and *"stop justifying bugs because
it's the way it is, either things are right or not."* The flip-day scope line had deliberately
left `_post_grade_filters` reading the RAW LLM grade while `_score_ep` read the lattice
verdict — so a real EP wrongly graded routine at a sub-12% gap (the typical labelled real EP
gaps ~10%; 4 of the 7 ever-graded labelled real EPs came out routine) was binned at admission
before the correction built the same day to save it could act. MRNA 2026-08-19 scored at its
gap-10.0 tick graded `strong` — one grade notch from dying in that filter.

**Evidence** (read-only prod capture `scripts/probes/_lattice_admission_capture_out.txt` +
the #533 shadow eval `docs/analysis/catalyst_tier_shadow_533_2026-08-22.md`):
- *Real EPs killed by the routine-gap<12 filter, BEFORE:* **0 of the 26 labelled real EPs on
  their recorded prod ticks** (Q4 — their routine verdicts arrived AFTER admission via the
  revenue-gate/prose downgrades, or they died on other gates: RVOL, top-20 cap, score<50,
  M&A). The kill is a standing structural exposure, not a recorded event: 19 of 26 labelled
  real EPs gap under 12% at the open, and the grader hands routine to real EPs — any future
  member whose routine verdict lands AT GRADE TIME dies in this filter with no score, no
  alert row, no recorded text. *AFTER:* still 0 recorded (nothing regresses — the lattice
  never demotes a non-routine grade to routine, so the acting-grade filter is monotonic in
  the ADMIT direction, pinned by `test_lattice_never_demotes_any_grade_to_routine`); the
  routine-graded-real-EP class now reaches the corrective and the scorer instead of the bin.
- *Ordinary gappers stopped by the routine filter, BEFORE:* 75 graded ticker-days per 60d
  (42 scan days) ≈ **1.8 killed per scan day**, 68 of them terminal (never alerted that day)
  ≈ 1.6/day. These produce zero alerts today. *AFTER:* a killed name is admitted only when
  the corrective promotes it (fired on 6 of 45 routine live alerts ≈ 13%) and it then still
  faces the score bar: with flat gap credit 10 + strong 15, only ADV$ ≥ $500M reaches raw 40
  (the bar at regime ×1.0) on those terms alone — 12 of the 75 killed ticker-days qualify.
  Expected new HIGH alerts ≈ 75 × 0.13 × 0.16 ≈ **1.6 per 60d ≈ +0.04/day**; upper bound
  ≈ +0.1/day if the $250-500M-ADV rows cross via float/theme bonuses or a Bull ×1.2 regime.
  Baseline: 111 HIGHs / 38 alert days ≈ 2.9/day → **≈ +1-3% alert volume.**
- *R6 pm-shares carve-out (`game_changer` arm, acting side only):* 40 pm-shares-killed
  ticker-days per 60d (all gap ≥ 10), 18 terminal; their grades were never recorded, so the
  delta is a bound, not a measurement: at the graded-pool top-tier rate (43%) × the lattice
  keep-rate (~40%), ≈ 3 per 60d ≈ **+0.07/day** newly bypass the share floor and still face
  the RVOL gate + score. Corrective-rate caveat: the 13% is measured on routine ALERTS
  (gap ≥ 12) — the killed pool (gap 9-12) may differ; the new filter-kill tier records
  (below) measure both channels exactly from day one.
- *Total priced admission delta:* **≲ +0.1-0.15 HIGH alerts/day against 2.9/day** — the
  "materially more noise" alternative (a different gap threshold on the corrected grade) is
  not warranted at this cost; no threshold was touched.

**Anticipated effect**: (1) the routine-gap<12 filter and R6 carve-out condition on the
acting grade — no candidate is filtered on a grade the score disagrees with; (2) ≈ +0.04 to
+0.15 HIGH alerts/day (both channels, bounds above); (3) filter-killed GRADED candidates now
write `mi_catalyst_tier_shadow` rows (ep_score/live_tier NULL) — closing the ARM-class
evidence hole that made 4 of 7 routine-graded members "undetermined offline"; (4) two rare
consumers change behaviour with the one-grade rule, stated not hidden: a corrective-promoted
routine on an earnings day now enters the revenue gate (≤ ~1 extraction/week, cached
per ticker-day), and a lattice-DEMOTED game_changer with no-fresh-news prose is now eligible
for the #72 prose downgrade (tightening only on the demoted-recap × no-news intersection).

**#72 downgrade Telegram now reports what actually happened, not what the downgrade alone
decided** (Finding 5 fix, 2026-08-2x): two of the #72 downgrade's own prose markers ("no
specific catalyst" / "no specific news") are also rule-4 demotion-marker text, so if the
same prose also names a concrete company event, the lattice can promote the name straight
back out of routine — the message now sends AFTER that final resolve and names whichever
grade actually acted, instead of asserting "will not promote to HIGH" before the corrective
has had a chance to run.

**Reversion-flag**: REVERSAL of the 2026-08-22 "Catalyst tier FLIPPED" entry's scope line
("the flip's re-tiering deliberately does NOT extend into `_post_grade_filters` — the shadow
counterfactual was evaluated within the post-filter pool; extending admission would loosen
unevaluated"). That reasoning was WRONG, not incomplete: it preserved a fork in which
admission killed candidates on the exact grade the flip was signed as too broken to act on —
re-creating the measured failure (a backwards grader deciding life-or-death) INSIDE
admission, where a false exclusion leaves no row and no trace (P1/P14); and the loosening it
feared is measurable and small (priced above). Consistency of the acting grade outranks
counterfactual purity of the evaluation pool. Also extends R6 to `game_changer` on the
acting side only — REFINEMENT of 2026-05-17 P2.1b (without it, a lattice promotion would
strip a name of a bypass its old grade earned: a better grade admitting less).

**Status**: built + suite-verified (6061 passed / 7 skipped; 16 new tests in
`tests/test_lattice_admission_consistency.py` pin behaviour, direction, and the
no-second-grade-path source invariant). COMMITTED 2026-08-23; deploys in the
SUNDAY 08-23 after-hours window (21:15-22:15 ET, scope `both`) so it is live for Monday's
07:00-10:00 ET scan — a Monday-noon deploy would land AFTER the morning scan and push the
first live test to Tuesday.
Same ONE revert flag as the flip: `catalyst_tier_lattice` OFF = the raw LLM grade acts at
every point, byte-identical pre-flip behaviour (the flip-day mixed state — lattice score,
raw filters — is deliberately no longer reachable: it IS the fork the operator forbade).

### 2026-08-22 — Grading shortlist ranks by the three-term PRE-SCORE, not gap size (OPERATOR-DIRECTED, ONE-FLAG REVERTIBLE)

**Trigger**: the same-day #533 separation change deleted gap size from the SCORE for running
backwards on real EPs (AUC 0.34, flat gap points, conviction floors 1–3 deleted — all
operator-signed), yet `run_ep_scan` still SORTED the morning's candidates by `gap_pct` and
graded only the first twenty — the proven-wrong measure kept deciding which names get looked
at at all. Operator, on finding it still live: *"how are we still using it after all this
work… that's like saying this is completely wrong for weeks and fixing it for weeks and then
say we still use it."* Second, forward-looking reason: admitting more candidates via
real-time prices (#584-class widening, separately dated) would push more names into the same
20 slots, still ordered by the wrong key — the shortlist had to be fixed before admission
widens.

**Evidence**: Stage 0 replay of all 16 cap-attributed labelled real EPs
(`docs/analysis/shortlist_survival_stage0_2026-08-22.md`) + the pre-score replay of every
logged scan day (`docs/analysis/shortlist_prescore_replay_2026-08-22.md`). **Stated plainly:
Stage 0 measured the recovery at "at most one name"** (SNOW 05-07, conditional on an ungraded
catalyst; demonstrably recoverable end-to-end: zero — the wall behind the cap is the score
bar, not the cap). **So the justification is COHERENCE (a measure proven backwards must not
decide who is looked at) and FUTURE-PROOFING, not retention recovery.** What the re-ranking
demonstrably improves: the liquidity axis ranks all five of the killed set's biggest
R-winners (MU/SNDK/BE/ARM/SNOW) inside the top 20, where gap ranked them 20th–100+.
Weight-table basis: liquidity (15, weight 3 — ex-ante 20d ADV$ AUC 0.72, the best measured
signal), gap (10, weight 1, FLAT — operator signed "stop paying for gap size"), theme (10,
weight 1 — mirrors the live R4 bonus). `extension` / `prior_3m` / `adv_trend` /
`cooldown_proximity` deliberately EXCLUDED: the prior-momentum penalty was deleted the same
day for firing on real EPs and junk at identical rates (31% vs 32%); the others are
unmeasured — a term enters only with a measured direction. A starting table, not a fitted
one. Tie-break policy (required — Stage 0 found a 9-way tie at the rank-20 cut): continuous
ADV$ desc, then ticker asc; never gap.

**Anticipated effect**: the graded 20 change on flood mornings — liquid moderate-gap names
(the real-EP profile) enter the shortlist; thin max-gap names drop past rank 20 (logged, not
graded). On thin boards (<20 candidates) behaviour is identical — everyone was graded before
and still is. Alert VOLUME should not move materially (the score bar is unchanged); alert
COMPOSITION shifts toward liquid names. Watch: a labelled real EP falling out of the
shortlist · HIGH alerts halving vs the prior 30-day average · two consecutive silent days.
Every candidate + both orderings recorded per tick in `mi_ep_shortlist_shadow` (raw inputs
only), so the counterfactual stays measurable at $0.

**Reversion-flag**: NEW (the ordering had never changed since inception; the cap VALUE 20 is
unchanged, now named `ep_rubric.SHORTLIST_SIZE` + registered in
`scripts/gate_provenance_registry.py`). One revert flag: `ep_shortlist_prescore` runtime
toggle / `EP_SHORTLIST_PRESCORE_ENABLED` env, default ON — OFF restores gap ordering exactly
(~60s, no redeploy), pinned by `tests/test_ep_shortlist_prescore.py`.

**Status**: shipped — `ep_shortlist_prescore` / `EP_SHORTLIST_PRESCORE_ENABLED` confirmed ON
(code default, no DB override, env unset in both containers — prod read 2026-08-23). Field
validation still pending: `mi_ep_shortlist_shadow` holds 0 rows (no trading day has run since
this deployed — today is Sunday). Verify-live = rows for EVERY candidate (not just twenty) on
the next trading morning with `acting_key='prescore'`.

### 2026-08-22 — Near-miss band [50, 65) restored in the morning briefing, VISIBILITY ONLY (operator-directed) [#533 follow-on]

**Trigger**: the rescale below (same day) correctly removed the MODERATE *tier* and, as a side
effect, left `[50, 65)` completely silent — no row, no reason, no trace anywhere the operator
looks. Operator: *"we don't need separate alerts but we have a section for close but misses,
or moderates, can we put them there? I want them recorded in case we miss real EPs there."*
This is P1 in his own words elsewhere: a false exclusion that leaves no trace is invisible and
therefore uncatchable.

**Build**: the morning briefing's existing EP ALERTS section (`_format_ep_section`,
`agents/market_intelligence/briefing.py`) now renders a `👀 Near-miss (50-65, recorded only —
not tradeable)` block sourced from `mi_ep_scan_log` rows where `score_tier IS NULL` and
`50 ≤ ep_score < 65` (presented scale) — rows `ep_detector.py` already writes on every
score-based skip (`_scan_row`, the `continue` at the `ep_score < ep_threshold` check). No new
column, no new table, no new Telegram surface — a pure read of what was already being
recorded. Ticker/score/gap/catalyst per name, capped at 12/day with an overflow count; the
header gains an `N near-miss` count. The pre-existing generic 5-slot "Near misses:" catch-all
line is untouched except that it now excludes tickers already shown in the dedicated block
(no double-count).

**⚠ The trap this build does NOT fall into** (named in the rescale entry below): re-arming
`ep_rubric.resolve_moderate_cutline` to return `50` on the separation side would give these
candidates `score_tier="MODERATE"`, which would (a) re-arm the earnings-day MODERATE→HIGH
override — turning some near-misses into real HIGH alerts / ORB entries, a criteria change the
operator did not ask for — and (b) make them cross-strategy-allocator slot contenders. Neither
happened: `resolve_moderate_cutline(True)` is still `None`, unchanged. The near-miss band is
sourced entirely from rows where the tier decision is ALREADY TERMINAL (`score_tier IS NULL`,
written after the `continue`, before the override or the allocator ever run) — displaying them
cannot retroactively change that decision. Pinned by `tests/test_ep_near_miss_band.py`:
source-inspection pins on `run_ep_scan`'s ordering (skip-continue → tier assignment →
earnings-override, in that order, must not reorder), a boundary sweep of the real
`resolve_moderate_cutline`/skip-condition over the whole `[50, 65)` band proving `continue`
always fires, an end-to-end check through the real `_score_ep` with a gap≥10%/game_changer-
adjacent shape (the override's own trigger condition) landing in-band and still resolving to
`tier=None`, and briefing-level tests that the band never double-counts a real MODERATE/HIGH
row or a legacy-side alert.

**Volume — attempted a $0 measurement, result is INCONCLUSIVE, the 2.3/day figure stands.**
The rescale entry below cites "~2.3 names/day on the #533 corpus" with no saved derivation
(grepped `docs/analysis/` — nothing). First pass (`scripts/probes/_nearmiss_533followon_replay.py`):
pulled every candidate that reached `_score_ep` under the OLD/currently-live rubric in the
trailing 90 days (`mi_ep_scan_log`, last-seen row per ticker/day, 463 candidates over 61
trading days) and re-scored each through the REAL, currently-committed `_score_ep` +
`SCORE_WEIGHTS` (imported, never reimplemented), defaulting `float`/`vol_conviction`/
`theme_bonus`/`confidence_multiplier` to zero/1.0 (none of those inputs are in
`mi_ep_scan_log`): **≈1.4 near-miss names/day** (85/61). Initially read as a correction
(2.02/day HIGH replay landed near the rescale study's modeled 1.81/day, suggesting the
harness was sound) — **advisor review caught that this cross-check doesn't establish
faithfulness**: the omitted inputs are worth up to +25 presented points (theme +12.5, float
+6.25, vol_conviction +6.25, plus the ×1.2 agreement multiplier), against a band only 15
presented points wide, so a coincidental match on HIGH volume says nothing about the
near-miss band specifically.

**The actual faithfulness check** (`scripts/probes/_nearmiss_harness_faithfulness_check.py`):
replayed the same 463 candidates through `SCORE_WEIGHTS_LEGACY` + the per-regime bar (the
rubric that ACTUALLY produced each row's stored historical `ep_score`) and compared
row-by-row against that stored value. Result: **median diff −6.0, mean −5.0, only 27% within
±5 points, 51% under-scored by more than 5** — the harness systematically UNDER-scores
because the omitted inputs matter as much as the advisor flagged. That makes the missing-input
bias larger than the 1.4-vs-2.3 gap itself, in a non-monotone direction (missing points both
keep candidates out of `[50, 65)` from below AND keep them from crossing 65 into HIGH), so
**1.4/day is not reported as a correction of 2.3** — the honest read is "near-miss volume is
probably order 1–3/day, consistent with the cited ~2.3, not shown wrong." The 2.3/day figure
stands uncorrected; this paragraph exists so the next person doesn't re-trust the first-pass
1.4 number without re-running the faithfulness check.

**Does the band have data by 9:00 AM ET send time? Checked, yes.** The EP scan job runs every
5 minutes 7:00–10:00 AM ET (`scheduler.py::_ep_scan_job`); the morning briefing sends at a
fixed 9:00 AM ET (`CronTrigger(hour=9, minute=0, ...)`, `JOB_MORNING_BRIEFING`). Prod check
(trailing 15 trading days, read-only): scored rows (`ep_score IS NOT NULL`) start landing at
7:00–7:20 AM ET on 14 of 15 days, with 5–247 scored rows already recorded before 9:00 AM ET
on every one of those days; the one exception (2026-08-21) was a scan outage (2 scored rows
all day, first at 9:55 AM) unrelated to this change. The near-miss block will have real
candidates to show on ordinary trading days, not render empty by default.

**Reversion-flag**: none needed — this is a display-only read, not a scoring/tiering change,
so it carries no criteria risk and nothing to revert on `ep_score_separation`. On the legacy
side (`ep_score_separation` OFF) the band is always empty by construction: a legacy score in
`[50, 65)` already gets `score_tier="MODERATE"` via the pre-existing cutline-50/per-regime-bar
path (a REAL alert, shown in the main EP ALERTS list, untouched by this change) rather than a
scan_log skip row, so the two surfaces can never collide.

**Status**: shipped (commit `7218aadc`, an ancestor of the running prod checkout `8bcf6ff0` —
verified 2026-08-23). No toggle — display-only read, reversion-flag is "none needed" (above).
Field validation still pending: no trading day has run since deploy (today is Sunday).
Verify-live: first morning briefing with a sub-65 candidate shows the near-miss block;
`mi_ep_alerts` gets zero new `score_tier='MODERATE'` rows on the separation side (unchanged
from today).

### 2026-08-22 — RESCALE: the separation score presents as 1.25×raw+15, bar expressed as 65, dead 50 cutline removed (PRESENTATION ONLY — ALERTING SET PROVEN IDENTICAL) [#533]

**Trigger**: the separation change (below) fixed the ORDERING but broke the READABILITY: every
score fell, the bar had to drop to 40 — BELOW the legacy 50 cutline — leaving the bands
incoherent and the MODERATE band empty. Operator: *"the proper fix to make this make sense is
to increase score of EPs, lower score of non EPs and keep bar at reasonable level... maybe
that's just cosmetics, but it is easier to read and understand."* He reads these numbers on
his phone to judge alerts — a score whose bands mean nothing is a worse instrument even when
the filtering is right.

**Evidence**: this is a presentation change — the evidence burden is the PROOF THE ALERTING
SET CANNOT CHANGE, not new outcome data. (a) By construction: one strictly-increasing affine
transform (`presented = 1.25 × raw + 15`) applied to the FINAL score — after the conviction
floor (which forces raw pre-multiplier) and after the regime multiplier — with the bar mapped
through the same function (65 = T(40)); `s ≥ bar ⟺ T(s) ≥ T(bar)` for any strictly-increasing
T, floor-forced scores included. (b) By test (`tests/test_533_rescale_invariant.py`): decision
identical before/after on the 69-case boundary fixture, the 26 labelled real EPs × 3 grades ×
3 multipliers × 2 liquidity scenarios, a 2,700-shape input grid, and an exhaustive 0.1-step
sweep of the raw axis through the bar (1.25 = 5/4 is binary-exact: raw 39.9 → 64.9 skip,
40.0 → exactly 65.0 HIGH — no rounding flip). (c) Placement on the measured #533 corpus
(existing captures, $0): real EPs at known grades present ≈ 67-105 (alerting members 67.5 /
67.5 / 90 / 105), routine ordinary gappers ≈ 30-52 (median 40.5), scale floor 27.5. The
targeted "ordinary gappers in the 30s" holds for the routine-graded modal gapper; the
strong-graded half of the control mix presents in the 50s-low-60s BELOW the bar — that overlap
is the rubric's real resolution (within-day AUC 0.649), not a scale artifact, and no
order-preserving map can shrink it. The `50` cutline: mapped (T(50)=77.5, above the bar) and
removed are behaviourally IDENTICAL (band empty either way); removed is chosen because a
cutline above the bar is a dead number that misleads. Alert-volume consequence of removal:
ZERO — the band has been empty since the separation flip.

**Anticipated effect**: zero change to what alerts — same tickers, same days, same tiers
(HIGH volume, ordinary share, reachability all exactly as the separation entry priced). What
changes is every operator-facing number on the separation side: HIGH alerts read 65-115ish
instead of 40-72 (MRNA 105 Bull / 90 non-Bull), junk reads ~30s-40s, the bar is a round 65,
and skip reasons read `score N < bar 65` (the reason-string consumers in `missed_outcomes.py`,
`briefing.py`, `ep_selectivity_breakdowns.py`, `ep_latency_audit.py` were taught the new form;
bucket name `score_below_50` kept stable). `mi_ep_score_shadow.sep_score_*` is on the
presented scale from this change on — the row's own `sep_bar` column stamps the scale (40 =
pre-rescale raw rows, 65 = presented). `mi_ep_alerts.ep_score` likewise moves to the presented
scale on the separation side (scale changes at the deploy boundary, as it already did at the
separation flip). MODERATE band: none while the flag is ON (was already empty); reappears
intact on revert.

**Reversion-flag**: REFINEMENT of the 2026-08-22 separation change (numeric expression only —
no weight, tier cut, or raw threshold moved; `SEPARATION_BAR_RAW` stays 40). Rides the SAME
one revert flag: `ep_score_separation` OFF → `SCORE_WEIGHTS_LEGACY` has `output_scale: None`
(explicit override — the `{**SCORE_WEIGHTS}` spread would otherwise inherit the transform), so
flag OFF presents the old raw scale + 50 cutline + per-regime bars byte-identically — still
pinned by the 69-case stage-2 baseline (`tests/test_ep_score_stage2_refactor.py`, green).

**Status**: shipped (commit `ba664767`, an ancestor of the running prod checkout `8bcf6ff0` —
verified 2026-08-23), acting via the same `ep_score_separation` flag as the separation change
below (confirmed ON, code default, no override, env unset in both containers). Presentation
change with a proven-identical alerting set, no new operator sign-off sought on WHAT alerts
(nothing about that moved); the scale choice itself implements his quoted ask. Field
validation still pending: `mi_ep_score_shadow` holds 0 rows (no trading day has run since
deploy). Verify-live: first separation-side HIGH presents ≥65 with `sep_bar=65` in
`mi_ep_score_shadow`.

### 2026-08-22 — SEPARATION: flat gap credit + floors trimmed to branch 4 + uniform HIGH bar 40 (OPERATOR-SIGNED, ONE-FLAG REVERTIBLE) [#533]

**Trigger**: the operator's own frame, which produced the card: *"there's two parts to this
coin, real EP to score higher and non real EP to score lower, the combo will make lowering
the bar, or setting the bar anywhere more meaningful in terms of filtering properly."* The
separation study then measured where an ordinary gapper's HIGH score actually comes from:
**71% of it is payment for gap size** (30 raw points from the 25/20/15/10 ladder + 41 from
the conviction floors, both keyed on gap), and **93% of ordinary HIGHs needed a floor to
clear their bar**. On the priced result the operator signed: **"ok, let's go, similar to
before, we have fixing EPs so bias for action but keep tracking existing if we make
changes."**

**Evidence**: `docs/analysis/score_separation_533_2026-08-22.md` (+ the bar pricing in
`ep_threshold_rederivation_2026-08-22.md`) — 26-member #577 fixture vs the 1,100-row tier-A
gap corpus, all from existing captures, $0:
- Floor branches 1-3 bind on 28% of ordinary admissible gappers vs 8% of real EPs (mean lift
  +9.9 vs +2.1 pts) — only 3 of 25 members gap ≥15%, so those branches are structurally
  reserved for ordinary gappers. Gap ladder: AUC 0.34 on real EPs (runs backwards).
- The package (flat 10 + delete branches 1-3 + keep branch 4): within-day AUC 0.537 → 0.649;
  ordinary gappers scoring above the median real EP 62% → 38%. Each half alone buys ~+0.04;
  together +0.11 — points and floors are BOTH gap payment, one axis.
- **Bar 40 = the volume-neutral choice**: 1.78 modeled HIGH/day vs 1.81 today (about one
  FEWER alert a month) with **all 18 floor-alive real EPs reachable** at a top catalyst grade
  (vs 6 today). It is the ONLY setting that holds today's alert volume — and ONE number to
  change if the operator wants fewer alerts (45 cuts alerts ~55%, 50 cuts ~77%).
- ⚠ Caveats, stated honestly: the label is IN-SAMPLE (discovered on this data), 13 of 26
  members fall on one session, **only 7 of 26 were ever graded**; the reachable-@game_changer
  columns are CONTINGENT on the new catalyst lattice awarding the top grade (the bar buys the
  option, the grader exercises it); **the grade wall still holds QCOM and AMD at any score
  shape or bar** (routine-graded; no score change fixes the grader); and bar 40's ABSOLUTE
  volume rests on the relative anchor (the corpus omits $5-10 and sub-$50M-day names). Honest
  out-of-sample judge: the post-07-16 label window (~mid-October) + the live record below.

**Anticipated effect**: HIGH volume roughly unchanged (~-1 alert/month); the HIGH stream's
ordinary share drops ~97% → ~90%; real EPs stop being arithmetically excluded in non-Bull
regimes (today's Correcting bar 75 sits 10 points ABOVE a perfectly-graded real EP's ceiling);
MRNA-class (gap ≥10 + game_changer) keeps firing via the kept branch 4 (60 ×1.2 = 72). The
score<50 MODERATE cutline keeps its value and its MODERATE role (NOT ruled on) — but the HIGH
decision now runs FIRST, because the priced bar-40 policy counts 40-49 scores as HIGHs
(cutline-first would have silently shipped the bar-50 row, −77% alerts); with the legacy bars
(65-80) the ordering is byte-identical to the old code, so the revert is exact. While the flag
is ON the MODERATE briefing band is empty. Measured from day one by `mi_ep_score_shadow`
(below), not inferred.

**Reversion-flag**: NEW for the flat gap credit and the uniform bar; **REVERSAL of the
2026-03-20 conviction-floor design** (`77179405`/`63eda07a`: "a 20%+ game-changer gap should
score ≥70 on its own", 20%+strong→80) for branches 1-3. Why the prior reasoning was WRONG,
not just incomplete: it took the gap itself as evidence of institutional conviction — bigger
gap, more conviction, floor it above the bar. Measured against the labelled real-EP cohort
five months later, gap size points the OTHER way (real EPs are liquid names at moderate gaps;
the ≥15% region is 3 of 25 members vs 43% of ordinary admissible gappers) — the floors were
calibrated on the big gapper by design and manufactured an ordinary-only tail above every
bar. Branch 4 (10%+gc→60, `ed3e514e` 2026-04-14) is NOT part of that reversal: it was built
as the dead-zone fix FOR a real EP (BE) and is deliberately KEPT (deleting it gains 0.008 AUC
and re-kills MRNA at its 10% read — pinned by `tests/test_533_separation_flip.py`).
**Revert = ONE flag, default ON** (`ep_score_separation` runtime toggle /
`EP_SCORE_SEPARATION_ENABLED` env) — reverts ALL THREE parts together (ladder, floors, bar):
- Instant (≤60s, no redeploy): `INSERT INTO mi_safeguard_state (safeguard, account_mode,
  state, last_transition_at, updated_at) VALUES ('ep_score_separation', 'global', 'off',
  NOW(), NOW()) ON CONFLICT (safeguard, account_mode) DO UPDATE SET state = EXCLUDED.state,
  updated_at = NOW();`
- Permanent: `EP_SCORE_SEPARATION_ENABLED=false` in prod .env + redeploy market-agent.
Flag OFF → `ep_rubric.SCORE_WEIGHTS_LEGACY` (old ladder + all four floors) + the per-regime
bar act — byte-identical old behaviour, proven by the 69-case pre-change boundary sweep
(`tests/test_ep_score_stage2_refactor.py`, fixture captured from the true pre-change code)
+ the end-to-end pins in `tests/test_533_separation_flip.py`.
**"Keep tracking existing" (the operator's condition)**: every scored candidate writes BOTH
sides to `mi_ep_score_shadow` (`ep_score_shadow.py`, catalyst-tier-record pattern) — sep_*
= ALWAYS the separation side at bar 40, legacy_* = ALWAYS the old rubric at the per-regime
bar, and an explicit **`live_side`** column ('separation'/'legacy') stamps which side ACTED,
never inferred from dates. Both sides run through the same `_score_ep`, never a
reimplementation.

**Status**: shipped (commit `51d5200c`, an ancestor of the running prod checkout `8bcf6ff0` —
verified 2026-08-23) — `ep_score_separation` / `EP_SCORE_SEPARATION_ENABLED` confirmed ON
(code default, no DB override, env unset in both containers). Field validation against the
shadow record still pending: `mi_ep_score_shadow` holds 0 rows (no trading day has run since
deploy — today is Sunday). Known seam,
deliberate: display surfaces reading the STORED regime row's `ep_threshold` (briefing regime
line, agent.py why-no-alert prose, allocator's advisory `legacy_eligible` label) still show
the per-regime bar while the flag is ON — `regime.py` and stored rows untouched so the
revert side survives; alerting uses the flag-gated bar. Follow-up if the flag sticks: point
those displays at the acting bar.

### 2026-08-22 — Catalyst tier FLIPPED to the corrected lattice (OPERATOR-SIGNED, ONE-FLAG REVERTIBLE) [#533 Change 6]

**Trigger**: MRNA 2026-08-19 — the operator's canonical textbook EP — graded `strong` at 07:05
and was KILLED at score 21.6 on its 10% gap read; only a freak 33% gap print rescued it. The
clear was luck, not detection — a defect, not an experiment. Meanwhile the live top tier went to
42-44% of ordinary last-60d alerts (near-modal) while at most 1-2 of the 7 graded labelled real
EPs got it. Operator, rejecting the wait-for-October option: *"why wait so long? The premise is
that we got into MRNA by chance, so this is a bug we're fixing, can we do a negative test
instead i.e. flip now and revert when wrong, observe/compare with existing, and have a condition
to test if we're right or not and monitor."* Then, to the flip plan: **"go."**

**Evidence**: `docs/analysis/catalyst_tier_shadow_533_2026-08-22.md` — the shipped lattice
itself replayed (never a reimplementation) over all 264 stored live alerts + the 26-member #577
fixture, one read-only prod capture, $0: (a) MRNA re-tiers strong → game_changer on the
operator's own evidence (unscheduled + forward + 7 other Healthcare names on the day's board)
and clears HIGH at the REAL 07:05 read (72.0 ≥ 65) instead of surviving on the freak print;
(b) ordinary-alert `game_changer` rate 43% → 18% (last 60d; 42% → 19% within HIGHs) — the flip
TIGHTENS, so the risk is missed alerts, not bad ones; (c) the PEG class survives (17 of 52
scheduled GCs keep the top tier on beat+forward; strongs are never demoted); (d) alert volume
≈ neutral on replay (HIGH 187 → 185; +6 MOD→HIGH, −8 HIGH→MOD, −2 MOD→none over ~4 months).
⚠ **HONEST LIMIT: 4 of the 7 graded labelled real EPs (ARM / QCOM / AMD / UMC) are
UNDETERMINED offline** — they died below score 50, so no catalyst text was ever stored and the
routine-corrective cannot be evaluated on them at $0. We genuinely cannot predict the flip's
effect on that class; the monitor below IS the test for it (the negative-test design the
operator chose). Known instrument limits, disclosed not smoothed: the #568 keyword axes missed
INTC 04-24's beat on its truncated surviving text (demoted to strong, still HIGH via the
gap≥20 floor), and sector follow-through is beta-confounded on flood days (raw counts recorded
per row so the lane stays re-cuttable).

**Anticipated effect**: top-tier rate on ordinary alerts drops to ~14-19% (near the 11.6%
graded-candidate base rate — rare again instead of near-modal); scheduled recaps without
beat+forward lose 10 catalyst points (floors intact); MRNA-class strongs promote intraday as
the group repricing fills in (the shadow regrades every tick — the live grade changed intraday
on only 15 of 700 graded ticker-days); net alert volume roughly unchanged. Not fully
predictable: promotions among graded scan-only rows that never alerted (no stored text
offline) — bounded small, measured exactly by the recorder from day one.

**Reversion-flag**: NEW (first live change to tier ASSIGNMENT; the LLM tier definitions,
`_score_ep` weights, thresholds, floors and every filter are untouched underneath — the lattice
is a new one-step re-tier layer on top). **Revert = ONE flag, default ON**
(`catalyst_tier_lattice` runtime toggle / `CATALYST_TIER_LATTICE_ENABLED` env):
- Instant (≤60s, no redeploy): `INSERT INTO mi_safeguard_state (safeguard, account_mode,
  state, last_transition_at, updated_at) VALUES ('catalyst_tier_lattice', 'global', 'off',
  NOW(), NOW()) ON CONFLICT (safeguard, account_mode) DO UPDATE SET state = EXCLUDED.state,
  updated_at = NOW();`
- Permanent: `CATALYST_TIER_LATTICE_ENABLED=false` in prod .env + redeploy market-agent.
Scope lines, deliberate: `_post_grade_filters` still reads the RAW grade (the evaluation
covered only the post-filter pool — extending the flip into admission would LOOSEN
unevaluated); the catalyst cache keeps the raw grade (the lattice recomputes every tick).
Fail direction in code: any lattice error → the raw LLM grade acts that tick, logged loudly.
`mi_catalyst_tier_shadow` keeps recording BOTH sides with CONSTANT column semantics
(`live_quality_*` = raw LLM grade always, `shadow_tier_*` = lattice always) + a `live_side`
column ('llm'/'lattice', pre-flip rows backfilled 'llm') stamping which side ACTED — the
live-vs-old comparison continues uninterrupted and no reader infers the acting side from dates.

**Status**: shipped, awaiting field validation — under the NIGHTLY flip monitor
(`health_checks.run_catalyst_lattice_monitor`, wired into `_post_nightly_audit_job` 17:30 ET,
no new cron; stands down if the flag is reverted). Three revert triggers, any hit → Telegram
naming the trigger + the numbers + the exact revert SQL, plus an audit row: (a) **P1** — a
`tests/fixtures/must_not_miss_eps.py` member graded `routine` by the acting side (announced
once per member; the fixture now ships in the market image so this trigger cannot be silently
dark); (b) HIGH alerts **per stock that gapped** over the last 7 days fall >50% vs the prior 30
days (pooled over trading days, era-scoped to the flip); (c) two consecutive trading days with
zero EP alerts.

**Trigger (b) is measured against GAP SUPPLY, not against a flat baseline (2026-08-26).** It
false-fired twice in two days — 08-24 (`high_volume_drop`) blaming the flip for a fall that
began a week before it, and 08-25 (`zero_alert_days`). Operator: *"we are at the tail end of
earnings season, so gap-ups (and downs) shrink naturally"*, with the constraint that governs
the whole design: *"i don't want to make the assumption that more real EPs happen during
earnings season, just more gap ups (and downs) in general due to earnings, let's not conflate
the two, I don't have any data to say if there's similar effect on real EPs."* So the
denominator is the number of stocks whose OPEN gapped ≥10% above the prior close inside the
D-1 universe floors (prior close ≥ $5, prior-day volume ≥ 50k shares), counted per trading day
from `mi_daily_closes` — a fact we record. **Nothing encodes an expected EP rate, a seasonal
scale factor or a per-month threshold**; the trigger now asks only whether our CONVERSION of
available supply halved. The trigger kind is `high_conversion_drop` (renamed from
`high_volume_drop`, so an audit query cannot silently mix the two statistics).
- **Why that denominator survives the 2026-08-22 boundary**: the obvious one — candidates in
  `mi_ep_scan_log` — is not comparable across 08-22, because #570 made the two silent D-1
  universe floors log a row and the distinct-ticker count jumps ~18/day to ~222/day for that
  reason alone (213 of 222 rows on 08-24 are `filter:universe_prev_close_too_low`).
  `mi_daily_closes` is a different table written by a different job (nightly_data_pull 17:00
  ET), untouched by #570, complete on both sides. It is also OUTSIDE the funnel, so a break in
  the #489/#490 real-time admission layer cannot shrink numerator and denominator together and
  hide itself.
- **Backtest, 2026-07-30 → 2026-08-25** (real production series, era scoping switched off so
  every day is actually judged): the per-trading-day form fires 3× — 08-21, 08-24, 08-25 — and
  all three are false, the tape. The supply-normalised form fires **0×**. It is not a mute:
  on 08-24 it misses the bar by **one HIGH alert** (it fires at ≤6 in the recent week; we had
  7), and the same thin 08-18→08-24 tape with our alerts removed fires at a 100% conversion
  fall. Same answer for a 9% and a liquidity-filtered denominator, so the choice of yardstick
  is not load-bearing.
- **What it now misses**: any real break whose timing coincides with a supply fall of similar
  size — halve our conversion in a week the tape also halves and it stays silent. It is also
  silent whenever `mi_daily_closes` is too thin to measure (< 2,000 rows carrying an open
  price), rather than falling back to raw counts.
- **⚠ The 30-day prior window is still spike-inflated — on the CONVERSION axis now.**
  Supply-normalising removes the supply half of the early-August burst; the conversion half
  stays in the baseline (the burst weeks were elevated on both — collapse analysis Result 4).
  July converted 6.1 HIGH alerts per 100 gapping stocks; the prior window entering 08-28
  converts 11.6. **A return to exactly July-normal conversion clears the 50% bar by 2.6 points**
  — which is why 08-24 and 08-25 land one alert short. Consequence: on **2026-08-28**, the first
  day era-scoping lets trigger (b) speak (5 post-flip trading days), it fires unless roughly 6
  HIGH alerts arrive across 08-26→08-28, and the honest first reading of such a fire is
  spike-inflation, not a lattice break. The window shape (7 vs 30) is part of the signed trigger
  and was NOT touched — changing it is the operator's call.
- **What it structurally cannot answer**: whether the tape holds fewer real EPs or we got worse
  at finding them. That needs the EP rate per gapping stock, which the operator explicitly said
  we do not have. Conversion also moves on ANY funnel change — a signed change elsewhere (the
  extension cap 50%→75%, 08-22, sits inside the current prior window) would trip it while the
  message prints lattice revert SQL. And the two sides use different price bases: the
  denominator is open-vs-prior-close, the numerator is decided pre-market off live prices
  (07:00–09:55 ticks), so a systematic shift in pre-market-to-open fade — itself plausibly
  seasonal on a thin tape — moves conversion with no funnel change at all.
- **Trigger (c) is deliberately NOT supply-normalised.** Two silent days on a live money path
  is worth a look even when the cause turns out to be the tape. Its firing logic is unchanged;
  the message now carries each day's gap count and the trailing conversion rate as CONTEXT (not
  a forecast) so it can be dismissed at a glance.
- **#611 (2026-09-01) — the supply figure reconciled against `mi_ep_scan_log`, arithmetic
  unchanged, wording fixed.** The alert read "4 and 3 stocks gapping 10%+" for 09-01/08-31;
  counting distinct tickers in `mi_ep_scan_log` with a day-MAX `gap_pct >= 10` instead gives 42
  and 52. Traced end to end (read-only prod SELECTs): both counts are correct for what they
  measure, and they measure different things. Applying the SAME $5/50k floors to the naive
  scan-log count (using its own `prev_close`/`prev_day_volume`) drops 42 → 6 and 52 → 8 — most
  of the "10x" was un-floored penny/micro names. The rest is definitional: `mi_ep_scan_log.
  gap_pct` is `(current_price - prev_close)/prev_close` re-computed on EVERY scan tick, so its
  day-max is the ticker's PEAK pre-market/scan-window reading, not the settled opening print —
  the exact price-basis split already noted above ("the two sides use different price bases").
  Of the 6/8 floor-passers, only the ones whose SETTLED OPEN (`mi_daily_closes`) actually
  gapped ≥10% survive: WETO/YEXT/PXS/GDXD (4) and WETO/MOVE/SAIC (3) — reproducing the alert
  exactly (PRLD peaked +12.3% intraday but opened -0.9%; CRK peaked +10.5% but opened +9.6%).
  **Nothing about the trigger, the flip, or any threshold changed** — the operator-facing
  message now says "opened X%+ above the prior close" and spells out the $5/50k floors inline
  instead of the ambiguous "stocks gapping X%+ past the universe floors", so a future reader
  cannot substitute the scan log's per-tick reading for this measure again. Pinned in
  `tests/test_611_supply_reconciliation.py`.

### 2026-08-19 — `MIN_GAP_PCT`: 10.0% → 9.0% (OPERATOR-SIGNED, REVERSAL of 2026-05-17 R2)

**Trigger**: `tests/fixtures/must_not_miss_eps.py` (#577) found 15 of 25 evidence-sourced tradeable
≥10R winners (`docs/analysis/winner_r_available_2026-08-16.txt`, GEOMETRY 1) are excluded TODAY by
the 10.0% floor — a false EXCLUSION, the error P1 (`docs/roadmap/ep_profitability_program.md` §
THE PRINCIPLES) says must never happen silently. Operator: *"loosen to what though?"* Priced in
`docs/analysis/gap_floor_decision_table_2026-08-19.md` (749 tier-A gap days, $0, all pre-existing
captures or one-shot read-only prod pulls). Operator, on being shown the table: *"ok, let's take 9
for now."*

**Evidence** (N≥10 met — 749 gap-days, 15 winners in the excluded band): 9.0% recovers 8 of the 15
excluded ≥10R winners (MU 49R, MRVL 35R, SNOW 25R, BE 16R, ALGM 23R, AMKR 20R, UMC 18R, USAR 16R)
for +6-8 candidates/day (≈+25% of daily volume); pool ≥10R density improves 2.0% → 3.0%. 8.0% would
recover all 15 at +18-23/day (density 3.3%) — he chose the smaller option deliberately. 8.5% was
rejected: 56 extra gap-days over 9.0 buy exactly 1 more winner (the band's middle is hollow; winners
cluster at 8.0-8.4% and 9.5-9.9%, not evenly). ⚠ Honest margin: AMKR clears by 0.03pp (9.03% vs the
9.0% floor, on the fixture's session-open psv basis) — one of the 8 is basis-marginal, not a clean
clear like the other 7.

**Why the prior reasoning (2026-05-17 R2, ADR 0003 §3) was WRONG, not merely incomplete**: R2 lifted
8.0→10.0 on a **win-rate read of 8 trades** — the 8-10% gap bucket showed 0/8 (0%) win rate over a
60d cohort. That read predates P3 (`ep_profitability_program.md`, operator 2026-08-16: *"we need to
remember EPs are rare and winrate is low… if we hit a real EP we gain 10X, that's the distinction
here"* — "a median cannot see a 10x"). A 0%-win-rate read is structurally blind to the tail: on this
exact excluded 8-10% band, **337R of R-available sits below the 10% line, against 174R in today's
entire ≥10% pool** — two-thirds of the programme's own ≥10R tail was sitting under a line drawn on
eight losers, because win-rate arithmetic cannot see that a bucket can lose 8 small bets and still
carry the biggest winners. The bucket wasn't mis-measured in 2026-05-17; the measure itself (win
rate, pre-P3) was the wrong instrument for a rare/fat-tailed setup.

**Regime interaction — explicitly checked, NOT changed**: ADR 0003 §3's Phase-1 recommendation read
"lift floor to 10% (or 12% in elevated regimes)". That regime-dependent variant was **never built**
— grepped `ep_detector.py` + `regime.py`: `MIN_GAP_PCT` has always been one flat module-level
constant with no regime branch (confirmed 2026-08-19). The only elevated-regime-flavored number in
the file is `ep_threshold` (the HIGH-tier SCORE cutoff, `regime.py`: Bull=65 / Choppy=70 /
Correcting=75 / Crisis=80) — a completely separate gate, untouched by this change. Nothing to
preserve or migrate; there was no regime behavior on the gap floor to begin with.

**What did NOT change (THE LINE — operator ruled the value, nothing else)**: the R6 pm-shares
carve-out (`gap_pct ≥ 10% AND catalyst_quality == "strong"`, 2026-05-17 P2.1b) — a separately-signed
criterion that coincidentally shares the old 10% number; the "routine + low gap" post-grade filter
(`catalyst_quality == "routine" AND gap_pct < 12%`); the earnings-day MODERATE→HIGH override
(`gap_pct ≥ 10% AND is_earnings_day`); and the `_score_ep` gap-magnitude scoring tiers (8/10/15/20%
point bands). All four independently hardcode a number near the old floor but are distinct,
previously-signed gates — left untouched per the operator's exact instruction.

**Anticipated effect**: universe admission recovers 8 of the 15 named winners (gains a scan row/
trace — not a guaranteed alert; the top-20 gap cap and score<50 gate still stand downstream, per the
decision table §4). Live candidate volume: +6-8 names/day (≈+25%). The RT Pass-2 superset/floor
re-application (`_pass1_gap_floor`, `_apply_realtime_pass2`) and the entry-time re-check
(`entry_pipeline.check_rt_gap_floor`, wired via `live_tracker._MAGNA53_MIN_GAP_PCT`) both read the
same `MIN_GAP_PCT` constant, so they move to 9.0% automatically — no separate wiring change needed
or made.

**Reversion-flag**: REVERSAL of 2026-05-17 R2 (8.0→10.0). Env override for fast rollback:
`EP_MIN_GAP_PCT=10.0` (or any value) — no redeploy for an emergency revert to the constant; a true
revert of this decision also means re-adding the 8 tickers above to
`tests/fixtures/must_not_miss_eps.py::BASELINE_DEBT`.

**Status**: shipped 2026-08-19 (operator-signed), code + SSoT + fixture in the same commit. NOT
deployed — left in-tree per instruction (CLAUDE.md: agent commits, operator deploys). Verify-live at
deploy: first day's `mi_ep_scan_log` gap-candidate count should read ~6-8 higher; `/audit` or a
direct query for any of the 8 named tickers on a future analogous gap should show a scan row instead
of no trace.

### 2026-08-16 — Protective stop moves to entry − 2R at half size; the +2R target does NOT move (OPERATOR-SIGNED, THE LINE)

**Trigger**: the EP profitability program's stop-fork analysis
(`docs/roadmap/ep_profitability_program.md` §0c/§0c-pre, 2026-08-16). The live cohort's shape —
0 winners in 17, 10 of 12 losses at ≈ full −1R, median adverse excursion while held **−1.97R** —
says the ORB-low stop sits INSIDE the normal noise path of a working EP. The operator described the
bounded rule; §0c-pre simulated it as an actual arm (correcting the earlier error of quoting the
no-stop arm's number for it) and he signed it 2026-08-16.

**The change, exactly as signed:**
1. **Stop**: ORB low → **`entry − 2R`**, `R = entry − ORB_low` (so `new_stop = 2·ORB_low − ORB_high`).
   The ORB low still DEFINES R; it is no longer the exit.
2. **Size halves — via the existing formula, NOT a second multiplier.**
   `prepare_orb_order` already computes `shares = risk_dollars / (entry − stop)`; doubling the stop
   distance halves the share count by itself, leaving **dollar risk per trade unchanged**
   (`risk_dollars` still = equity × risk_pct = the dollar loss if the stop fills). An explicit
   halving on top would QUARTER the position — checked for and absent, pinned by
   `test_size_halves_via_the_formula_no_second_halving`.
3. 🔴 **The profit target does NOT move.** 1/3 still comes off at the ORIGINAL
   `entry + 2·(entry − ORB_low)` price. `scan_profit_triggers` previously framed the target off
   `entry − hard_stop` — with the new stop that silently becomes **+4R**, never tested, never
   approved. The frame is now `order_manager.profit_target_r_per_share`: ORB-based
   (`entry − orb_low`) for magna53, `entry − stop` for every other strategy (9M Day 2's
   prior-day-low stop IS its R — leaking the ORB frame there would rewrite ANOTHER strategy's
   target, the #490 latent-defect class). A magna53 row with no usable `orb_low` SKIPS the trigger
   loudly rather than fire at a fabricated level (ADR 0014). Pre-change open rows have
   `stop == orb_low`, so both frames agree — in-flight trades see a byte-identical target at flip.
4. **Breakeven-after-partial, the SMA trail, and `update_stop`'s raise-only broker floor are
   UNTOUCHED** (no diff in `exit_logic.py`, `live_tracker.py` daily pass, `update_stop`,
   `execute_partial_exit` breakeven = `max(stop, entry)` — which equals `entry` under either stop).

**Evidence** (r1 — N≥10; cited from §0c-pre, not re-derived): **matched 43 reconstructed HIGH
trades, identical rows, equal dollar risk** — live ORB-low stop **SUM −6.0R, median −1.00** vs
**2R stop at half size SUM +11.4R, median +0.33**. 3R at a third size: +12.2 sum but lower median
and max → **2R chosen**. The median going positive is the mechanism: a 2R-wide stop simply is not
hit as often, so most trades stop being full losers. **Limits, verbatim from the analysis:** one
regime (April–May 2026), reconstructed not lived, slippage and auction fills unmodelled, **no
out-of-sample until `mi_exit_path_shadow` accrues (review gated at 20 closed positions, ~early
October)** — that shadow frames R off `orb_low` FIRST (`stop_ref`), so its record stays in ORB-R
units across this change.

**Anticipated effect**: the median live trade stops printing an automatic −1.00R; stop-out
frequency falls; share counts halve; dollar risk per trade, alert volume, and admission are
unchanged. The +2R partial fires at the same prices as before.

**What was verified UNCHANGED** (each read in code, not assumed): entry trigger (stop-limit buy at
ORB high) + `stop_limit_buy_price` formula · `stop_too_wide` (`validate_orb_entry`, ORB range vs
1.5×ATR — judges ORB geometry, which did not move) · chase cap (`CHASE_RISK_INFLATION_CAP` —
formula untouched; its planned-risk denominator is now the 2R distance, so the DOLLAR risk it
admits at the cap, planned $risk × 1.5, is identical to before) · gap floor `check_rt_gap_floor` ·
ORB window/cleanup · OCO carve-out #566 + partial accounting #567 (consume `limit_price`/stop from
the row — upstream pin covers them) · all safeguards (max positions, daily loss, drawdown breaker,
circuit breaker, PDT) · 9M Day 2 builder (`prepare_prior_day_low_orb_order`) untouched.

**Downstream stop==ORB-low assumptions found and handled:** (a) `scan_profit_triggers` — THE
dangerous one, fixed above; (b) `/positions` pending-entry render (`agent.py`) displayed
`orb_low` as the stop — now prefers `stop_price` (orb_low kept as legacy-row fallback);
(c) telemetry R units: `mi_sell_discipline_records` / `pivot_stop_shadow` / `giveback_shadow`
define R = `entry − hard_stop` (actual placed risk) → their R for NEW trades is in 2R-stop units
(≈ half the old numeric R for the same move) — deliberate, their stated definition is "actual
initial stop"; `kill_scale_bands` (R = pnl/risk_dollars) and `mgmt_judge` (already
`entry − orb_low` by design) are unit-stable; `describe_stop_move`'s "x.xR beyond breakeven"
Telegram line now reads in placed-stop units (display only). (d) The 5-min shadow ORB variant
(`shadow_orb_tracker`) imports `prepare_orb_order` and inherits the change — correct, it is
defined as apples-to-apples with live. (e) The offline EOD sim (`backtester/tracker.py`,
`mi_paper_trades`) keeps its own old-rule stop — offline lane, out of the signed scope, flagged
here so its divergence is known.

**Reversion-flag**: **REVERSAL** of the founding ORB-low stop rule (operator's own
`EP_TRADING_RULES.md` §B, 2026-03-27; this SSoT's definition since birth 2026-05-07). Per
CHANGE_PROCESS r4, the prior reasoning was WRONG for this cohort, not merely incomplete: it treated
a touch of the ORB low as the setup's invalidation, but the measured excursion distribution says
otherwise — the median trade goes −1.97R against while held, and the 11 of 43 names that dipped
past −2R still summed +13.9R in outcomes. At −1R nothing is yet decided; the old stop was
exiting inside noise. Hard revert = restore `stop_loss_price = orb_low` in `prepare_orb_order`
(the `risk_per_share` line then restores full size by the same formula) + drop the
`profit_target_r_per_share` frame in `scan_profit_triggers` (back to `entry − stop`) + redeploy
market-agent + execution. No toggle — a stop level cannot ship dark; the reversion is a code
revert, which is why the SSoT + tests pin every half of it.

**Status**: **LIVE — deployed and verified 2026-08-16** (operator-signed; commit `561a8c6f`,
"the stop change went live"; no toggle exists for a stop level, so deploy IS the flip). Two of
the three verify-live layers confirmed on real trades (prod read 2026-08-23), the third
partially: (1) placed stop — AMLX 2026-08-18 (ORB H=30.07 L=28.58 → 2R stop 27.09,
`hard_stop`=27.09), MRNA 2026-08-19 (H=120.15 L=115 → 2R stop 109.85, `hard_stop`=109.85), MRVL
2026-08-19 (H=241.53 L=235.84 → 2R stop 230.15, `hard_stop`=230.15) — all three match
`2·ORB_low − ORB_high` exactly; (2) the +2R target frame — the two real `profit_trigger_fired`
fires since 08-16 (`mi_audit_log`) both match `entry + 2·(entry − orb_low)` exactly (AMLX
target $33.473657 = 30.211219 + 2·(30.211219−28.58); MRNA target $132.25 = 120.75 +
2·(120.75−115)) — **not** the +4R a stop-anchored frame would silently produce; (3) breakeven
CONFIRMED, trail NOT YET exercised — both AMLX and MRNA show `breakeven_active=true` with
`stop_price == entry_price` exactly, matching `max(stop, entry) = entry`, but both are still
`status=filled` (open), so the SMA10/20 trail has not engaged on any post-08-16 trade yet —
that piece of (3) stays outstanding until one closes. Tests: `tests/test_2r_stop_change.py` (14,
behavioural), 7 mutations each reddening their named test (recorded per docstring); full suite
green.

### 2026-08-08 — #516: a keyword match may no longer overrule a contrary classification (OPERATOR-SIGNED)

**Ruling:** he judged 8 M&A suppressions across #514 and 2026-08-08. **7 were false positives**
(WEN, UMAC, LCID, FRMI, SOUN, LII, SCZM); **1 was correct** (CLRO). On the last four: *"none of
these are MA."*

**Change:** in `ma_filter.is_likely_ma`, when `catalyst_quality` is present AND is not `'mna'`,
the keyword-scan path is skipped. Our own graded view is no longer overridden by a bare word
match.

**Why this and not the obvious rule.** The obvious fix — *require the classifier to concur* —
would have released **CLRO, the one correct suppression**: CLRO was killed at the `9m_intraday`
detector before grading ran, so it has **no classification at all**. This guard only fires on a
CONTRARY verdict, so a name with no verdict is untouched. That distinction is the design.

**Measured over 73 fires / 60 days:** 28 (classifier agrees) stay suppressed · 27 (no
classification) unaffected · **18 released**. Of the released, the 4 he ruled are confirmed false
positives.

**The case that decided the binding-phrase question.** A prior test asserted that binding wording
should override a `routine` classification. **UMAC disproves it in production:** matched keyword
**"definitive agreement"** — the most binding phrase there is — while the real catalyst was
**Russell 2000 index inclusion plus a drone-sector tailwind**. The classifier said `routine` and
was right. That test is inverted, with the reason recorded in it.

**The safety net:** a veto FALLS THROUGH to the `polygon_news` check, which is deliberately NOT
gated. A genuine deal carrying a real headline still suppresses there. The keyword path simply
may no longer be the sole basis for overriding our own graded view.

⚠ **NOT FIXED, and PARKED by the operator (*"I don't know enough to make a call here yet"*):**
`polygon_news` fired on WEN ×5, LCID ×2 and FRMI — all with **no stored classification and no
stored news summary**. It is simultaneously the worst-performing path and the only one that keeps
no evidence of why it fired, which is why FRMI is unjudgeable after the fact. Separate decision.

**Telemetry:** `mna_keyword_vetoed_by_classifier` is written ONLY when the veto actually changed
the outcome, so the row count is a direct measure of the rule's effect. Isolated in its own
try/except — telemetry can never alter the verdict.

Tests: `tests/test_ma_keyword_veto_516.py` (7), mutation-checked against broadening the rule to
"require concurrence" (which correctly fails the CLRO test) and against removing it entirely.

### 2026-08-07 — #541: the entry trigger is now ASK-aware, not last-trade-aware (OPERATOR-SIGNED, LIVE)

**Trigger**: two live entries killed by the venue in single-digit milliseconds, two days running.

| date | ticker | ORB high (trigger) | last trade | ASK | venue verdict |
|---|---|---|---|---|---|
| 08-06 | INSM | 129.41 | 128.674 | **129.48** | `[6098] Stop Price Already Triggered` |
| 08-07 | QNST | 19.80 | 19.50 | **19.83** | `Unsolicited: Bad Stop 19.8` |

**Root cause**: a buy-stop placed at or below the current OFFER is immediately marketable, so it
is not a stop, and the venue refuses it. `#500`'s price-aware entry guard already owns exactly
this question — *"has price already run past the ORB high, so the trigger would be
in-the-money?"* — but it answered using `get_latest_trade`. On a thin first-minute gapper the last
trade and the offer diverge badly: both names read "not through" on trades and "already through"
on the ask.

⚠ **This is why three months of paper probes never reproduced it.** Paper fills against a synthetic
book with a tight spread; the live failure needs a WIDE ASK, which is what a thin gapper has in its
first minute and what paper does not model. The 08-06 probe deliberately tested the
trigger-already-printed shape on paper and saw it ACCEPTED — a false clear.

**Change**: `_pick_entry` now ALSO switches to the limit-buy fallback when `ask > orb_high`, at
`ask * 1.002`. New `alpaca_client.get_latest_quote` (SIP feed, same discipline as
`get_latest_trade`; a zero/absent ask returns None rather than 0.0, so a broken quote can never
read as a cheap offer).

**Not a new entry rule** — this is `#500`'s signed mechanism given the price reference the venue
actually uses. The trigger LEVEL is unchanged (the ORB high), the protective stop is unchanged (the
ORB low), and sizing is unchanged (planned risk).

**Bounded by the existing chase cap**, recomputed on the two real orders: QNST fallback $19.87 =
**1.12x** planned risk; INSM $129.74 = **1.10x**. `CHASE_RISK_INFLATION_CAP` is 1.5x, so both are
comfortably inside and an outsized chase is still refused.

**Evidence**: n=2, both first-minute gappers, both measured from the SIP NBBO at the exact
submission timestamp plus Alpaca's own event-stream reason. ⚠ **Honest limit — the RATE is not
measured**: how often the ask sits through the trigger on setups NOT worth taking is unknown, and
was offered to the operator as a pre-ship measurement. He ruled to ship without it, on the basis
that the alternative is a known-zero (the order is cancelled and we get nothing either way).

**Ship**: shipped behind `mi_safeguard_state('entry_ask_aware', <mode>)`, DEFAULT OFF, then flipped
ON for `live` by the operator on 2026-08-07 ("deploy and live now"). Fails CLOSED on an unreadable
flag or quote. 7 tests incl. a premise test that fails if the trade-vs-ask divergence ever stops
being the discriminator. Reversible with one row, no redeploy.

**Cost of NOT doing it, measured**: INSM ran +33% intraday; QNST posted record revenue +43% YoY and
net income +496%. Both entries were lost to a mechanism, not to judgement.


### 2026-08-02 — #490: real-time admission requires the level to SUSTAIN 3 bars (BUILT OFF, operator-signed)

**Trigger**: operator 2026-08-02 — *"target should be stable, in fact just a single 1min bar touching
>10% may be too lose especially for premarket, maybe we should see that move sustain with a few
bars."* Prompted by two cases he read himself: **MYGN 07-30** (*"I don't see >10% except for on
specific 1min bar and it crashed back down immediately… next day it dropped 46%"*) and **QURE 07-29**
(touched 12.3% inside the 09:30 bar, closed it at 9.7%, decayed all morning).

**The argument is a priori, NOT the backtest.** A level that holds three consecutive minutes is a
LEVEL; a level touched once and gone is a PRINT. This is the reasoning already embedded in the Q3
print-corroboration guard, applied one level up — Q3 asks *is this print real*, this asks *is this
LEVEL real*. ⚠ **The operator named the central risk himself — *"this is selecting criteria based on
hindsight of wins"*** — so the outcome table below is used ONLY as a safety check that nothing
valuable is destroyed, never to select the rule.

**Evidence** (r1: N≥10; we have 97) — `scripts/probes/_490_sustain_rule.py` over all 97
`ep_rt_universe_catch` events:

| rule | admits | med open→close | med open→high | med open→low | win ≥+5% |
|---|---|---|---|---|---|
| 1 bar (today) | 81 | +3.9% | +9.8% | −1.7% | 41% |
| 2 consecutive | 67 | +4.0% | +10.0% | −1.7% | 45% |
| **3 consecutive (SIGNED)** | **46** | **+5.0%** | **+10.4%** | **−1.2%** | **50%** |
| 3 of last 5 | 50 | +4.1% | +10.0% | −1.4% | 48% |
| 7 of last 10 | 10 | +0.2% | +5.9% | −2.8% | 20% |

Two signs it is not curve-fit: **it reverses** (7-of-10 is worse than doing nothing — a fitted curve
would be monotone), and **risk improves with return** (median open→low −1.7% → −1.2%), the opposite
of what fitting to wins usually buys. **M-of-N was tested as the operator asked and is NOT used** —
consecutive beats it at equal strictness.

⚠ **I recommended N=2; the operator signed N=3.** Recorded as his call. My argument was overfit
exposure — 3 is the argmax of the table and drops 10 good names incl. RACC (+31%) vs 3 for N=2.

**Anticipated effect**: roughly 57% of today's real-time catches survive. **This changes DETECTION
only** — operator ruling the same day, *"once open we are trading 1-min bars as per today"*: the
09:31 ORB entry mechanics are untouched.

**Implementation**: `_sustain_ok` (pure predicate) + a gate at the would-be-catch in
`_apply_rt_universe_overlay`, evaluated BEFORE the catch is logged (test-pinned — after would make
it cosmetic). Bars come from a new `collector.get_alpaca_minute_closes`, batched, memoised per tick,
on the tiny would-be-catch set (~0-3 symbols/tick). **BACKWARD-looking only** — a forward wait would
push detection past the 09:45 ORB cutoff and recreate the miss #490 exists to remove.

⚠ **FAILS OPEN on an undecidable verdict, and this is the load-bearing property.** No bars, too few
bars, a fetch error, or the toggle off ⇒ today's behaviour. Pre-market bars are genuinely sparse
(SCL had no 09:30 bar at all); converting "no data" into "reject" would silently become "reject
everything pre-market" — a far bigger change than the one signed. **Mutation-tested**: making sparse
bars reject fails 2 tests. Both rejects and undecidables are logged BY NAME
(`ep_rt_sustain_reject` / `ep_rt_sustain_undecidable`) so "the rule is on" cannot look identical to
"the rule never had data" — the exact instrumentation trap that made gate 1 unanswerable.

**Reversion-flag**: NEW. Reversion = `ep_rt_sustain_enabled` off (~60s, no deploy).

**Status**: **LIVE — operator signed the flip 2026-08-02 09:53 ET** (*"flip it now, it's more
conservative regardless"*). Shipped OFF, verified inert in both containers, then flipped; both
confirmed reading `True`.

⚠ **Its BLAST RADIUS today is telemetry, not trading, and that should not be misread as "it works".**
`ep_rt_universe_authoritative` and `ep_rt_gap_authoritative` are both still **False**, so a
universe catch is SHADOW — logged, never admitted. The sustain rule therefore changes *which shadow
catches get recorded*, and pre-filters the cohort so that when RT-3 is eventually flipped the
admission set is already correct. **It cannot affect a live trade while the authority toggles are
off.**

**The operator's reasoning is structurally correct**: the gate can only `continue` — it removes
would-be catches and can never admit one. There is no path by which it loosens detection.

15 tests. **Reversion**: `ep_rt_sustain_enabled` off, ~60s, no deploy.

**Watch for** (pre-committed): first 30 live catches vs the replay's prediction — materially worse
means the replay was fitted, revert; a rejected name running ≥+20% once is a review, twice a revert. ⚠ **THE ≥+20% ARM WAS SUPERSEDED 2026-08-28 (operator-signed) — see the change-log entry at the top of this file. It named no baseline, no denominator and no window, which made it unfalsifiable; it is now a 10% rate on TRADEABLE misses over 30 trading days with a ≥30 minimum, and it raises a REVIEW rather than reverting. Do not cite the form below as live.**

⚠ **READ 2026-08-24 — the ≥+20% arm is LITERALLY MET (20 names) AND THE READING IS AN ARTIFACT.
Do NOT revert on it. Operator ruling pending (#593).** The condition never named a BASELINE, so it
was measured from the day's OPEN — and a name that faded pre-market opens depressed, so the fade
manufactures the +20% it is then charged with. 17 of the 20 breaches are that artifact; only 3 names
held the gap floor and ran, and all 3 were caught or killed elsewhere (DCTH alerted via the delayed
path; AVAH and MATV died on the score floor and the top-20 cap). Measured cost of this rule over 16
trading days: **zero names**. 88% of what it declined had already faded below the gap floor by the
opening bell — pre-market prints, not levels, which is exactly what the rule exists to catch.
▶ **The correction, pending his sign-off: measure the run from the PRE-MARKET LEVEL THE RULE
DECLINED, not from the open** — that is where we would have been positioned, and a name that fades
and recovers to it made us nothing. ⚖ Tightening a revert condition makes a safety net LESS likely
to fire, so it is his call and not a doc tidy-up. Evidence: `docs/analysis/sustain_rule_cost_2026-08-24.md`.


### 2026-08-01 — #490: MIN_GAP_PCT now enforced at SUBMISSION, not only at the scan tick (BUG FIX; built OFF)

**Trigger — operator ruling, 2026-08-01**: *"the blocking live path is in fact correct given the
price retreated from the 10% gap, so in a way the current path is a bug."*

**This is a bug fix, not a criteria change, and the distinction is the whole point.** `MIN_GAP_PCT =
10.0` is an existing signed criterion (2026-05-17 R2). `live_tracker.process_new_alerts_live` selects
`FROM mi_ep_alerts WHERE alert_date = $1 AND score_tier = 'HIGH'` — **the alert ROW, written on
whichever scan tick first scored it, often hours before the open** — and submits at 09:31 without
ever re-reading price. A name that retreated below the floor in between was entered **in violation of
the system's own criterion.** Nothing about the 10% threshold is being changed here; it is being
applied at the moment the money moves.

⚠ **I initially framed this as a new filter needing CHANGE_PROCESS r1's N≥10 before it could ship.
That was the wrong standard** — r1 governs *threshold changes*. There is no threshold change here.

**Evidence** (`docs/analysis/490_delay_missed_eps_2026-08-01.md`): FTNT 2026-07-30 — alert written
07:00 on a stale 10.79% gap; at **09:30:05, one minute before entry, the system logged its real-time
gap at 7.77%** — and entered anyway, for −$6.63. All three names that faded below the floor before
entry (WKC −$23.80, QBTS −$22.26, FTNT −$6.63) lost money. A gap that retreats before the open is the
setup failing its own premise, which is what the criterion exists to catch.

**Implementation**: `entry_pipeline.check_rt_gap_floor`, called as stage 4b — beside the fade guard
(same class of gate: setup quality read off live price) and BEFORE sizing and submission. Denominator
is `db.get_prev_close` reading `mi_daily_closes`, i.e. the **same Polygon prev_close the detector
uses as its sole denominator**, so the scan and this guard cannot disagree about one name on one day.
(`mi_ep_alerts` has no prev_close column — an earlier draft read `alert_context["prev_close"]`, which
does not exist, and would have silently failed open and done nothing.)

**FAIL OPEN, deliberately.** It blocks ONLY on a positive, trustworthy real-time read below the
floor. Toggle off, no prev bar, no/zero/negative last trade, or ANY exception → the entry proceeds
exactly as today. Same posture as `check_fade_guard`'s silent-on-data-failure rule: on a guard that
can only remove entries, a failure that blocks is far worse than one that lets a marginal trade
through. `tests/test_490_entry_gap_recheck.py` pins both invariants (21 tests incl. the floor
boundary — at exactly 10.00% it must PASS, not block). **Mutation-tested**: making it fail closed
fails 3 tests.

New skip reason `setup:gap_below_floor`, rendered via `humanize()` (test-pinned) so the machine
prefix never reaches Telegram.

**Reversion-flag**: NEW. Reversion = set `ep_rt_entry_gap_recheck` off — ~60s, no deploy.

**Status**: **LIVE — operator SIGNED OFF 2026-08-01 ("yes"), flipped 20:34 ET.**

Shipped OFF, verified inert in both containers, THEN flipped. Deployed `market-agent` → `execution`
(both green).

**Prod proof the guard is not a silent no-op** (run in-container after the flip, on real data):
```
apollo-execution:
  FTNT -> BLOCK: setup:gap_below_floor: rt 5.6% < 10% floor
          (alert said 10.8%, last $161.80 vs prev close $153.22)
```
FTNT's actual 7/30 entry was $166.65 against a $153.22 prev close = **8.8%, below the floor** — the
entry we should not have taken.

⚠ **The guard only ACTS on apollo-execution, and that is where entries run** (`EXECUTION_MODE=http`,
so `trigger_orb_entry` POSTs there — *"creds + broker live in execution"*). On apollo-market the same
call **fails open**, because that container's Alpaca credentials are deliberately blanked (creds
isolation). That is the designed direction, but it means **if `EXECUTION_MODE` were ever set back to
`inprocess`, this guard would silently stop working** rather than fail loudly. Worth knowing before
anyone touches that env var.

**Reversion**: set `ep_rt_entry_gap_recheck` to `'off'` — ~60s, no deploy.

⚠ **CORRECTED same evening (found by the `/simplify` pass, two reviewers independently): the guard
originally baked MAGNA53's floor into a SHARED pipeline stage.** `submit_trade_entry` is the single
funnel for MAGNA53 **and** 9M Day 2, and `check_rt_gap_floor` imported `ep_detector.MIN_GAP_PCT`
(10%) directly — so it would have applied MAGNA53's criterion to 9M Day 2, whose own signed bar is
**3% gap OR 4% intraday gain** (`ninem_detector._MIN_GAP_PCT`). That is rewriting another strategy's
entry discipline: THE LINE.

**Live exposure was ZERO and that was luck, not design** — 9M Day 2 is `phase=deprecated`, and the
phase gate (`entry_pipeline.py:481`) runs BEFORE stage 4b (line 544), so it never reached the guard.
Both reviewers predicted live 9M skips on Monday; verified against `mi_strategies` and the call
order, that prediction is wrong. The defect was LATENT — it would have fired the moment 9M Day 2 was
ever re-enabled.

**Fix**: the floor is now a per-strategy PARAMETER (`rt_gap_floor_pct`, default `None` = opt out),
exactly the idiom `check_fade_guard` already uses for `ratio`. MAGNA53 opts in at its own 10% from
`live_tracker.py`; 9M Day 2 does not. A test asserts the shared funnel no longer imports any one
strategy's constant, and another asserts the same price blocks at 10% and passes at 3%.

**Verify-live due Monday 2026-08-03**, and the reversion trigger is pre-committed:
1. Expect `setup:gap_below_floor` skips ONLY on names whose real-time gap is genuinely under 10% —
   spot-check each against `mi_daily_closes` prev close.
2. ⚠ **Revert trigger — needs an ABSOLUTE FLOOR before the ratio is allowed to mean anything:
   revert only if `HIGH alerts ≥ 4` AND `>1/3 of them blocked`.** The measured rate is ~1 in 6 live
   entries; a much higher rate means the real-time read or the denominator is wrong, not that the
   cohort collapsed. **Below N=4, do NOT act on the percentage** — with 2 alerts a single correct
   block reads as 50% and would revert a working guard, and with 0 alerts the ratio is undefined
   and passes vacuously. Under the floor, inspect each block by hand against `mi_daily_closes`
   prev close instead. (Same small-denominator trap as `_ROWCOUNT_MIN_MEDIAN` in #340 and the
   negative-control leg above — a percentage carries no signal until the denominator is real.)
3. Negative control: confirm entries still HAPPEN. Zero entries with zero `gap_below_floor` skips
   means the ORB job did not run, not that the guard is quiet.
4. ⚠ **Attribute every skip to WHICH guard fired — the two shadow each other.**
   `ep_rt_gap_down_authoritative` removes a stale name at the SCAN tick, so it never becomes an
   alert and never reaches the 09:31 check; `ep_rt_entry_gap_recheck` only ever sees what survived
   upstream. The measured split is real (WKC + QBTS were caught at the alert tick, FTNT at 09:30),
   but a raw count of `setup:gap_below_floor` will read artificially LOW and must not be read as
   "the entry check is inert" — it may simply be shadowed. Count `ep_rt_floor_flip_down` with
   `"acted": true` separately from `setup:gap_below_floor` skips.

### 2026-08-01 — #490: gap authority SPLIT — the REMOVE half gets its own toggle (built OFF, awaiting sign-off)

**Trigger**: operator, 2026-08-01, on being shown the volume cost of the RT cutover — *"with 30+
more EP that is potentially traded, that's adding a lot if true, may mean we need more filters if we
let this cohort in, not that is a reason to block them if legit"* → *"fix the vol"*.

`ep_rt_gap_authoritative` does two opposite things at once. Measured per-day over 7/21-7/31:

| half | effect | per day |
|---|---|---|
| flip-UP (`rt ≥ 10 > delayed`) | **admits** candidates the stale gap rejected | **+25.0** |
| flip-DOWN (`rt < 10 ≤ delayed`) | **removes** stale false-admits | **−13.9** |

Against a baseline of 1.86 HIGH alerts/day and 0.57 live entries/day, the admit half is a large
expansion — and grading runs only on ADMITTED candidates (`ep_detector.py:1888`), so it lands on the
LLM path whose end-to-end latency (median 27s, max 150s, measured at ~2 candidates/tick) is what
keeps detection inside the 09:45 ORB cutoff. **The remove half has no such cost: it shrinks the
cohort.** They were inseparable only because one assignment drove both.

**Evidence** (CHANGE_PROCESS r1 — N≥10 evaluated; full working
`docs/analysis/490_delay_missed_eps_2026-08-01.md`): 111 `ep_rt_floor_flip_down` ticker-days over
the 8 days the telemetry has existed. Of those, **11 became scored alerts — all 11 HIGH — and 4
reached a live trade row.**

⚠ **Only 2 of the 4 would actually have been prevented, and the timing is why.** `live_tracker.
process_new_alerts_live` selects `FROM mi_ep_alerts WHERE alert_date = $1 AND score_tier = 'HIGH'` —
**it reads the alert ROW, not the current tick's candidate list.** So dropping a candidate only
prevents an entry if the flip-down happens on the tick that would have WRITTEN the alert. A
flip-down after that is telemetry: the row already exists and the 09:31 entry proceeds.

| ticker | date | delayed | RT | flip-down @ | alert written @ | prevented? | P&L |
|---|---|---|---|---|---|---|---|
| WKC | 07-24 | 11.63% | 8.91% | 08:15:00 | 08:15:00 (same tick) | ✅ **yes** | **−$23.80** |
| QBTS | 07-27 | 11.29% | 9.50% | 07:20:01 | 07:20:00 (same tick) | ✅ **yes** | **−$22.26** |
| FTNT | 07-30 | 10.79% | 7.77% | 09:30:05 | 07:00:00 | ❌ no — 2.5h late | −$6.63 |
| ARM | 07-30 | 15.46% | 8.34% | 09:45:10 | 08:55:00 | ❌ no — after entry | $0 (cancelled) |

**Defensible saving: −$46.06 of a −$224.01 30-day total (20.6% of the loss) from 2 of 17 trades** —
neither of which ever qualified on real-time data, and both losers.

⚠ **Honest N**: the criterion is evaluated on 111 events / 11 alerts, but the P&L attribution rests
on **2 filled trades**. Telemetry only starts 2026-07-21, so a longer window does not exist yet.
Two trades is not a distribution — the case rests on the mechanism (these names did not meet the
10% floor on truthful data) rather than on the size of the measured saving.

▶ **FTNT exposes a separate and arguably larger gap, NOT fixed here.** Its alert was written at
07:00 on stale pre-market data; at **09:30:05 — one minute before the entry — the system recorded
that its real-time gap was 7.77%, below the 10% floor — and entered anyway**, because nothing
re-validates an alert against real-time data at submission time. That is an entry-path change, needs
its own sign-off, and is filed under #490 rather than smuggled into this one.

**What shipped**: `ep_rt_gap_down_authoritative` (runtime toggle + `EP_RT_GAP_DOWN_AUTHORITATIVE`
env), consulted ONLY when `ep_rt_gap_authoritative` is off, so full authority still subsumes it.

**Never-loosen, structurally**: the branch is guarded by `rt_gap < MIN_GAP_PCT <= dl` — the flip-DOWN
condition exactly — so it can only push a decided gap BELOW the floor. A superset-only admit
(`dl < MIN_GAP_PCT`) fails `MIN_GAP_PCT <= dl`, is never touched, and `_floor` drops it as today.
`tests/test_490_gap_down_authority.py` pins this with a 144-case sweep over (delayed, rt) pairs on
both the verified and unverified prev_close paths, asserting the admitted set is a SUBSET of today's.
**Mutation-tested**: removing the guard fails 3 tests including the sweep.

`ep_rt_floor_flip_down` now carries `acted` — without it the event read identically in both modes and
verify-live could not tell whether the cleanup was running.

**NOT changed**: `MIN_GAP_PCT=10.0`, the ORB window, scoring weights, safeguards, sizing, and the
flip-UP half — which stays gated behind `ep_rt_gap_authoritative` exactly as before.

**Reversion-flag**: NEW (splits an existing toggle; neither half changes meaning). Reversion = set
the toggle back off — no code change, no deploy.

**Status**: **LIVE — operator SIGNED OFF 2026-08-01 ("yes to both"), flipped 20:00 ET.**

Shipped OFF first and verified inert, then flipped — so the code path was proven live before it was
allowed to act. Deploy sequence (`ep_detector.py` is in `exec_loaded_modules.txt`, so BOTH services
run it): `deploy.sh market-agent` → `deploy.sh execution`, both green. Delta read before deploying —
the only code change in the range was this one. Toggle set in `mi_safeguard_state`
(`ep_rt_gap_down_authoritative` / `global` / `on`); **both containers confirmed reading
`down=True, full=False`** — i.e. the remove half is acting and the flip-UP half is still gated.

**Reversion**: set that row to `'off'` — takes effect within ~60s, no deploy, no code change.

**Verify-live due Monday 2026-08-03** (first market session), THREE legs — the third is the one that
makes the check non-vacuous:

1. `ep_rt_floor_flip_down` events carry `"acted": true` and the summary suffix `REMOVED`. Still
   reading `SHADOW` ⇒ the toggle is not being honoured.
2. The tickers named in those events do NOT appear in `mi_ep_alerts` for that date.
3. ⚠ **NEGATIVE CONTROL — confirm the scan ran at all** (any `ep_rt_*` event for 2026-08-03).
   Flip-downs averaged 13.9/day, but that is an average and a quiet Monday can legitimately produce
   zero. Without this leg, "no flip-down rows" passes legs 1-2 vacuously and is indistinguishable
   from the detector never running. (`shadow-zero-effect-check-instrumentation`: a dark mechanism
   reading zero effect is usually an artifact until the acting population is confirmed.)

### 2026-07-25 — #490 RT-1: full real-time detection built DARK (shadow note only — NO criteria change)

**Trigger**: operator ruling 2026-07-24 ("there isn't a rational reason to not use real-time
data when we are trading real-time") + the signed design
`docs/analysis/490_full_realtime_design_2026-07-25.md` (all 6 forks ruled). Detection reads a
~15-17-min-stale Polygon snapshot while execution is already Alpaca SIP; the class the #489
hybrid structurally cannot catch holds the biggest moves (NVVE +95.3% cross→high; TRAX +46.6%).

**Evidence**: design §9 — N=47 residual (hybrid_caught=false) cases, prod-measured on the
CROSS basis; 190/190 prev_close mismatch events proven to be Alpaca's pre-open T-2 off-by-one
(§1.2), not vendor noise.

**What shipped (ALL dark — `EP_RT_UNIVERSE_ENABLED` default false; runtime toggles
`ep_rt_universe_authoritative` / `ep_rt_volume_authoritative` default off; flags-off is
freeze-tested byte-identical)**: Pass-0 full-universe Alpaca SIP overlay (one fetch/tick,
reused by Pass-2 + the miss watchdog); tick-quality guards Q1-Q4 (NBBO band + quote freshness +
MANDATORY minute-bar corroboration for any RT-only admission + absolute insanity bound
replacing the 30pp clamp on the universe path) with a loud `ep_rt_tick_quality_reject` reason
enum; halt quarantine (heuristic, §4); corporate-action (split) hold (§2.2); G1 scan-log
columns populated (`gap_pct_rt/gap_pct_delayed/price_source/rt_price_age_s/prev_close_alpaca`);
`ep_rt_universe_catch` shadow events (audit-only, digest surfacing per the 7/21 noise ruling);
volume/RVOL shadow (§6.1, own flip); `current_price` coherence under authority (§6.4);
cross-basis residual columns + O-9 retired as a trigger (§9.4).

**Live-behavior deltas that ride the CURRENT hybrid (bug fix + observability, not criteria)**:
(1) the Pass-2 prev_close cross-check is now DATE-KEYED (§2.1) — pre-open, Alpaca's
`previous_daily_bar` deterministically holds T-2, so the old compare silently dropped the RT
read of every candidate whose prior day moved >0.5% (the pre-open shadow was censored:
flip-up 29 RTH vs 2 pre-open). Fail direction unchanged (real mismatches still degrade to
delayed); (2) the Pass-2 30pp clamp emits `ep_rt_gap_clamped` (C1 — clamps were invisible).

**NOT changed**: `MIN_GAP_PCT=10.0` (the 2026-05-17 R2 decision is preserved — and will be
enforced on truthful data post-flip), ORB window 9:31-9:44, scoring weights, safeguards,
sizing, the delayed Polygon path (retained as universe/reference/failure-ladder, §7). The
detection COHORT is untouched until the operator executes RT-3 (`ep_rt_universe_authoritative`
+ `ep_rt_gap_authoritative` on) after the RT-2 shadow packet — that flip gets its own
change-log entry (data source: "Polygon delayed reference + Alpaca SIP real-time universe
overlay").

**Reversion-flag**: NEW (first change to the detection data source; extends #489's shipped
shadow architecture). Rollback: R1-R5 (§8) — every rung instant + independent, landing on
byte-identical prior behavior.

**Status**: deployed, RT-2 shadow ACTIVE — `EP_RT_UNIVERSE_ENABLED='true'` confirmed in both
containers (prod read 2026-08-23). RT-3 (`ep_rt_universe_authoritative` /
`ep_rt_gap_authoritative` on) has NOT happened — neither has an override row in
`mi_safeguard_state`, so both still default **False** (verified same read); a universe catch
is still SHADOW, never admitted. Next: RT-2 gates (≥10 trading days AND ≥5 residual-catch
days, 8 measurable gates, 3 operator-reviewed named lists) → RT-3 operator flip.

### 2026-07-24 — FL-5 reconcile: doc synced to code

Six stale items corrected (no code change): (a) catalyst weights were
documented as multipliers (1.0×/0.7×/0.3×) — code is an ADDITIVE component
(`game_changer`→+25, `strong`→+15, `routine`→+0, ep_detector.py ~1140); (b)
`ep_threshold` range was "65-75" — `regime.py` runs Bull=65/Choppy=70/
Correcting=75/**Crisis=80**, so the true range is 65-80; (c) ORB submission
window text implied the full 9:00 hour — the market-open gate makes the
effective window **9:31-9:44** ET; (d) `MIN_GAP_PCT=10%` hard floor added to
the filter list (was undocumented); (e) the filter list now separates
**pre-grade** filters from the **post-grade** ones (M&A filter, routine+low-gap
skip, pm-shares floor carve-out — all in `_post_grade_filters`, moved
post-classification by #405 2026-07-03 specifically so they can read
`catalyst_quality`) instead of presenting all seven as one undifferentiated
pre-grade cascade; (f) added a note that the Holistic Grade Judge (toggle,
currently OFF) overwrites `score_tier` when enabled.

### 2026-07-23 — #500 Price-aware initial ORB entry: bounded limit-buy fallback when price is already above the ORB high (+ broker-cancel reason capture) [operator-SIGNED]

**Trigger**: ARWR 2026-07-22 (live) — +19.57% gap HIGH EP; the 9:31:00.8 stop-limit bracket
went pending_new → cancelled by Alpaca within ~1 min because price (~$89.06) was already above
the $87.92 ORB-high trigger (an in-the-money buy stop is invalid at the broker); operator saw
"entry cancelled, no reason." SMCI (sitting AT its ORB high) filled the same morning. The
re-entry path has handled exactly this since May (`attempt_day1_reentry` ~615); the initial
entry never did — so the entry mechanism failed preferentially on the most violent gappers.

**Evidence**: `docs/analysis/500_orb_entry_price_aware_proposal_2026-07-23.md` — full-history
cancelled-entry cohort N=11 (read-only prod SQL + SIP tape): in-the-money-stop class **N=2**
(ARWR live, CADL paper) — FLAGGED small-N (below the N≥10 bar; the branch is an order-type
correctness fix per the 2026-05-20 gate-inversion precedent, but the 1.5× chase cap IS a
threshold calibrated on N=2). ARWR fallback sim: +0.16R/−0.16R day-1-close bounds, MFE
+1.7R–2.1R, risk inflation ≤1.37× (admitted). CADL (+14.8% chase, 11.3× inflation, −3R/−11R
sims) is the cap's sole historical drop — **operator reviewed + confirmed the drop list per
rule 3 at sign-off 2026-07-23**. Adjacent classes NOT fixed (named to prevent attribution
drift): LULD rejects (#475 review), gap-through-limit (#22 / known-limitation 4).

**Anticipated effect**: entries where price ≤ ORB high at submit — byte-identical bracket
(zero behavior change; the overwhelming majority). When price > ORB high at submit (~2% of
the 89 historical submissions, concentrated in the strongest gappers): a bounded limit buy
(`latest×1.002`, risk-inflation cap `CHASE_RISK_INFLATION_CAP=1.5` env-tunable, worst case
1.5% equity vs the sized 1.0%) replaces a guaranteed broker cancel; beyond the cap →
`setup:chase_cap_exceeded` skip + Telegram (fail-safe: missed entry, never a bad fill). The
retry re-decides the branch. `mi_live_orders` records the ACTUAL order (type/limit; no fake
trigger row for the limit fallback). Broker cancels/rejects now persist a `broker:*`
skip_reason with a last-vs-trigger diagnosis (`order_manager.broker_terminal_reason`, WS +
polling paths) + Alpaca's terminal order snapshot merged into `mi_live_orders.raw_response`
— "no reason" cannot recur. Hardening ride-along: `place_limit_buy_with_stop` now passes
`OrderClass.OTO` + `StopLossRequest` + the naked-order guard (the alpaca-py
silently-dropped-stop_loss gotcha — a latent NAKED-limit-buy bug on the re-entry path, which
had never fired in prod: 0 limit buys in 89 historical entries). Est. ~1 engaged entry /
6 weeks at current alert volume.

**Reversion-flag**: NEW for `submit_entry` (extends the re-entry's price-aware branch — in
code since May, never fired in prod — to the initial entry, with a chase bound the re-entry
lacks). Hard revert = delete the `_pick_entry`/`_chase_cap_reason` branch in `submit_entry`
(restores the unconditional bracket) + revert the `broker:`/`setup:chase_cap_exceeded`
skip-reason additions. The `place_limit_buy_with_stop` OTO/naked-guard hardening should
survive any revert — it fixes a latent naked-order bug independently of #500.

**Status**: operator-SIGNED 2026-07-23 (decisions §7 of the analysis doc: branch + 1.5× cap +
CADL drop-list + reason capture approved; option B cancel-triggered retry DEFERRED,
data-gated on post-fix residual `broker:entry_cancelled` rows). Deployed (commit `85947a86`,
an ancestor of the running prod checkout `8bcf6ff0` — `_pick_entry` / `CHASE_RISK_INFLATION_CAP`
confirmed present in the prod checkout 2026-08-23; no toggle, code is the flip). Verify-live
layers: (L1) deploy-day below-orbH entries byte-identical brackets; (L2) first engaged fallback
— log line + OTO stop leg + honest mi_live_orders row; (L3) next broker cancel carries a
`broker:*` reason, never a bare "cancelled".

### 2026-07-19 — Large-cap rel_volume floor SHADOW observer added (audit-only, no criteria change)

Telemetry only, no detection-criterion change (operator shadow-approved 2026-07-19).
`_emit_large_cap_relvol_floor_shadow` (ep_detector.py) writes one
`filter:large_cap_relvol_floor_shadow` mi_audit_log row per HIGH alert with ADV$
(`adv_20 * prev_close` — the pre-gap price, matching `mi_stock_scores.close`, NOT
today's gapped `current_price`) >= $50M and rel_volume < 0.5, gated `LARGE_CAP_RELVOL_FLOOR_SHADOW_ENABLED`
(default ON). Does NOT skip the alert or change any grade/gate/entry decision — pure
observation of what a future LIVE floor would have done. See `data_gated_reviews.yaml` →
`large_cap_relvol_floor_shadow_evidence` for the forward-tracking review (N>=10 settled
shadow-flagged entries, ~2026-09-01) that gates any future LIVE flip
(`LARGE_CAP_RELVOL_FLOOR_ENABLED`) — operator-signed only, never auto-flipped.

### 2026-07-18 — Analyst-upgrades bonus REMOVED — dead feed since 2026-03-14 (#332, operator-signed)

**Trigger**: #332 C1 setup-class classifier build surfaced that `_score_ep`'s cached-grade tick
hardcoded `upgrades_30d = 0` (a latent inconsistency vs the uncached path). Gated fix on a
backtest before touching a live-scoring path per CHANGE_PROCESS.

**Evidence**: `docs/analysis/332_analyst_bonus_backtest_2026-07-18.md` (probe:
`scripts/probes/_332_analyst_bonus_backtest.py`, read-only, run over prod postgres + the REAL
production `get_fmp_analyst_ratings` function per memory `rigor-before-paid-eval-spend`):
1. The feed (`collector.get_fmp_analyst_ratings`, yfinance `Ticker.recommendations`) has been
   structurally dead since 2026-03-14 — it returns the AGGREGATE grade-count table (columns
   like `strongBuy`/`buy`/`hold`/`sell`), and the string-matcher compares grade NAMES against
   INTEGER COUNTS, which can never match. Verified by running the real function in the live
   `apollo-market` container for NVDA/AAPL/PLTR (the most analyst-covered names in the
   market) — all returned `upgrades_30d = 0` — plus 20 sampled live-alerted tickers, also 0.
2. **Realized impact of the cached-tick hardcode: 0 alerts, 0 tier flips** across all 251
   retained live alerts (2026-04-13 → 2026-07-17) — the uncached path ALSO always computed 0,
   so cached − uncached = 0 on every tick. The "fix" as originally scoped (thread the real
   cached value) would have threaded a constant 0.
3. Reconstructed counterfactual (a REPAIRED feed's value, had it worked): bonus-eligible
   alerts do NOT outperform (N=203 with fwd-10d outcomes; permutation p=0.29 overall, p=0.18
   within-HIGH; mean fwd-10d direction actually LOWER for eligible). What the live `>=3`
   threshold's grade-set actually selects is analyst-coverage BREADTH (TXN/QCOM/ROKU/DDOG/
   WDAY/ZM class) — a mature-large-cap proxy, the OPPOSITE of this rubric's own neglect thesis
   (`breakdown["neglect"]` already scores 52w-high distance directly). The honest "true
   upgrade" threshold (`>=3` distinct upgrade Actions) occurred once in 3 months of EP
   candidates — nothing to calibrate a bonus on even if repaired.

**Anticipated effect**: NONE on any historical or current alert/tier/score — removal is
**behavior-identical by construction** (the term contributed exactly 0 on every tick, ever,
since the feed always returned `analyst_upgrades=0` and `0 >= 3` is false). Forward-looking
effect: removes the risk of a future yfinance schema change silently re-animating the bonus at
an uncalibrated +5 raw points (worth 5.0–7.2 final points post-multiplier) with no edge behind
it.

**Reversion-flag**: REMOVAL (dead-feed retirement) — not a reversal of a specific prior dated
change; the bonus predates this SSoT's change-log history. Not a REFINEMENT (no repair
shipped) and not a REVERSAL of a deliberate calibration (the backtest's §4 shows no calibration
would have justified keeping/repairing it).

**Status**: shipped, behavior-identical by construction (evidenced against all 251 retained
live alerts, not merely asserted) — no field-validation period needed for a change with a
provably-zero realized delta.

**Scope of removal**: `breakdown["analyst"]` term + the `analyst_upgrades` parameter deleted
from `_score_ep` (`agents/market_intelligence/ep_detector.py`); the now-orphaned
`get_fmp_analyst_ratings` fetch + `upgrades_30d = sum(...)` aggregation removed from the
per-candidate scan loop and from `collector.py` (verified no other LIVE consumer via repo-wide
grep — a pre-existing, already-broken standalone script `backtest_ep.py` also referenced it
but was already non-functional before this change, unrelated missing symbol). The `#332`
classifier's OWN `upgrades_30d` (the `episodic_neglect` low-coverage cut) is UNAFFECTED by this
entry — it now sources independently from `collector.get_recent_upgrade_events` (yfinance
`Ticker.upgrades_downgrades`, dated events), a repair tracked in
`docs/decisions/0028-setup-class-conviction-profiles.md` §2, not this rubric.

### 2026-08-22 — Two backwards-running score components DELETED [#533]

**Trigger**: the same selection study and priced proposal as the liquidity change below. The
operator signed off on continuing: *"do all in order."*

**Evidence**: `docs/analysis/score_redesign_proposal_533_2026-08-22.md`, 26 labelled real EPs vs
1,074 ordinary gap days.
  - **`neglect` (DELETED, NOT replaced)** — scored *"is this stock ≥30% below its 52-week high"*,
    a **beaten-down** detector. The operator's thesis is a long **QUIET** base wherever it sits.
    **MRNA — his own canonical textbook EP — is `Off 52W High 0.0%` and scored ZERO on the
    component named after his own thesis.** 65% of labelled real EPs scored zero. It paid JUNK
    more than real EPs: 48% of controls got points vs 35% of members. **In-package: +0.09 AUC.**
  - **`prior_momentum` (DELETED)** — fired on real EPs and ordinary gap days at the **same rate
    (31% vs 32%)**, subtracting up to 25 points while separating nothing. It drove **ARM to −12,
    dead last on its board**, on a real EP that had already beaten the admission cap at rank 18.
    **In-package: +0.04 AUC.**

**Anticipated effect**: scores rise slightly across the board (two subtractive/zero-heavy
components removed); ranking improves. No change to throughput beyond the bar effect.

**Reversion-flag**: NEW for both — neither component had been changed since inception.

**Status**: shipped, awaiting field validation.

⚠ **WHY `neglect` GOT NO REPLACEMENT — the important part.** The pre-registered quietness
measure WAS built and calibrated to his own MRNA annotations (it finds his 106-day base exactly)
and scored **AUC 0.42 — real EPs have SHORTER quiet bases than their board rivals.** That is the
**third null/backwards read across three definitions and two labels.** The base thesis stays in
the VISION lane and the rank shadow until something measures it that does not run backwards.
Deleting a broken proxy is not the same as abandoning the idea.

⚠ `prior_3m_change` is still computed and still logged — it is simply no longer SCORED.

### 2026-08-22 — Score ranks on LIQUIDITY, not relative volume [#533]

**Trigger**: the selection study (`docs/analysis/selection_layer_533_2026-08-22.md`) found the
composite score **anti-selective** — AUC 0.37-0.41 against 26 labelled real EPs, where 0.5 is a
coin flip. Of 26 real EPs the funnel kept ZERO. The operator signed off after reviewing the
priced proposal: *"sign off on the liquidity change."*

**Evidence**: `docs/analysis/score_redesign_proposal_533_2026-08-22.md`, measured on 26 labelled
real EPs vs 1,074 ordinary gap days.
  - Old `rel_volume` ladder scored *"how unusual is today's volume for this stock"* — **AUC 0.31,
    i.e. it ran BACKWARDS.** The labelled cohort's MEDIAN is **1.8× — which earned ZERO** — while
    a sleepy micro-cap at 3× scored 10.
  - **Ex-ante 20-day ADV$ separates at AUC 0.72**, better than same-day dollar volume (0.65),
    needs no intraday projection, and is already computed per scan row (`adv`).
  - **It is the load-bearing change**: the full proposed package scores 0.33 WITHOUT it and
    0.63-0.70 with it.
  - Within-day slot ordering (the MRNA-vs-MRVL problem): a real EP's median board percentile
    goes from **28th (worse than random) to 75th**.

**Anticipated effect**: alert volume roughly flat-to-down — the full package is 2.07/day vs
today's 2.46. This change alone moves ranking, not throughput. Tiers: ≥$500M→15, ≥$250M→12,
≥$100M→10, ≥$50M→7, else 0. A second tier set (1B/500/250/100) gives the same package AUC, so
nothing hinges on the exact cuts.

**Reversion-flag**: NEW — first change to this component since inception.

**Status**: shipped, awaiting field validation.

⚠ **Four limits stated, not buried.** (1) **In-sample**: the liquidity axis was DISCOVERED on
these same 26 names; true out-of-sample is the post-07-16 label window (~mid-October) plus the
rank shadow. (2) The label is outcome-conditioned and its R-geometry favours liquid names, so
**part of this separation may be the label itself**. (3) It selects mega-caps on beta days — the
catalyst grader downstream must still separate real news from sector sympathy, and that grader is
currently the wall (a `routine` grade still kills a real EP under every variant tested).
(4) **The separate 2.0× session-RVOL GATE is untouched** — this changes RANKING only; whether
that gate should stay is not priced here.

⚠ **Unknown ADV falls back to the OLD RVOL ladder rather than scoring 0** — a data gap must never
silently sink a candidate (P1: a false exclusion leaves no trace). Mirrors
`_check_adv_dollar_volume`, which also passes an unknown-ADV name rather than dropping it.

### 2026-08-22 — Extension cap loosened 50% → 75% [#577A]

**Trigger**: the #577 gate-pricing sweep. The extension gate ranked first of eleven gates by how
many of its excluded names later reached a ≥100% 20-day peak (29). The operator then signed off
on the loosening after reviewing the banded evidence: *"ok, signed off on the change to 75%."*

**Evidence**: `docs/analysis/gates_extension_top20_577_2026-08-22.md`, 170 blocked rows over four
months. The gate as configured is **91% redundant** — that share of its kills would have died at
ADV / ATR% / market-cap anyway; its UNIQUE kills are 15 rows. Banded:
  - **50-75%**: 5 names ran ≥50%, including 2 doublers (FCEL, MRAM), against 1 loser. This is the
    slice being recovered.
  - **75-100%**: the dead zone, and it holds the disasters the gate genuinely prevents —
    CAR −80%, SPCE −60%. **This is why the new cap is 75 and not 100.**
  - Whole-gate population median 20-day close is −44%, with 63% falling ≥30% — the gate as a
    whole is sound; only its bottom band was mispriced.

**Anticipated effect**: ~2 extra HIGH alerts per 4 months (~0.5/month). Expected converted
doublers per loosening ≈ 0.4-0.6 after the remaining catalyst/score funnel (~24% pass). This is a
SMALL, bounded loosening — not a throughput change.

**Reversion-flag**: NEW — first change ever to `MAX_EXTENSION_PCT`, which has been 50.0 since
inception.

**Status**: shipped, awaiting field validation.

⚠ **Two limits stated, not buried.** (1) All five recoverable names sit in ONE April macro
regime; the next flood day is the out-of-sample test. (2) The only recoverable winner with minute
bars (MXL 04-24) fills at **−1R under the stop rules in force and ≈+3.5R under the current 2R
stop** — so whether a recovered winner actually pays is decided by CONVERSION (#562), not by this
admission change. Loosening the door does not by itself make money.

### 2026-07-18 — Extension-rule wording corrected (transcription fix, NOT a criterion change) [#481]

The "Extension" rule (Universe eligibility line 19 + Filter 4 line 30 + score-factor list line 53)
was mis-transcribed at this doc's birth (2026-05-07, `59e4601`) as `prev_close ≤ 1.50× SMA-10` — a
rule that has **never existed in the code** (`git log --all -S "sma_10 * 1.5"` → no commit, ever).
The LIVE guard, since inception, is `MAX_EXTENSION_PCT=50.0`: skip if `prev_close` is ≥ 50% above the
MIN(close) of the last ~5 trading days (`ep_detector.py:99`, gate `:1858-1866`; MIN, not a single
5-days-ago point). Operator ruled 2026-07-18 (#481) that the live 50%/5-day rule is the intended
criterion → corrected the wording to match the code. **No detection behavior changed** — this is a
documentation/provenance fix. Also corrected line 53's score-factor list to name `prior_momentum`
(the 3-month extension PENALTY, −25/−15) rather than a non-existent "extension" component. The
constant is now cited in `gate_provenance_registry.py` against this corrected SSoT.

**Reversion-flag**: N/A (doc-only correction; the code has always been the 50%/5-day rule).

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
16 unit tests. **Deployed and field-validated**: `title_implies_acquirer` /
`mna_acquirer_title_skipped` confirmed wired in the running prod checkout (verified
2026-08-23); the live wiring has fired for real, 4 times, 2026-06-24 through 2026-07-07
(`mi_audit_log`, prod read-only). Monthly accuracy review continues as a standing check.

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

**Anticipated effect**: with the toggle OFF (current, SHIPPED DORMANT) — **zero behavior change**, byte-identical to W1 shadow; the judge writes only its own `judge_*` columns + `ep_grade_decision` audit traces. ⚠ 2026-08-27: the toggle is ON and has been for months — `grade_engine_authority='judge'` on 145 of the last 147 alerts; this paragraph describes the pre-flip state only. With the toggle ON (operator-gated, paper-only) — the paper HIGH set is re-graded: gap-only HIGHs with no material catalyst demote out of entry; material-relative-to-size MODERATEs promote into entry. Net HIGH count change unknown until the live cohort accrues (first judge fire 2026-06-09).

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

> ⚠ **Amended 2026-08-24 (#591, operator-signed).** That close now runs only when the
> stop fill leaves NOTHING outstanding. If shares remain — a +2R carve-out limit still
> resting at the broker, ETON 2026-08-14 — the row stays OPEN at those shares and no
> re-entry is attempted; whatever exit owns them closes the trade. Re-entry is a
> full-stop-out concept, so the R3 decision itself is unchanged. SSoT:
> `docs/setups/exit_discipline.md` change log, 2026-08-24 (#591).

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
