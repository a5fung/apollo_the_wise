# Track-6 Evidence Pack — the 23 ready/overdue data-gated reviews (prepared 7/3 eve)

Purpose: make the Saturday operator-together block DECIDE-ONLY. Each review: evidence + a
proposed disposition (**the operator dispositions; hard-gate rules #3/#4 bar the agent from
self-classifying filter verdicts**). Live queries run 7/3 ~19:30 PT, read-only.

## Tier 1 — the cutover gates (all three are post-cutover now; the launch happened 6/22-6/28)

**1. `drawdown_breaker_promotion` (GATE 1) — propose CLOSE (completed).**
Live state: `mi_safeguard_state` = **paper=REDUCE, live=OK** — the breaker is ACTIVE, per-mode,
and demonstrably transitions tiers (the 6/5 REDUCE, today's paper REDUCE). It was armed BEFORE
real money per the operator's 6/3 tie-break; the cutover it gated has occurred; tier alerts now
Telegram (6/12 fix) and the transition claim is TOCTOU-proof (7/3). Nothing left to promote.
⚠ Side-fact for the operator: the PAPER account sits in REDUCE (its drawdown tripped the tier —
consistent with the paper-IEX cohort below; live is unaffected, OK tier, full size).

**2. `paper_r_expectancy_validation` (GATE 3) — propose CLOSE (adjudicated by #223).**
Raw query: n=21 closed paper trades since the 5/12 cohort reset, **total −13.54R** (−12.73R over
n=20 after `pnl_attribution` exclusions) — NEGATIVE on its face. But this exact number was
adjudicated at the GO decision: the #223 SIP-replay proved the paper-IEX loss is a FEED ARTIFACT
(selection delta +2.51R; synth-CANCELLED +1.59R/44%; IEX drops the fast clean winners), ratified
GO-supportive 6/19 → launch 6/22. The gate's premise (raw paper R = methodology truth) was
superseded by the SIP-reconstruction standard (`paper_iex_vs_live_sip_gate_adjustment`).
Close with that rationale; the LIVE R-expectancy accrual (#413 lifecycle + kill/scale bands)
is the going-forward measure.

**3. `unified_allocator_phase_1b` (#44) — READY, needs its comparison run (not decide-able tonight).**
Predicate: 20 decided-days ≥ threshold 15 ✓. The evaluation itself (allocator picks vs FCFS
winners, traded-through outcomes only) is a real analysis → propose: Saturday Sonnet card
(read-only cohort study), decision after.

**4. `alpaca_stop_trigger_reliability` (P2) — propose CLOSE + one gated task.**
The 6/3 resolution block already reframed it (order-record-grounded, operator-ratified):
ENTRY-side fill-rate class (stop-limit gap/no-trigger; limit too tight vs SIP), NOT an exit-side
protective-stop failure; exit-side activation is broker-side identical paper/live + covered by
#123 reconcile + never-naked. Disposition: convert to ONE gated entry-tuning task (widen limit /
stop-market-with-chase-cap — CHANGE_PROCESS, composes with #180's would-have-filled classifier)
and close the review.

## Tier 2 — the operator-together investigations (evidence already packed 7/1)
**5. `mna_filter_accuracy_review`** — the 7/1 sweep: SUNE +216% suppressed (+FRMI/ONDS/MMED);
n=48 suppressed cohort in the sweep output; FP/TP = operator labels → then the #410-shipped
pin-guard + any filter amendment go through CHANGE_PROCESS. **6. `mna_filter_direction_blindness`**
— fold into the same sitting (78% of fires matched on the "unknown" path per the 7/1 sweep).
**7. Judge unjustified-demotes** (via the monthly review): HQ +152% etc. — `/why` labeling session.

## Tier 3 — proposed-OBE from the HTF rebuild (the old flag detector no longer exists as reviewed)
**8-11. `flag_proximity_band_calibration` · `flag_ma_pin_filter` · `flag_proximity_bypass_hysteresis`
· `flag_detector_post_breakout_label`** — all four calibrate/label the PRE-#356 50%/60d flag
detector, replaced 6/27 by the sourced HTF (90/40 + ≤25% + Stage-2). #92's sweep verdict
(structural NO-GO: EOD-TRIGGERED is post-hoc) also stands recorded. Propose: CLOSE all four as
OBE, with any still-relevant question re-filed against the HTF/anticipation detectors only if the
operator sees one that carries over. (Deal-pin logic carried into the coil guard 7/3, #410.)

## Tier 4 — runsheet (read each block Saturday; dispositions NOT pre-judged where unknown)
| Review | What I know going in |
|---|---|
| `ep_cooldown_resetup_admission` | = #170's question (in_progress, 7/15) — likely dedup into #170 |
| `theme_engine_narrative_blindness` | Lane-2 #167 shadow is the running answer — likely dedup into #167 |
| `silent_failure_taxonomy` | The #381 gate + ratchet shipped 6/27; batch-1 remediation running tonight — likely close-as-built with #381 carrying the tail |
| `gap_atr_3_5x_band` | 7/1 sweep band data exists (2-3x best 43%, 3-5x 31%) — decide vs the band evidence |
| `nbis_rubric_calibration` | plausibly subsumed by the #329/#335 meta-rubric cluster |
| `fishhook_v3` / `p74_alpha_capture_stage2` / `breadth_cluster_view` / `adv_probe_retirement` / `extraction_pipeline_smoke` / `perplexity_sanitizer` / `gate5h_value_invariant` / `rel_volume_large_cap_floor` / `trade_stream_stop_placement` | read the blocks together Saturday — 30-60s each with the operator |

## Saturday flow proposal
Tier 1 (4 decisions, evidence above) → Tier 3 (one batched OBE call) → Tier 2 (the labeling
sitting) → Tier 4 (rapid block-reads). Target: all 23 dispositioned in ≤1 hour.
