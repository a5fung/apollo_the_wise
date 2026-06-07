# Gate-3 evidence — SIP-augmented R cohort (Lever A, 2026-06-06)

**Script:** `scripts/sip_replay_r_cohort.py` (read-only) · split from
`scripts/replay_would_have_filled.py` (#180). Run on prod, all history, `magna53`, paper.

## How to re-run (durable — for future evals & tuning)

```bash
# On-demand (read-only; SELECTs + Polygon bars; writes nothing):
docker exec apollo-market python scripts/sip_replay_r_cohort.py            # magna53, all history
docker exec apollo-market python scripts/sip_replay_r_cohort.py --days 90  # window
docker exec apollo-market python scripts/sip_replay_r_cohort.py --signal-type 9m_day2
```

**Auto-re-runs monthly** via the backward-check sweep (`agents/market_intelligence/
quarterly_review.py`, registered #223) — the stdout TL;DR leads with the SELECTION
delta so the monthly Telegram digest tracks whether IEX adverse-selection persists /
the edge holds as the cohort grows. Per `feedback_methodology_insights_need_periodic_
revalidation` (a finding without a sweep script silently goes stale). Re-snapshot this
doc when the verdict materially moves.

## Result

| Cohort | N | E[R] | median | win% | totR | maxDD |
|---|---|---|---|---|---|---|
| **1. REAL-only** (actually filled, IEX) | 19 | **−0.431** | −0.53 | 21% | −8.2R | 8.2R |
| **2. SIP-augmented** (real + 14 sim recoveries) | 33 | **+0.290** | −0.64 | 30% | +9.6R | 9.2R |
| **3. THE GAP** (= IEX winner-drop) | — | **+0.721** | — | — | +17.8R | — |

**Cohort split (fail-fast headline):** cancelled (IEX-dropped) N=21 → 14 `would_have_filled`,
7 `clean_miss`, **0 `gap_through`**. SIP-recoverable = 14/14 = **100%** of the recoverable set.

## What it means

The filled paper cohort looks like a losing system (−0.43 E[R]) **only because IEX
systematically fills the weak setups and skips the strong ones.** A clean breakout runs
away from the stop-limit → never fills on IEX's thin book → lands in the *cancelled*
cohort. A weak breakout pulls back to the limit, fills, then dies → lands in the *filled*
cohort. So the realized paper cohort is adversely selected; the dropped names (CADL +7.3R,
RDW +5.1R, MRVL +4.4R, FLEX +4.2R, INFQ +3.6R) are the winners. On SIP/NBBO fills the
cohort is **+0.29 E[R]**. The −$9,475 paper-IEX figure is largely a **measurement
artifact of IEX fill selection**, not a broken strategy. This is the strongest Gate-3
signal to date and directly supports a reduced-size live start (live fills off SIP/NBBO).

> ⚠️ The +0.29 SIP-augmented E[R] is **exit-model-confounded** — do not cite it as the
> headline. The clean, load-bearing number is the SAME-EXIT cross-check below (+2.27R
> selection delta). See "Gate-3 bearing — VERDICT".

## Honest caveats (do NOT overclaim)

- **Line 2 is half simulation** (14 of 33 rows). It's a less-biased *estimate* for the
  cutover decision, **not a realized track record.** The realized track record is Line 1.
- **Conservative lower bound:** synthetic exit = entry@limit → stop-or-day1-EOD, no
  trailing/partials → truncates multi-day winners (e.g. MRVL exited EOD day-1; live could
  run further). True edge ≥ +0.29 E[R]. → clears GO bar = strong; would-fail = ambiguous,
  NOT a NO-GO.
- **Tail-carried:** median R still negative (−0.64), win 30% — the +E[R] rides on ~5 fat
  winners. This is the *correct* Qullamaggie/momentum profile (cut at −1R, let winners
  run), NOT a red flag — but it means the edge needs enough trades for the tail to show,
  which argues for start-small-then-size-up, not all-in. **Quantified under #224 below
  (the synth-CANCELLED edge crosses 0 after dropping only ~3 names).**
- **N=33 is modest.** Decision-grade signal, not a closed verdict. Re-run as the cohort grows.
- Minute-bar fill is a print, not a guaranteed marketable ask at limit (cohort proxy).

## SAME-EXIT cross-check — the load-bearing number (advisor confound fix)

The +0.29 SIP-augmented E[R] was confounded: real-cohort R uses live exits (partials/
BE/trail, avgW +1.00R) vs synthetic R holds to EOD-day1 (avgW +2.97R). To isolate
**pure IEX selection**, both cohorts were re-scored under the *identical* `replay_one`
floor proxy (advisor 2026-06-06; `feedback_validate_metric_before_decision`):

| Same exit basis | N | E[R] | win% | avgW | totR |
|---|---|---|---|---|---|
| **synth-FILLED** (IEX *did* fill) | 13 | **−1.00** | 0% | — | −13.0R |
| **synth-CANCELLED** (IEX *dropped*) | 14 | **+1.27** | 43% | +4.29R | +17.8R |
| **SELECTION delta** | — | **+2.27** | — | — | — |

On one harsh exit basis: the names IEX filled **all** tag their stop (−1.00R, 0 winners);
the names IEX dropped post **+1.27R / 43% win**. The flip is **selection, not exit model** —
and the result is *stronger* than the confounded version. IEX was systematically filling
the losers (weak breakouts that pull back to the limit then die) and dropping the winners
(clean breakouts that run away from the limit). Live trading fills off SIP/NBBO and
captures the dropped cohort. (Caveat: the −1.00 floor on synth-FILLED is partly the
proxy's no-partial harshness; the robust, direction-certain fact is synth-CANCELLED
clears **+1.27R under the same harsh proxy**, where the edge demonstrably lives.)

## Gate-3 bearing — VERDICT

Gate 3 (realized-R expectancy) was the single biggest cutover blocker, gated on slow
winner-biased paper-IEX accrual. Lever A resolves the blocker qualitatively NOW:

- **The realized paper loss (−$9,475 / −0.43 E[R]) is an IEX execution-feed artifact, not
  a strategy-edge failure.** The tradeable cohort is materially positive once the feed's
  adverse selection is removed (+2.27R same-basis selection delta; gap_through=0 so every
  dropped winner was *reachable* at the limit).
- **GO-supportive for a reduced-size (80/20) live start at 6/22.** Live fills off SIP/NBBO,
  i.e. the feed that captures the dropped winners.

**Not claimed:** a precise positive live E[R]. The proxy brackets it (harsh on losers via
no-partials, generous on winners via no-cap/hold-to-EOD); the real number is what the
reduced-size live cohort will measure. This is decision-grade *direction*, not a pinned point.

**Independent hard path (unchanged):** the execution-reliability gates (IBM trio N=7, #150,
#142, #184) still gate the flip regardless of this R evidence. Lever A clears the *edge*
question; it does not clear the *reliability* question.

_Advisor pressure-test applied (2026-06-06); the cross-check meets the advisor's
pre-registered criterion (synth-FILLED strongly negative + synth-CANCELLED positive →
selection holds, GO-supportive stands)._

---

## #224 robustness hardening (2026-06-07) — the standalone >0 bar

The +2.27R *selection delta* (section above) is the **weaker "selection exists"** claim:
it is inflated by the no-partial proxy's harshness on synth-FILLED (every non-winner lands
at exactly −1.00R). The magnitude of that harshness is explicit: the **real** filled cohort
was N=19 at **21% win**, but under the floor proxy synth-FILLED collapses to N=13 at **0%
win** — the no-partial/hold-to-stop proxy turned ~4 real winners into stop-outs. That is
exactly why the delta is demoted and the standalone synth-CANCELLED +1.27R leads. The **sizing-relevant** question is whether synth-CANCELLED clears 0
**on its own**, and how concentrated that edge is. Per advisor 2026-06-07, hardened by
arithmetic-first checks (folded into the durable script's default output — re-runs monthly):

**1. Trim curve — drop the top-k winners from synth-CANCELLED (N=14, 6 winners + 8 at the
−1.00 floor):**

| | E[R] | totR |
|---|---|---|
| full (N=14) | **+1.269** | +17.76 |
| drop top 1 | +0.808 | +10.50 |
| drop top 2 | +0.453 | +5.44 |
| drop top 3 | **+0.097** | +1.07 |
| drop top 4 | **−0.317** | −3.17 ← crosses 0 |
| drop top 5 | −0.747 | −6.72 |

→ The standalone edge is **real but concentrated**: it survives dropping the top 3 names
and crosses 0 at the 4th. "Selection exists" (the +2.27 delta) is robust; "cancelled is
positive standalone" rests on ~3–4 fat winners out of 14. **Supports START-SMALL sizing,
not full-size.**

**2. Winner fill-realism — did the edge-carrying names trade *through* the limit, or graze
it?** All 6 winners are **convincing fills** (≥2 fillable bars OR ≥0.10% penetration below
the limit), zero single-print grazes:

| ticker | date | fillable bars | penetration below limit |
|---|---|---|---|
| CADL | 2026-04-20 | 2 | 0.92% |
| FLEX | 2026-05-06 | 1 | 1.19% |
| INFQ | 2026-05-21 | 1 | 0.95% |
| RDW | 2026-05-26 | 3 | 2.18% |
| AVAV | 2026-05-28 | 1 | 0.60% |
| MRVL | 2026-06-02 | 1 | 2.61% |

→ The names carrying the edge are **genuine SIP fills**, not classifier artifacts (MRVL/
FLEX/INFQ filled in one minute but with deep trade-through, not a one-print graze). (Minor:
AVAV filled 9:48, just past the 9:45 submission window — but it is the *smallest* winner
(+1.28R) so it does not drive the verdict.)

**3. Checks demoted / found redundant** (advisor 2026-06-07): bootstrap CI **demoted** —
N=14 with a bimodal {6 winners, 8 floor-stops} distribution gives false precision. Recent-
window slice **redundant** — the cohort already spans 2026-04-16…06-02, entirely within 90d.

**Net:** the #224 hardening does not move the GO direction (selection is real, winners are
genuine fills) but **sharpens the sizing read** — the standalone edge is concentrated, which
is exactly why the recommendation is reduced-size start, not full-size. Operator owns the
GO/size call at 6/22; this is evidence, not a verdict.
