# #533 Change 6 — the catalyst-tier SHADOW grader: measured against the wall it exists to break (2026-08-22)

**SHADOW ONLY — NOTHING LIVE CHANGED.** The live grade, prompt, tiers, score and every
threshold are untouched; the tier definitions are a detection criterion = the operator's
sole authority (THE LINE). What shipped is a deterministic re-tiering layer that runs
ALONGSIDE the live grader, writes to `mi_catalyst_tier_shadow`, and is read back by
nothing. $0 — no LLM call anywhere in it; evaluation ran on one read-only prod capture.
Adoption is CHANGE_PROCESS + operator signature. **Nothing here is committed or deployed.**

## The question

The proposal's own verdict (`score_redesign_proposal_533_2026-08-22.md`): every mechanical
score fix stops at the catalyst wall — a routine-graded real EP dies under EVERY variant
(0 of 26 clear 50 at any bar ≥35), while `game_changer` goes to 42-44% of ordinary live
alerts and at most 1-2 of the 7 graded real EPs. MRNA 2026-08-19 — the operator's canonical
textbook EP, *"complete gamechanger in every way"* — graded `strong` at 07:05 and was killed
at score 21.6 on its 10% gap read; only the freak 33% read at 07:10 rescued it. Can a
surprise-anchored re-tiering, built from inputs we already hold, (a) give MRNA the top
grade, (b) cut the ordinary-day false-positive rate, (c) without demoting the PEG class or
rebuilding gap-scoring under a new name?

## Data

- **Capture** (one pull, read many): `scripts/probes/_533c_capture.psv` — all 414
  `mi_ep_alerts` rows with flattened text (analysis, grounded corpus, catalyst), all 264
  stored #568 expectedness rows (`mi_alert_rank_shadow`), per-day scan boards with sectors
  for the 66 alert days, per-day regime + threshold, and the member-day audit rows
  (04-17 / 04-24 / 05-06 / 05-29 / 08-19). SQL: `_533c_pull.sql`.
- **The thing measured is the shipped logic itself**: the eval
  (`scripts/probes/_533c_eval.py`, output `_533c_eval_out.txt`) imports
  `catalyst_tier_shadow.shadow_retier` — never a reimplementation.
- Primary run uses the STORED expectedness axes (the live #568 derivation's own output on
  its full inputs); a consistency run re-derives them from the captured (truncated) text —
  12/264 shadow tiers move, so numbers below carry roughly that input-sensitivity.
- Label: the 26-member #577 fixture. Only 7 were ever graded; only MRNA (and INTC, via an
  audit-log excerpt — its alert row was purged) left any analysis text. n is tiny and
  treated as such throughout.

## What was built (one paragraph, pointers only)

