# #639 — the top-30's weekly churn: real rotation, or the engine losing identity?

**2026-09-11. $0 — a read of the canonical weekly grid the dashboard already computes.**
Probe: `portfolio-app2/_639_churn_split.py`. Read-only.

## Method and population

**Rows:** `theme_data.get_canonical_weekly_grid()` — **1,814 cohort-week rows across 25 weeks,
2026-03-30 → 2026-09-07**, restricted to rows carrying a non-null `week_rank` (rows without one are
not on any board and cannot enter or leave it).

**Board** = `week_rank <= 30` in that week. **Entrants** = canonical ids on this week's board that
were not on last week's. Classification is applied to entrants only, in this order: RENAMED (basket
overlaps a cohort on LAST week's board at Jaccard ≥ J under a different id) → REAPPEARED (basket
overlaps ANY basket in ANY earlier week, at any rank) → RETURNED / PROMOTED (same id seen before) →
NEW (neither id nor basket seen). Ticker sets come from the grid's own `tickers` column.

**Headline window: post-launch only — the 11 transitions AFTER 2026-06-22, 152 entrants.** The
2026-06-22 week is excluded as an era boundary, not as an outlier: it is the launch, 24 of 30 slots
turned over, and none of the 24 matched anything historical. Pre-launch weeks are reported in the
per-week table for completeness and are not in any percentage.

**Sensitivity:** every headline is given at J = 0.50, 0.60 and 0.75 rather than at one threshold,
because the conclusion should not rest on a number I chose.

## The question

Between a third and two thirds of a 30-slot board is a name that was not there seven days earlier,
every week for two months. The DoD demanded the SPLIT, not the percentage: is an entrant genuinely
new — its tickers never together on the board under any name — or an existing cohort wearing a
changed name?

## The answer: renaming is NOT the cause, and that is settled

Post-launch (the 11 transitions after 2026-06-22), **152 entrants**:

| class | J=0.50 | J=0.60 | J=0.75 |
|---|---|---|---|
| **NEW** — basket never seen, any week, any rank | 98 (64%) | 107 (70%) | 115 (76%) |
| **REAPPEARED** — the basket WAS on the board before | 53 (35%) | 44 (29%) | 37 (24%) |
| **RENAMED** — same basket, different id, last week | **1** | **1** | **0** |

**RENAMED is one entrant in eleven weeks, at every threshold tested.** Identity instability is not
what is churning the board. #476 and #471 were the right suspects and they are cleared.

## ⚠ Two corrections the first run needed

1. **Last week is not enough.** The first version compared an entrant's basket only against the
   PREVIOUS week's board. It scored 2026-06-22 as 24 entrants, ALL new, and RENAMED fell to zero
   from that week onward — the signature of a canonical-id reset, not of rotation. Every basket is
   now checked against every basket ever seen, at any rank, in any earlier week.
2. **2026-06-22 is an era boundary, not a data point.** It is the launch. 24 of 30 slots turned
   over in one week and matched nothing historical. Averaging across it measures two systems.
   Everything above is post-launch only.

## 🔑 But the finding underneath is the one that matters

**71% of the "genuinely new" entrants carry three tickers or fewer** (median 3), against 39% of the
reappearing ones (median 4).

| class | n | median basket | ≤3 tickers | max |
|---|---|---|---|---|
| NEW | 107 | 3 | **76 (71%)** | 59 |
| REAPPEARED | 44 | 4 | 17 (39%) | 19 |
| RENAMED | 1 | 2 | 1 | 2 |

**So the board churns because it keeps admitting tiny, freshly-assembled baskets** — not because
existing themes are being renamed.

⚠ **AND MY OWN MEASUREMENT IS WEAKEST EXACTLY WHERE THE MASS IS.** A 2-ticker basket sharing one
ticker with a prior 3-ticker basket scores Jaccard 0.25 and reads NEW. At these sizes "new" and
"unrecognised" are not separable by ticker overlap, so **63-70% is an UPPER bound on novelty**, not
a measurement of it. The task line already warned about this from the other direction.

## ⛔ The obvious recommendation is WRONG, and the data says so

The reading above invites "raise the membership floor — stop letting two-ticker cohorts hold board
slots". **I checked before recommending it, and it does not survive.** Post-launch, for every cohort
that reached the board, how long did it hold a slot:

| first reached the board post-launch | n | median weeks held | gone after one week | held 4+ weeks |
|---|---|---|---|---|
| **≤3 tickers** | 92 | **2** | 40 (43%) | 21 (**23%**) |
| **4+ tickers** | 50 | **1** | 26 (52%) | 8 (16%) |

**Small cohorts persist slightly BETTER, not worse.** Basket size does not predict staying power, so
a size floor would remove the tiny cohorts *and* the ones most likely to stay — while trading away
early detection, which is the entire point of the engine (a theme is supposed to show up in the
strongest names FIRST, and it has few members when it does).

**What the table actually shows is size-independent: roughly half of everything that reaches the
board is gone a week later — 43% and 52%.** That is the churn, and it has nothing to do with how
many tickers a cohort carries.

**RECOMMENDATION: do not filter on size. Confirm on time.** A cohort has to hold a top-30 slot for
two consecutive weeks before it is presented as a theme rather than a candidate. That removes about
half the churn by the board's own numbers, costs nothing in detection (the cohort is still tracked,
just not promoted), and makes no judgement about basket size — which is the judgement the data
refuses to support. ⚖ His call; it is a board-composition rule, not a matcher change.

⚠ **Limits, because n is small:** 92 and 50 cohorts, one post-launch quarter, and "weeks holding a
slot" is a proxy for value, not value itself. It is enough to REFUSE a size floor. It is not enough
to assert that small cohorts are better, and this doc does not.

## What this opens, and whose call it is

The honest next question is not about the matcher at all: **should a two- or three-ticker cohort
occupy a slot on a thirty-slot board?** Most of the churn is those slots turning over. That is a
board-composition rule — ⚖ **HIS call, not a matcher fix**, and this analysis produces evidence for
it rather than proposing a change.

## What this does not answer

- **Whether a "genuinely new" basket is a genuinely new THEME.** It measures ticker-set novelty on
  the board, nothing more. At a median of three tickers those are not the same statement.
- **Whether the market actually rotated.** This reads board membership, never returns. A board that
  churns and a market that rotates are different claims and only the first is measured here.
  [[themes-not-judged-on-returns-yet]]
- **Whether the canonical matcher is CORRECT.** It shows renaming is not driving churn. A matcher
  that wrongly SPLITS cohorts would produce exactly this picture too — which is why the ≤3-ticker
  concentration above is flagged as the weak spot rather than treated as settled.
- **Anything about the apollo-side theme engine.** This is the dashboard's own canonical grid, a
  separate code path, as #553's own line insists.
- **Pre-launch behaviour**, deliberately excluded above.
