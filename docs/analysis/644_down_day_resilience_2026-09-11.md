# #644 — down-day resilience: the measure, and the test it was built for

**2026-09-11. $0 — one read-only prod pull (psql, captured once) plus the dashboard's own
canonical weekly grid (portfolio-app2, local, no DB). Read-only throughout.**

## The decision this serves

#639 (`docs/analysis/639_board_churn_split_2026-09-11.md`) killed three recommendations for the
theme board's weekly churn — a basket-size floor, a two-week confirmation delay, a weeks-held
label — each looked right and each failed a follow-up query. What survived is that **board
membership in the `rs_avg`-ranked top 30 is close to memoryless**: given a cohort has held N
consecutive weeks, the chance it holds the next is 52.0% / 54.8% / 62.2% / 50.0% / 57.9% at
N=1/2/3/4/5+ — flat, ~55% overall, regardless of history. That is a statement about the ranking
axis (`rs_avg`), not about churn, and it points at the operator's own north star for what should
rank instead: *"may not have highest RS but rising, rising faster, and/or holding up better in
market down days."* `get_rs_velocity` and `get_rs_turners` already cover "rising" and "rising
faster." **Down-day resilience — "holding up better" — did not exist anywhere in `agents/` or
`shared/` before this.** #644's PLAN.md line is explicit that the measure is not the deliverable:
*"compute down-day resilience as of each cohort's first board week, then ask whether a week-1
cohort with positive resilience holds its slot at a rate materially above the 55% base rate...
WOULD-FAIL-IF: the answer lands inside 50-60%."*

**No wiring is proposed here.** This is evidence only — see ⚖ THE LINE at the bottom.

---

## Step 1 — the measure

`agents/market_intelligence/db.py::get_down_day_resilience(d, tickers=None, lookback=20)`, placed
next to `get_rs_velocity` (rising) and `get_rs_turners` (rising faster) — the third leg of subtle
RS.

```
resilience = median(name's daily return on SPY's down days over the `lookback` sessions before d)
           - median(SPY's own daily return on those same down days)
```

Positive = held up better than the market on the days the market fell.

**AS-OF DISCIPLINE (the whole point):** sessions used are `trade_date < d`, strictly — never
`<=`. This is deliberately NOT `get_rs_velocity`/`get_rs_turners`'s `_resolve_score_date`
fallback (which describes where a stock stands *as of* `d`, falling back to the latest complete
run on/before it). Down-day resilience describes what was already known *walking into* `d` — a
cohort's first week on the board — so `d`'s own session, and anything after it, must never enter
the window. Population: `mi_daily_closes` (SPY + the requested tickers, or every ticker with a
close in the window if `tickers=None`). Returns `[]` if fewer than `lookback+1` distinct sessions
exist before `d`, or if SPY had zero down days in the window; a ticker with zero valid down-day
observations is omitted from the result rather than scored 0.

**Tests:** `tests/test_644_down_day_resilience.py`, 8 tests — hand-computed resilience against a
synthetic calendar, sort order, `tickers=None` vs an explicit basket (incl. a `frozenset`, which
`_tickers()` in the churn-split script actually produces), a ticker with zero down-day coverage
(omitted, not zeroed), partial down-day coverage, insufficient session history, zero down days,
and the as-of leak test.

