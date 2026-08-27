# The Perplexity agreement boost: no measured support, and one confound that explains most of it

**Date:** 2026-08-27 (PT) · **Task:** #233 · **Mechanism:** `confidence_multiplier = 1.2` when
Perplexity's catalyst grade matches the Claude grader's · **Status:** measured. Retiring it is a
scoring change = THE LINE, so this is a recommendation.

---

## What the boost is

`ep_detector.py` sets `confidence_multiplier = 1.2` when Perplexity's grade equals the Claude
grader's, and passes `regime_multiplier * confidence_multiplier` into `_score_ep`. A 20% score
increase, purely for two models agreeing. It fires on **61 of 147** alerts in the last 60 days
and on 140 of 419 alerts with the field populated.

⚠ Until today the alert footer described Perplexity as *"second opinion, sets nothing"*. That
was wrong: this boost, plus the hedge-text downgrade (10 firings since 2026-05-05), are both
live effects. Fixed the same day.

---

## ⚠ Read the metric correctly

`mi_ep_scan_outcomes.fwd_5d_pct` is **maximum favourable excursion**, not a return:
`(highest high over the next 5 sessions − day-0 close) / day-0 close`. It is positive for almost
every row by construction. **Any "N up / 0 down" tally on this column is meaningless** — I ran
one before checking and it read 18-for-18, which measures nothing. Group *averages* remain
comparable; win rates do not.

---

## What the data says

All alerts with the field populated (2026-05 → 2026-08-21, n=419; 373 have a forward window):

| | alerts | avg 5-day MFE | avg gap | avg score |
|---|---|---|---|---|
| boost 1.2 (Perplexity agreed) | 140 | **9.17%** | 15.5% | 76.4 |
| boost 1.0 (disagreed) | 279 | **11.20%** | 18.8% | 66.8 |

Restricted to HIGH alerts — the ones that can be traded — the direction holds: **9.70% vs
11.14%**. Agreement on its own, ignoring the multiplier, points the same way: **8.97% agreed vs
11.53% disagreed**.

**But the confound is large and visible in the table above.** The boosted group gaps 15.5% versus
18.8%, and MFE scales with gap size. So the boosted names run less far substantially *because
they are smaller movers* — which is exactly what the boost is doing: lifting smaller-gap names
over the bar via a 20% score increase.

**Controlling for it — same score band, boosted vs not:**

| score band | boosted (n, MFE) | unboosted (n, MFE) |
|---|---|---|
| 42–55 | 40 · 6.3% | 64 · 9.8% |
| 55–69 | 25 · 10.1% | 44 · 12.4% |
| 70–84 | 23 · 11.4% | 76 · 11.6% |
| 86–96 | 13 · 12.7% | 41 · 10.5% |

Worse in two bands, level in one, better in one. **Within band, there is no signal.**

---

## Conclusion

**The boost has no measured support.** The raw comparison leans against it; the controlled
comparison is a null. It is a 20% score increase applied for a reason nothing has validated —
two models agreeing is not evidence a catalyst is better, and on this data it is not even
correlated with a bigger move once score is held constant.

**Recommendation: retire it** (`confidence_multiplier` fixed at 1.0), and keep Perplexity as the
recorded second opinion it is already labelled as. That is a scoring change, so it is the
operator's under THE LINE. #233 also pairs this with repositioning Perplexity as a labelled
recency source — unchanged by this finding.

---

## What this does not answer

- **Every alert here predates the 2026-08-22 rescale.** No post-rescale alert has a five-day
  window yet, so the score bands above are on the old scale and the era-scoped cut is empty.
  Re-run this once ~30 post-rescale alerts have matured.
- **MFE is not R.** It ignores the stop and the entry, so none of these numbers say what we
  would have made. They rank how far a name ran, nothing more.
- **Whether retiring the boost changes the alert set** is not measured here — that needs a
  re-score of the same cohort at 1.0 against the current bar, which the rescale makes a separate
  piece of work.

---

# Addendum — the better question: can a second model catch ERRORS?

Operator, same day: *"i'm not too concerned about boost giving us better winrate, where i see
potential value is perplexity or any 2nd model giving us validation vs catching potential
errors, can it do that?"*

That is testable now, because `judge_grade` was backfilled today — so three independent reads
of the same catalyst exist on one row: the **Claude grader's label**, **Perplexity's grade**,
and the **judge's own read**.

**Test:** treat the judge's disagreement with the label as the thing worth catching. Does
Perplexity's disagreement predict it? n = 174 alerts carrying all three.

| | judge agrees with the label | judge disagrees |
|---|---|---|
| **Perplexity agrees** | 71 | 16 |
| **Perplexity disagrees** | 58 | **29** |

- **Base rate:** the judge disagrees on 45 of 174 = **26%**.
- **When Perplexity disagrees:** 29 of 87 = **33%**.
- **When Perplexity agrees:** 16 of 87 = **18%**.
- **Recall:** Perplexity flags **29 of the 45** the judge flags = **64%**.
- **Precision:** of the 87 it flags, 29 are also judge-flagged = **33%**.

**And when both flag the same alert, they agree on WHICH WAY 25 times out of 29 — 86%.**

Direction is consistent too: both critics lean toward the label being too generous.
Perplexity says lower on 62 and higher on 25; the judge says lower on 35 and higher on 10.
Perplexity simply flags about twice as often.

## What that means

**Yes — but as an early warning, not a verdict.** Perplexity disagreeing roughly doubles the
odds that a second, better model also disagrees (33% vs 18%), and when both do they nearly
always point the same direction. It is far too noisy to act on alone: it flags half of all
alerts and two thirds of those flags are not corroborated.

That is exactly the shape #233 part (a) already proposes — feed the Claude-vs-Perplexity
**disagreement** into the judge as a labelled signal, rather than paying a blind 20% score
increase for agreement. **The boost and the error-check are two different uses of the same
comparison, and only one of them has evidence behind it.**

## ⚠ The confound that limits this

**The judge is not ground truth** — it is another model, and a check of one model against
another is not a check against reality. Worse for independence: the judge already reads
Perplexity's `[Web summary]` TEXT (this is exactly what #233 part (a) notes it does *not* read
the grade). So some of the 64% overlap may be shared input rather than independent
corroboration, which would inflate every number above. Sizing that would need the judge re-run
with Perplexity's text withheld — a paid eval, not a free join, and not run here.
