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

## ⛔ AND THE SECOND RECOMMENDATION FAILS TOO — he asked what its effect would be, and I had not checked

*"Confirm on time: two consecutive weeks before a cohort is presented as a theme."* Measured on the
same post-launch population, 142 cohorts that reached the board:

| | count | share |
|---|---|---|
| **GOOD — suppressed forever** (held exactly one week, never returned) | **66** | **46%** |
| **BAD — survivors delayed** (held 4+ weeks; 23 of them held 2 straight) | 29 | 20% |

**The cost, for the 23 survivors: they arrive one week late, and during that wait their rank moves a
median of −3 (UP the board), with 57% improving.** So the rule works as a noise filter — and it
makes you a week late on exactly the cohorts that turn out to matter.

🔴 **That is fatal, and for a reason already on the board.** A week is five trading sessions, and
**#486's step-3 read — which he ALIGNED ON 2026-09-07 — is that naming five sessions EARLIER lifts a
theme's remaining runway from 29% to 55%.** A two-week confirmation spends precisely that, in the
wrong direction, on the 20% of cohorts worth having. The rule trades away the thing the theme
programme exists for in order to tidy a display.

## ✅ The recommendation that survives: do not delay, LABEL

Present everything immediately, and show what is known about it: **"week 1" versus "held N weeks"**
on the board itself. The 46% one-week cohorts become visibly provisional instead of being hidden a
week; the 20% that matter are on the board the day they arrive, at full earliness; and the reader
does the discounting with the fact in front of him rather than the engine doing it for him.

It is also the same correction as every other one in this file's week: **two different facts — "new
and unproven" and "held for a month" — currently render identically**, and the fix is to stop
rendering them identically, not to suppress one of them.

⚠ **Recorded because I recommended the time rule BEFORE measuring it**, and he asked for the effect.
Both the size floor and the confirmation delay read as obviously right and both fail on the numbers.

## ⛔ THE THIRD RECOMMENDATION FAILS AS WELL — he said *"check your rec again before presenting it"*

*"Label each cohort with how long it has held a slot"* only works if that number PREDICTS anything.
It does not. Given a cohort has held N consecutive weeks post-launch, the chance it holds the next:

| held | 1 wk | 2 wks | 3 wks | 4 wks | 5+ wks |
|---|---|---|---|---|---|
| holds next week | 52.0% | 54.8% | 62.2% | 50.0% | 57.9% |
| n | 150 | 73 | 37 | 22 | 19 |

**Flat, near a coin flip, at every history length.** A label carrying a number that does not
discriminate is decoration, and printing it would imply a confidence the data does not support.

**Three recommendations, three failures — size floor, time confirmation, and now the label.** Each
read as obviously right. What they share is that all three tried to fix the BOARD.

## 🔑 What the flat line actually says

Board membership is close to memoryless: whether a cohort is in the top 30 next week is ~55%
regardless of everything it has done so far. **That is not a display problem and no rearrangement of
the display touches it.** It says presence in an `rs_avg`-ranked top 30 is not a signal you can act
on — which is a statement about the RANKING AXIS, not about churn.

And that lands on something already established rather than something new: the north star is that a
theme is real when it shows up in the strongest names FIRST, measured by **subtle RS — rising,
rising faster, and holding up better on the market's down days**. Checked again today: `get_rs_velocity`
(db.py:9411) and `get_rs_turners` (db.py:9779) cover the first two. **Down-day resilience still does
not exist anywhere in `agents/` or `shared/`** — the one leg #486's plan named as genuinely new, and
still the one missing.

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
