# catalyst_type forward signal + unknown-rate KPI — answered (2026-08-03)

**Review:** `data_gated_reviews.yaml::catalyst_type_forward_signal` (added 2026-05-30, predicate
fired 47/20). **Read-only. Nothing changed.**

Cohort per the review's own rule: HIGH alerts, `catalyst_type IS NOT NULL`, **`alert_date >=
2026-06-02` only** — pre-date rows are hindsight-labelled and would be lookahead
(`feedback_backfill_llm_label_lookahead`). Returns are **beta-stripped**: excess vs QQQ over the
same 5 sessions, because the review already proved raw return is bull-confounded (2026-05-30).

## (a) Forward signal by catalyst type

| catalyst_type | n | median excess vs QQQ | win rate | median raw |
|---|---|---|---|---|
| **sales_acceleration** | **31** | **+8.53%** | **90%** | +8.01% |
| policy | 7 | +6.83% | 100% | +3.58% |
| theme | 4 | +27.38% | 100% | +26.51% |
| pre_catalyst_anticipation | 2 | +6.27% | 50% | +1.13% |
| shortage | 2 | +2.93% | 50% | +2.95% |
| new_product | 1 | +4.86% | 100% | +1.69% |

**Only `sales_acceleration` is populated enough to read** (n=31). Everything else is n≤7 and is
reported for completeness, not for inference. `theme`'s +27% on n=4 is a curiosity, not a finding.

### The 90% win rate — checked for the obvious ways it could be fake

- **Selective outcome computation?** No. Of 67 typed HIGH alerts, 20 have no forward row and **all
  20 are dated 2026-07-27 or later** — they have not settled yet. The cut is purely temporal, so
  the analysis cohort (through 7/24) is unbiased *within its window*.
- **Bull-market confound?** Handled by construction — this is excess vs QQQ, and the excess median
  is slightly ABOVE the raw median, so the market was not doing the work.
- **What is NOT ruled out:** a momentum-factor tailwind across Jun–Jul that QQQ does not capture,
  and a single-window sample. This is one two-month regime.

## (b) The unknown-rate discovery KPI — the metric does not exist as specified

**The classifier never emits `unknown`.** Distribution over all 81 HIGH alerts since 6/02:
`sales_acceleration` 48 · **NULL 14** · `policy` 8 · `theme` 5 · `shortage` 2 · `new_product` 2 ·
`pre_catalyst_anticipation` 2 — and **zero literal `'unknown'`**.

The gap appears as **NULL**, which conflates two different things the review wanted separated:
"classifier ran and genuinely found nothing" versus "classifier never ran or failed". As written,
the unknown-rate KPI is unmeasurable — the same shape as the `phase3_telemetry_coverage_check`
defect found earlier today.

**The coverage question itself is nonetheless answered, and the answer is good:**

| month | untyped | total HIGH |
|---|---|---|
| 2026-06 | 14 | 43 |
| 2026-07 | **0** | 36 |
| 2026-08 | **0** | 2 |

All 14 untyped fall in **2026-06-02 → 06-05**, the first four days after the 5/30 ship. **Coverage
has been 100% since 6/06.** This was a rollout tail, not an ongoing discovery gap, so the
`->#149` coverage-failure branch does not fire.

## The finding that matters most, and it is not in the review's questions

`sales_acceleration` HIGH alerts show **+8.5% median 5-day excess at a 90% win rate**, while the
live traded record over an overlapping period is **0-for-9** (#503).

Those are not in conflict — they measure different things. This is **close-to-close on the ALERT**;
#503 is **entry-and-stop on the TRADE**. The same split appeared in the conviction-floor review
closed earlier today (five of six names closed green but stopped out intraday).

**Read together: selection looks healthy and execution does not.** That points at entry timing and
stop geometry, not at what we are choosing to alert on — which is where #508 and the operator's
stated priority already point. Offered as a pointer, not a conclusion; proving it needs an
entry-basis comparison on the same cohort.

## Recommendation

- **Close the review.** Both halves are answered: (a) measured and beta-stripped; (b) coverage is
  100% since 6/06 and the `unknown` label does not exist.
- **Do not act on the per-type numbers yet.** One populated cell, one regime window. The review's
  step 4 (feed `catalyst_type` into `phase5_meta_rubric_calibration`) is the right next home for it,
  and that is a scoring change = CHANGE_PROCESS + sign-off.
- **Worth fixing separately:** have the classifier emit an explicit `unknown` rather than NULL, so
  "found nothing" and "did not run" stop being the same value.
