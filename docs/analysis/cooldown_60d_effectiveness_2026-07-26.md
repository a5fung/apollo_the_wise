# 60-day EP cooldown — effectiveness measured (2026-07-26)

**Verdict: WORKING AS DESIGNED. No change warranted. Do not re-litigate off the
should've-entered list — that list is peak-ranked and shows the right tail by construction.**

**Trigger**: the 2026-07-26 weekly review's "should've-entered gaps (30d)" put the 60-day cooldown on
5 of 8 rows, including FCEL +88%, FCEL +48%, AEHR +39%, AEHR +22%, SLS +19%. I initially called it
"the single largest source of missed upside." Measured, that framing was wrong.

## Mechanism

`ep_detector.EP_COOLDOWN_DAYS = 60` — *"Skip if this ticker had an EP **alert** in last 60 days."*
It arms on a prior **alert**, not a prior **position**. Since most alerts never become positions
(filtered, skipped, cancelled, out-of-window), the cooldown mostly blocks names we never held:
**92 of 104 blocks (88%) are on tickers with no filled/closed trade.**

That looked like a defect. It isn't — the outcomes settle it.

## Outcomes (`mi_ep_missed_outcomes`, skip_reason ~ cooldown, `ret_5d`)

| population | n | mean 5d | median 5d | winners | best |
|---|---|---|---|---|---|
| **held before** (the designed target) | 12 | **−14.4%** | −11.2% | **0 of 11** | −3% |
| **never held** (the 88% collateral) | 92 | +1.0% | **−1.3%** | 42 of 91 | +56% |

**On its target population the cooldown is near-perfect: zero winners in eleven, averaging −14.4%
avoided per instance.** A name that already ran and that we already traded does not run again inside
60 days — the gate is correctly refusing to chase.

**On the collateral it is a coin flip**: +1.0% mean against a −1.3% median, 46% winners. The positive
mean is a thin right tail (best +56%); the median name goes slightly nowhere. Loosening the gate would
buy that tail and pay for it with the other 54%.

## Why the review made it look worse than it is

`should've-entered` ranks by **peak missed upside**. Any gate's worst-looking cases are its right tail
by construction — the list cannot show you the 50 names the same gate correctly declined, because
those have no upside to rank. **Reading a peak-ranked list as an effectiveness measure is selection
bias.** The same caution applies to the "Missed Opportunities / by skip reason" block: `peak = max
intraday high over 5 days` is an upper bound nobody could have captured, not an achievable return.

## What would change this verdict

- The `held before` cohort turning positive (would mean re-entries are now working) — n=12, worth
  re-checking as the live cohort grows.
- A material shift in the never-held median away from ~0.
- Evidence that the tail is *identifiable in advance* — e.g. if the +56% and +88% cases share a
  feature the gate could condition on. That is the only version of "loosen the cooldown" that is not
  just buying variance. Not investigated here.

## Method

Read-only prod SELECTs. `held` = `mi_live_trades` with `status IN ('filled','closed')` — deliberately
NOT any row, because cancelled/skipped rows are not positions (AEHR 2026-07-15 was broker-rejected and
never held, yet its alert still armed the cooldown). `ret_5d` is close-basis and therefore understates
intraday excursions — see the #503/#306 cross-basis finding; it is directionally fine for a
population comparison but should not be read as achievable P&L.