`agents/market_intelligence/catalyst_tier_shadow.py`: a one-step re-tiering lattice over
the live grade — the live LLM grade stays the only news-magnitude estimator; the lattice
moves it at most one tier on mechanical surprise evidence: the #568 axes
(`expct_scheduled` / combined forward-backward / beat language), rule-4 demotion markers +
concrete-event evidence (regex over the recorded analysis/corpus), and sector
follow-through (other same-sector names on the day's crossed board). Recomputed every scan
tick — first/last verdicts + `regrade_count` per (scan_date, ticker) — so a 07:05 grade is
no longer pinned all morning. Wired fire-and-forget in `ep_detector.run_ep_scan` after
`_score_ep` (captures the score<50 skips — where ARM/QCOM/AMD died with no recorded text);
fail-open end to end. Table DDL in `db.py`; 23 tests in
`tests/test_catalyst_tier_shadow.py`; suite 5786 passed / 7 skipped.

## Result 1 — MRNA 2026-08-19 comes out `game_changer`, and clears at its REAL 07:05 gap read

- Shadow verdict on the recorded alert: **strong → game_changer**, rule
  `strong_promoted_group_repricing` (unscheduled per the live #568 row + forward content +
  7 other Healthcare names on the day's 17-name board, 44% share — the operator's own
  evidence: *"many other biotech names rose significantly on same day"*).
- Counterfactual at the killing tick: gap read 10.04%, live raw score 18 (=21.6/1.2).
  Shadow game_changer ⇒ gap≥10 floor 60 ⇒ **score 72.0 ≥ that day's HIGH threshold 65**.
  **The reference EP alerts HIGH at its modal-gap read instead of surviving on a freak
  33% print.**
- Timing honesty: the board's sector composition is captured day-aggregate; whether 4+
  healthcare names had crossed by 07:05 exactly is unknowable offline. The intraday-regrade
  provision is what makes this robust: the moment the group fills in, the shadow flips —
  before the ORB window, unlike the live grade, which changed intraday on only 15 of 700
  graded ticker-days.

## Result 2 — the false-positive rate: 43% → 18% of ordinary live alerts

| pool | live game_changer | shadow game_changer |
|---|---|---|
| all 264 live alerts | 78 (30%) | **38 (14%)** |
| last 60 days (n=149) | 64 (**43%**) | **27 (18%)** |
| HIGH alerts (n=187) | 78 (**42%**) | **36 (19%)** |

- Where the cut comes from: 35 scheduled game_changers demoted for missing content-delta
  evidence (no beat language AND/OR no forward-changing content), 9 unscheduled ones for no
  concrete forward event. 17 scheduled game_changers KEEP the top tier on beat+forward —
  the PEG class survives (Result 4). All demotions are one step, to `strong` — floors
  intact, so a 20%+ gapper still alerts; this is a 10-point haircut, not a skip.
- Shadow game_changer lands at 14-19% — near the 11.6% graded-candidate base rate, i.e. the
  top tier becomes rare again instead of near-modal.

## Result 3 — the 26 labelled real EPs: 2 of 7 verified clear, MRNA's clear becomes structural; 4 of 7 undetermined offline

- **MRNA**: clears at the 07:05 read (Result 1) — under live grading it cleared only by the
  33% gap print. **INTC 04-24**: replayed on its surviving audit-log text the keyword axes
  MISS the beat ("$13.6B versus Wall Street expectations of $12.4B" carries no
  beat-verb-near-"estimate" pattern) → shadow demotes to strong — **but at gap 27.9% the
  gap≥20+strong floor 80 still clears HIGH**. Net: **2 of 7 clear, same count, one of them
  no longer by luck.** The INTC miss is an instrument limit of the #568 regexes on
  truncated text, flagged, not smoothed.
- **ARM / QCOM / AMD / UMC: undetermined offline.** They died at score<50, so no alert row
  exists and `mi_ep_scan_log` stores no analysis text — the corrective (routine + rule-4
  markers + concrete event → strong) cannot be evaluated on them at $0. This is exactly the
  hole the live shadow closes going forward: the new capture point records every GRADED
  candidate including the score<50 skips. **QURE**: killed by the M&A hard filter — flagged
  in the proposal as a separate question, out of scope here.
- The other 19 members were never graded at all (floor/cap kills upstream) — no tier fix,
  live or shadow, touches them.

## Result 4 — both operator corrections are applied, and where

- **Scheduled ≠ unsurprising (the PEG family).** The calendar axis alone never demotes:
  a scheduled event with beat + forward-changing content keeps `game_changer`
  (`gc_kept_scheduled_content_delta` — 17 of 52 scheduled GCs in the replay). Demotion
  requires a KNOWN scheduled lane with content-delta evidence ABSENT — evidence-of-absence,
  not calendar-as-verdict; a wholly-unknown calendar keeps its tier (fail-open). Strongs
  are never demoted at all, so no scheduled strong is harmed anywhere.
- **P13 — the unpriced residual.** Recorded, deliberately NOT scored: the table stores the
  residual's raw inputs per row (gap first/last, ADV$, rel_volume, projected multiple, both
  grades) so the estimate becomes computable once an honest magnitude axis exists. Scoring
  it today would calibrate a residual against the broken 3-level grade on n=7 —
  manufactured confidence. The frame is in the module/table docstrings by name.

## Result 5 — which side of the price-reaction line this sits on

- **The lattice reads NO subject price reaction.** `shadow_retier` takes no gap, price or
  score argument — pinned structurally by
  `test_shadow_retier_takes_no_price_input`. Nothing in any demotion or the routine
  corrective touches price.
- **One input is market-derived and partially on the reaction side, disclosed: sector
  follow-through** — the presence of OTHER same-sector names on the day's crossed board,
  used ONLY to gate the single promotion lane (strong→GC, additionally requiring
  unscheduled + forward). It infers surprise from the PEERS' reaction, never the
  subject's own gap — the operator's own MRNA argument — but it is **beta-confounded on
  sector-flood days**: on 07-30's 86-name board, 42% of names pass the confirm; the
  instrument cannot tell the cause (MRNA) from a passenger (TWST, promoted alongside it
  same day). It fired 4 times in 264 alerts (CAMT 06-02, AEHR 06-17, MRNA + TWST 08-19)
  because the joint gate is narrow. Raw counts (n_same / board_n / share) are recorded per
  row so the lane can be re-cut or removed against outcomes without new data. **Verdict:
  the implementation is on the right side of the line except this one gated, disclosed,
  replayable input — remove it and MRNA stays `strong`.**

