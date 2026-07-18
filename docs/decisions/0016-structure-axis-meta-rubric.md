# ADR 0016 — Technical Structure as a Scored Meta-Rubric Axis (#330) — DRAFT for operator sign-off

Status: **ACCEPTED** (operator-signed 2026-07-04 AM, as proposed) (designed 2026-07-03 eve, on the ADR-0015 pattern). #329 child axis 2 of 3
(#328 theme · **#330 structure** · #331 gap-alignment). Read 0015 first — the form, guardrails,
and rollout discipline are inherited; this ADR specifies only what differs.

## Scope boundary vs #331 (important)
**#330 grades the structure the stock brought INTO the catalyst day** — long-term trend, base
quality, extension state. **#331 grades what the GAP did to that structure** (punched through
resistance vs faded into congestion). Keeping them separate keeps each calibratable alone.

## The components (v1 — the sign-off surface)
Sourced from `user_meta_rubric_architecture` (§D dimensions) + `htf_stage2_long_term_trend_filter`
(the NCI dead-cat lesson: short MAs catch up on a crash-recovery — the LONG-term trend is the
real filter):

| Component | Signal | Source (existing — search-before-build) |
|---|---|---|
| **Stage-2 long-term trend** | above 200MA AND within ~25% of 52w high | mi_daily_closes MAs; the #356 HTF Stage-2 gate logic (reuse its exact predicate) |
| **Base quality going in** | prior consolidation tightness before the gap | **RMV** (`flag_detector._compute_rmv` — the SSoT tightness primitive, `reference_rmv_tightness_metric`) over the pre-gap window |
| **Extension state** | how stretched vs SMA-10/20 at the PRIOR close | the 9M detector's extension gate (prev_close ≤ 1.20×SMA-10) — citation corrected 7/4 post-signing (STEP-0 flag: MAGNA53's gate is a 5-day-min-close form; the SPECIFIED metric is unchanged) |

v1 mapping: **boost-only, mirroring 0015** — Stage-2 + tight base = +1 tier-step eligibility;
partial (Stage-2 only) = near-miss band; absent/unknown = 0, never negative. Rationale for
boost-only here too: gross bad structure is ALREADY hard-gated at detection (the 1.20×SMA-10
extension gate); re-penalizing post-detection would double-count the gate. A bidirectional v2
(penalizing gap-into-heavy-overhead) is #331's territory and a CHANGE_PROCESS question with data.

## STEP-0 calibration (before any shadow ships — same discipline as 0015)
The 452-row cohort carries theme fields but NOT structure — however all three components are
**computable historically from mi_daily_closes** for each (ticker, alert_date). STEP-0 = backfill
the three features onto the same cohort (read-only script, mirrors `backfill_theme_axis_shadow`),
then the same stage×outcome cross-tab: does Stage-2+tight-base actually separate fwd-5d outcomes?
If the boost direction is contradicted at N≥30, the table changes before exposure.

## Mechanics, guardrails, rollout — inherited from ADR 0015 verbatim
Pure `structure_axis_credit(features) -> {credit_steps, marker, reason}`; shadow-only logging
beside the live label; the judge unchanged; stacking caps across #328/#330/#331 are #329's call
(proposed default: **max +1 step TOTAL across all axes** until #329 decides); flip =
CHANGE_PROCESS + N≥10 divergences + operator labels. THE LINE: no detection gate, no threshold,
no live grade changes on any agent authority.

## Rollout
1. Operator signs the component table (with/after the 0015 sitting — same Saturday block).
2. ~~STEP-0 structure backfill on the 452-row cohort + cross-tab (read-only).~~ ✅ done 7/4
   (`docs/analysis/structure_axis_step0_2026-07-04.md`) — boost direction not contradicted at
   the only adequately-powered read (N=386 relaxed variant); proceeded to shadow build.
3. ~~Shadow build (Sonnet card, the 0015 shadow's sibling — one session).~~ ✅ shipped:
   `agents/market_intelligence/structure_axis_shadow.py` (+ `mi_structure_axis_shadow` table,
   `db.get_daily_bars_asof` accessor, wired into `ep_detector.py`'s `_judge_shadow` beside the
   #328 theme-axis shadow). Full write-up: `docs/setups/meta_rubric.md` §Structure axis.
   `stage2_only_near_miss` ships at 0 credit in v1 (documented implementation call, not in the
   ADR's literal text) — see the SSoT doc for the STEP-0 evidence behind that call.
4. Composition + flip at the #329 checkpoint.