**The as-of leak test, proved RED:** `test_session_on_or_after_d_never_affects_the_answer` plants
poisoned SPY/ticker rows dated exactly `d` and `d+1` (SPY "crashing" to 5.0, a ticker "mooning" to
5000) into the same fixture and asserts the answer is bit-identical with and without them. To
confirm the test actually catches a leak rather than passing vacuously, the source's `trade_date
< $1` was changed to `<= $1` by hand and the suite re-run:

```
FAILED tests/test_644_down_day_resilience.py::test_session_on_or_after_d_never_affects_the_answer
AssertionError: a row dated on/after d changed the answer — as-of leak
```

Confirmed failing (the poisoned row at `d` entered the window and changed XYZ's resilience from
+0.02 to a different value), then reverted — `git diff` on `db.py` is empty. Full suite after
revert: `tests/test_644_down_day_resilience.py` 8/8 green.

---

## Step 2 — the test

### Method and population

**Board:** `portfolio-app2`'s `theme_data.get_canonical_weekly_grid()`, `week_rank <= 30`, same
source #639 used. **"Week-1 cohort"** = an ENTRANT to `board[w]` relative to `board[w_prev]` —
the exact `entrants = board[w] - board[prev]` #639's own script computes — across the **11
post-launch transitions** (`week_start > 2026-06-22`). This reproduces #639's own published
figure **exactly: 152 entrants.** Each entrant carries its own `as_of_date` (the actual snapshot
date behind that week's ranking, not the Monday `week_start`) and its ticker basket **as observed
at that week** — resilience is computed against the cohort as it looked on the day it entered,
not a later or earlier basket.

**"Holds next week"** = the same `canonical_id` present in `board[w_next]`. Entrants from the
final week on file (2026-09-07) have no next week yet (19 of the 152) and are excluded from the
outcome measure only — **133 scorable.**

**Reconciling against #639's own persistence table (n≈150 at N=1):** this population's hold-next
rate is **69/133 = 51.9%**, essentially identical to the previously-published 52.0%. The count
differs (133 vs ~150) because the ad hoc script that produced that earlier table was never
committed to `portfolio-app2` (confirmed: `git log --oneline --all -- '_639*'` shows only the
entrant-classification script that IS on disk) and is not available to diff against line by line.
**The rate match — not the count — is the check that matters here**: a materially different
population would be very unlikely to land within 0.1 point of an independently-derived figure by
chance. This population is used as defined above, with its own denominator stated on every
number below rather than borrowed from the unreproducible one.

**Resilience:** `get_down_day_resilience(as_of_date, tickers=basket, lookback=20)` — the actual
function above, not a reimplementation — called once per entrant. Prices: one read-only psql pull
(`scripts/probes/_644_closes.csv`, 45,982 rows, 508 tickers incl. SPY, `2026-05-01`..`2026-09-10`,
captured once, 2026-09-11) loaded into a fake connection that honors the same `trade_date < $1` /
`= ANY($n)` filters real Postgres would, wired in for `db.get_pool()` so the code path exercised
is the real one. **Every one of the 91 distinct trading dates in the pull has an SPY row and none
fall on a weekend — no #554-style stray-date contamination in this window.** Checked twice: once
against the 508-ticker pull, and once directly against the full table
(`SELECT COUNT(DISTINCT trade_date) FROM mi_daily_closes WHERE trade_date BETWEEN
'2026-05-01' AND '2026-09-10'` on prod = 91, matching the subset exactly) — the real function's
`SELECT DISTINCT trade_date` scans all ~9,700 tickers, not just the 508 pulled here, so this
confirms the session calendar this doc used is the same one the real function would use in prod.
**All 152 entrants
scored with full basket coverage** (every ticker in every basket had ≥1 valid down-day
observation; median basket size 3, matching #639's own finding for NEW entrants). Cohort
resilience = **median** of its member tickers' resilience (median, not mean, to match the
"median beside mean" standard and because baskets are small — median 3 tickers — where one
outlier member would otherwise dominate a mean).

### The numbers — the specified test

Split at resilience sign (positive vs. non-positive), on the 133 scorable entrants:

| group | n | holds next week | rate |
|---|---|---|---|
| **positive resilience** | 90 | 48 | **53.3%** |
| non-positive resilience | 43 | 21 | 48.8% |

Difference: **+4.5 points.** Two-proportion standard error on this split: 9.3 points. The
difference is **0.49 standard errors** — indistinguishable from noise.

**WOULD-FAIL-IF triggered: 53.3% lands inside the 50-60% band.** This is the fourth idea in this
line of work that read as though it should matter — a stock holding up on the market's down days
in the month before it reaches the board — and does not survive a direct test. Positive resilience
does **not** predict holding the board slot at a rate materially above the ~52-55% base rate.

**The split itself is lopsided, and that is part of the answer, not noise to look past:** 90 of
133 scorable entrants (68%) carry positive resilience — an `rs_avg`-ranked board pre-selects for
names that have generally done well, which naturally includes doing well on the market's down
days, so the sign split starts with little room to discriminate (the small side, 43, carries most
of the statistical uncertainty: its own standard error alone is 7.6 points). For context on the
full 152: 102 (67%) carried positive resilience regardless of scorability — the same skew.

`d = as_of_date` deliberately excludes the snapshot day's own session (strictly `< d`, per Step
1's as-of discipline) — resilience is measured over what was known walking INTO the cohort's first
board week, not including the day the board itself was formed. This is stricter than "everything
the board saw," by design.

### A secondary, exploratory cut — NOT the specified test

Splitting at the **population median** resilience (+0.48%) instead of at zero, to balance the two
sides (66 vs 67, instead of 90 vs 43):

| group | n | holds next week | rate |
|---|---|---|---|
| above median resilience | 66 | 41 | 62.1% |
| at/below median resilience | 67 | 28 | 41.8% |

Difference: **+20.3 points**, SE 8.5 points, **2.4 standard errors** — a larger gap than the
specified test found, and one that would ordinarily be worth a second look. **It is reported here,
not built on.** This cut was planned as a contingency *before* running the primary test, precisely
because a sign split on a population already skewed 90/43 toward positive (see below) has an
unbalanced, lower-powered comparison on the small side — not chosen after seeing the primary
result to go looking for a better one. Even so: one cut, one window, n≈66/67 a side, not corrected
for having looked at more than one split — not enough to promote past "worth another independent
replay before it means anything." **The task's pre-registered test is the sign split above, and
it failed (landed inside 50-60%).** This secondary result does not rescue it.

---

## What this does not answer

- **Whether a DIFFERENT lookback (not 20 sessions), a different aggregation (mean instead of
  median), or a longer holds-next horizon (2+ weeks, not 1) would land outside the null band.**
  Only the specified 20-session/median/next-week configuration was tested, deliberately, to avoid
  searching for a version that works.
- **Whether resilience predicts anything about RETURNS.** This tests board-slot persistence only
  (a display/ranking-axis question), not whether high-resilience cohorts went on to perform
  better as trades. #639's own caveat applies again: themes are not judged on returns yet.
  [[themes-not-judged-on-returns-yet]]
- **Whether the median-split's 2.4-SE gap would replicate on an independent window.** It was
  computed on the same 133 observations as the failed primary test, is a single post hoc cut, and
  is not corrected for having looked at more than one split.
- **Anything about the apollo-side theme engine.** Like #639, this reads the dashboard's own
  canonical grid — a separate code path.
- **Whether the unreconciled n (133 here vs. ~150 in the earlier, uncommitted script) reflects a
  real definitional difference or a lost detail of that script.** The near-exact rate match is
  reassuring but not proof of an identical population.
- **Pre-launch behaviour** (before 2026-06-22), deliberately excluded, matching #639.

---

## ⚖ THE LINE

This is evidence only. `get_down_day_resilience` ranks, scores, admits and alerts on nothing —
it is a read-only accessor next to `get_rs_velocity`/`get_rs_turners`, and this document tests it
against board persistence without wiring it anywhere. Any use of it to rank, score, admit, or
alert is a detection-criterion change and is the operator's call behind CHANGE_PROCESS, not
something this document proposes or decides. Nothing in the trading system changed.