## Result 6 — alert-volume change: net −2 alerts over 4 months (≈neutral)

- Within the already-alerted pool (recomputing each moved alert's score with the shadow
  tier, per-day regime multiplier + threshold): **+6 MODERATE→HIGH** (the routine
  corrective + CAMT's promotion), **−8 HIGH→MODERATE**, **−2 MODERATE→none** (CAT/ZBRA
  08-04, demoted scheduled recaps falling under 50). HIGH count 187 → 185.
- Not measurable offline: promotions among graded scan-only rows that never alerted (no
  stored text). Bounded small — the only upward paths are the corrective and the
  4-in-264-rate promotion lane — and the live shadow measures it exactly from day one.
- The sector-momentum auto-demotion the card asked about: **checked — it is prompt rule 4
  of `_classify_catalyst_claude` (an LLM instruction), no mechanical demotion exists in
  code.** Removing it live is a prompt change = paid re-grading + criterion change, so the
  shadow instead reverses its observable effect at $0: routine + rule-4 markers + concrete
  company event → strong (fired on 6 of 45 routine live alerts: ASTI, QFIN, HYMC, WEN,
  CHTR, SG).

## ⚠ What this does NOT answer

- **Whether the shadow tier converts to R.** Every number is separation/counterfactual
  against an outcome-conditioned label and a replayed pool; no P&L is claimed.
- **n=7 graded real EPs, and only 2 with recorded text.** The member-side read is
  underpowered by construction; 4 of 7 are undetermined offline. The honest n accrues from
  the live shadow at $0; the 19-member retro-regrade stays priced-but-not-spent (its replay
  bias is documented in the proposal — the freshness rule reads dated news as stale, so it
  would "confirm" the inversion as an artifact).
- **Whether sector follow-through survives a true flood regime.** No scan log existed on
  04-08 (13 of 26 members); the beta confound is measured only on the 66 logged days.
- **Per-tick truth.** The capture is day-aggregate; intraday regrade behaviour
  (regrade_count) has no offline baseline — it starts measuring when the shadow runs.
- **The keyword instrument is narrow.** The INTC miss (Result 3) and 12/264
  truncation-sensitivity divergences bound how much the #568 regexes can carry; the shadow
  records its inputs so the axes can be improved and replayed.

## What this means

**The wall is breakable with inputs we already hold: the shadow gives the operator's
canonical EP the top grade at the gap read that actually killed it, cuts the ordinary-day
top-tier rate from 43% to 18%, keeps the PEG class, stays alert-neutral, and touches
nothing live.** Its one impurity (peer-reaction corroboration in the promotion lane) and
its one measured miss (keyword narrowness on INTC's text) are both disclosed and both
replayable from recorded inputs. The decision it tees up for the operator: let the shadow
accrue live rows and judge the tier rewrite on its record, then rule on promoting the
lattice (or an LLM-prompt rewrite it validates) through CHANGE_PROCESS. What would settle
it: the post-07-16 label window (~mid-October) joined against `mi_catalyst_tier_shadow`.

## Files

- Shadow grader: `agents/market_intelligence/catalyst_tier_shadow.py` (lattice + writer) ·
  DDL in `agents/market_intelligence/db.py` (`mi_catalyst_tier_shadow`) · wiring in
  `agents/market_intelligence/ep_detector.py` (input capture after `_score_ep` + batch
  dispatch next to the scan-log write)
- Tests: `tests/test_catalyst_tier_shadow.py` (23) + registry classifications in
  `agents/market_intelligence/health_checks.py` (`_NOT_SWEEP_PARAMS`) and the reasoned
  allowlist entry in `tests/test_alert_rank_shadow.py`
- Evaluation: `scripts/probes/_533c_pull.sql` · `_533c_capture.psv` · `_533c_eval.py` ·
  `_533c_eval_out.txt`
- Anchors: `score_redesign_proposal_533_2026-08-22.md` (Change 6) ·
  `selection_layer_533_2026-08-22.md` · `ep_reference_mrna_2026-08-19.md` ·
  `ep_profitability_program.md` (P13) · method template `adv_floor_556_2026-08-20.md`
