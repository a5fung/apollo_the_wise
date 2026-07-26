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

---

## Addendum — the "is the tail identifiable in advance?" question is already instrumented, and the answer so far is NO

Above I said the only honest path to loosening the cooldown is evidence the tail is identifiable
ex-ante, and that it was "not investigated here." **It is already instrumented** — `#170` emits
`cooldown_resetup_admit_shadow` for suppressed candidates that look like RE-SETUPS (hard gap + weeks
since the prior alert). It is telemetry-only and fail-open: the candidate stays suppressed live, the
shadow just accrues the cohort. 139 raw events since 2026-06-02, which is **11 distinct ticker-days**
(events fire per 5-min scan tick — do not read the raw count as the sample).

**Discrimination test — do re-setups beat the rest of the cooldown-blocked pool?**

| cohort | n | mean 5d | median 5d | winners | best |
|---|---|---|---|---|---|
| RE-SETUP (hard gap + weeks since) | 11 | **−3.9%** | +1.3% | 6/11 (55%) | +14% |
| other cooldown-blocked | 91 | −0.3% | −2.6% | 36/91 (40%) | **+56%** |

**Mixed, and the mean goes the wrong way.** Re-setups win on median (+1.3% vs −2.6%) and win-rate
(55% vs 40%), but LOSE on mean (−3.9% vs −0.3%), dragged by RUM −25.3%, BTGO −19.3%, RLAY −15.4%.

**The decisive point: the criterion misses the tail it would need to justify itself.** FCEL's +88%
(2026-06-26) is not in the re-setup cohort at all; the FCEL re-setup it did capture (07-14) returned
+2.1%. The best re-setup was ORKA +14.2% — against +56% available in the general pool. So the
criterion is not selecting for the big movers; it is selecting a slightly-higher-median,
worse-mean subset.

**Verdict: do not admit the re-setup class on this evidence.** n=11 is too small for a real verdict
and the shadow keeps accruing for free — but the direction is not encouraging, and "higher median,
worse mean, misses the tail" is the profile of a criterion that adds variance without adding edge.

**The bar for revisiting:** the re-setup cohort beating the rest on BOTH mean AND median at n≥30 —
the same both-measures rule the ORB-cutoff review uses, and for the same reason (one or two tail
anecdotes must not carry the decision).

Data note: `RLAY 2026-06-02` appears twice in `mi_ep_missed_outcomes` — duplicate rows, immaterial
here (both −15.4%) but worth knowing if that table is used for counting.
