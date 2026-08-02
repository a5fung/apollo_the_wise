# CHANGE PROPOSAL — require the ≥10% move to SUSTAIN before real-time admission (#490)

**Status: DRAFT, awaiting operator sign-off. Nothing built, nothing flipped.**
Per `docs/setups/CHANGE_PROCESS.md`. SSoT to update in the same commit: `docs/setups/magna53_ep.md`.

---

## 1. Trigger

Operator, 2026-08-02: *"target should be stable, in fact just a single 1min bar touching >10% may be
too lose especially for premarket, maybe we should see that move sustain with a few bars."*

The trigger is not a backtest result. It came from reading two cases:
- **MYGN 07-30** — operator: *"I don't see >10% except for on specific 1min bar and it crashed back
  down immediately, so this is a good avoid, especially knowing next day it dropped 46%."*
- **QURE 07-29** — touched 12.3% inside the 09:30 bar, closed it at 9.7%, decayed all morning. The
  residual metric counts that as a missed catch. It is not: declining a level that never held is
  correct behaviour.

## 2. The argument this proposal rests on — mechanism, NOT the return table

⚠ **The operator named the central risk himself: *"this is selecting criteria based on hindsight of
wins."*** He is right, and this proposal is deliberately structured so that concern cannot be
hand-waved.

**The case for the change is a priori and does not need the outcome data at all:**

> A price level that holds across three consecutive minutes is a **level**. A level touched in one
> minute and gone is a **print**. Pre-market especially, a single thin print can carry a 1-minute bar
> through 10% with no participation behind it. Detection samples every 5 minutes and acts at 09:31
> on a stop-buy — it needs the level to still be there, not to have been there.

That argument stands on its own. It is the same reasoning already embedded in the existing Q3
minute-bar corroboration guard, applied one level up: Q3 asks *"is this print real?"*, this asks
*"is this LEVEL real?"*

**The outcome table is used ONLY as a safety check** — to confirm the change does not destroy
something valuable — **not to select the rule.** That distinction is the whole answer to the
overfitting objection.

**Two pieces of evidence that the pattern is not curve-fit:**
1. **It reverses.** 5-of-10 and 7-of-10 are *worse than doing nothing* (+0.2% median close, 20% win).
   A curve-fitting exercise produces a monotone "stricter is better" story. A reversal is a
   mechanism: past ~3 bars you stop requiring persistence and start requiring the move to be *old*,
   which selects for stale moves with nothing left.
2. **Risk improves alongside return.** Median open→low goes −1.7% → −1.2%. A rule fitted to wins
   typically buys return with drawdown. This does the opposite, which is what a genuine noise filter
   looks like.

## 3. Evidence (CHANGE_PROCESS r1 — N≥10; we have 97)

`scripts/probes/_490_sustain_rule.py`, all 97 `ep_rt_universe_catch` events, day-level outcomes.

| rule | admits | med open→close | med open→high | med open→low | win ≥+5% |
|---|---|---|---|---|---|
| 1 bar (today) | 81 | +3.9% | +9.8% | −1.7% | 41% |
| 2 consecutive | 67 | +4.0% | +10.0% | −1.7% | 45% |
| **3 consecutive** | **46** | **+5.0%** | **+10.4%** | **−1.2%** | **50%** |
| 2 of last 3 | 71 | +4.0% | +9.8% | −1.7% | 45% |
| 3 of last 5 | 50 | +4.1% | +10.0% | −1.4% | 48% |
| 5 of last 10 | 26 | +3.0% | +9.3% | −2.1% | 38% |
| 7 of last 10 | 10 | +0.2% | +5.9% | −2.8% | 20% |

**Consecutive beats M-of-N at equal strictness** (3-consecutive 46/+5.0% vs 3-of-5 50/+4.1%;
2-of-3 ≈ 2-consecutive). Allowing gaps dilutes exactly the property being tested. **So the M-of-N
family the operator asked to test is measured and NOT recommended.**

**Honest limits, stated not buried**: n = 46-81; **seven rules compared** = real multiplicity, so any
single cell could be noise; 5 shadow days = one regime; day-level open→close is **not** what an ORB
entry with an ORB-low stop captures.

## 4. THE FORK FOR THE OPERATOR — 2 bars or 3?

This is the one genuine decision, and it is precisely where the overfitting risk bites.

| | 2 consecutive | 3 consecutive |
|---|---|---|
| admits | 67 of 81 (drops 14) | 46 of 81 (drops 35) |
| good names dropped (≥+5%) | 3 | 10 — incl. **RACC +31%**, the cohort's best |
| measured improvement | small | larger |
| **overfit exposure** | **low** — barely tuned, closest to "more than one bar" | **higher** — 3 is the argmax of the table |

- **2 consecutive is the CONSERVATIVE choice**: it captures the a priori argument ("more than a
  single print") with the least dependence on which number scored best, and it forgoes only 3 good
  names.
- **3 consecutive is the MEASURED optimum**, and its reversal-shaped curve is real evidence — but
  choosing it *because it topped the table* is the exact selection-on-hindsight the operator flagged.

▶ **Recommendation: 2 consecutive.** It is the version whose justification survives even if the
outcome table is entirely noise, and it costs 3 names instead of 10. If forward data reproduces the
3-bar edge, tightening later is cheap; un-dropping RACC-class names after the fact is not.

## 5. Implementation (if signed)

Backward-looking only: at the detection tick, require the last N in-hold minute bars to close ≥
`MIN_GAP_PCT`. **No forward wait** — that would push detection past the 09:45 ORB cutoff and recreate
the miss #490 exists to fix. Bars are already fetched for Q3, so there is no new I/O.

⚠ **Pre-market sparse bars are the operator's own flagged case and need an explicit rule.** SCL had
no bar at all at 09:30. Proposal: judge the window on the bars that EXIST, and require at least 2
real bars before the rule can reject — otherwise "3 consecutive" silently becomes "reject everything
pre-market", which is a bigger change than the one being signed.

Toggle-gated (`ep_rt_sustain_bars`, default 1 = today's behaviour), so reversion is a value change
with no deploy.

## 6. Pre-committed forward check — the real answer to overfitting

Because the selection risk cannot be argued away, it gets measured:

1. **First 30 live catches under the rule**: compare their outcome distribution against the replay's
   prediction. Materially worse ⇒ the replay was fitted, revert to 1.
2. **Log what the rule REJECTS** (`ep_rt_sustain_reject`, named + deduped) so dropped names stay
   auditable. A rule whose rejects are quietly invisible cannot be judged later.
3. **One occurrence of a rejected name running ≥+20% is a review; two is a revert.**

## 7. What this does NOT do

It does not make the strategy profitable, and it is not a fix for entries or exits. It reduces noise
admitted at detection. The shadow ORB control still shows zero winners across bull and correcting
months with no broker involved — that problem is upstream of this and untouched.
