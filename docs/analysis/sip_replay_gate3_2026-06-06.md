# Gate-3 evidence — SIP-augmented R cohort (Lever A, 2026-06-06)

**Script:** `scripts/_sip_replay_r_cohort.py` (read-only) · split from
`scripts/replay_would_have_filled.py` (#180). Run on prod, all history, `magna53`, paper.

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
  which argues for start-small-then-size-up, not all-in.
- **N=33 is modest.** Decision-grade signal, not a closed verdict. Re-run as the cohort grows.
- Minute-bar fill is a print, not a guaranteed marketable ask at limit (cohort proxy).

## Gate-3 bearing

Gate 3 (realized-R expectancy) was the single biggest cutover blocker, gated on slow
winner-biased paper-IEX accrual. Lever A replaces that with a less-biased SIP estimate
available NOW. **Reading: GO-supportive for a reduced-size (80/20) live start at 6/22**,
conditioned on the execution-reliability gates (IBM trio N=7, #150, #142, #184) — which
are independent and remain the hard path. Pending advisor pressure-test before it's filed
as the formal Gate-3 verdict.
