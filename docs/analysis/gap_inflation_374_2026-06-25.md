# #374 STEP-1 — EP pre-market gap inflation: frequency + impact (2026-06-25)

**Trigger:** SNX 6/25 stored a 11.22% gap (helping it reach HIGH) off an implied ~$315 pre-market
price that was outside its 280–296 range both days; the real open gap was ~0%. Operator asked: how
often does a thin/unrepresentative pre-market print inflate the gap, and does it tip names into HIGH?

## How the gap is measured (why this happens)

`gap = (current − prevDay.c) / prevDay.c` (`collector.py`), where `current` = the latest pre-market
minute-bar close / last trade, snapped at **detection time** (EP scan runs 7–10 AM, mostly pre-open).
The gap then feeds MAGNA53 directly — **gap magnitude is worth up to 25 of ~100 points**
(`ep_detector.py:902-911`). So one bogus or unrepresentative pre-market print sets the gap AND the
score. Pre-market detection is *by design* (catch the gap before the 9:31 ORB), so the fix can't just
be "use the open" — it must protect legit early gappers.

## Frequency (HIGH alerts since 2026-05-01, stored gap vs actual open gap)

| metric | count | % of HIGH |
|---|---|---|
| HIGH alerts (with open + prev-close data) | 342 | — |
| stored gap inflated **> 3%** vs open gap | 49 | **14%** |
| stored gap inflated **> 10%** vs open gap | 18 | **5%** |

It is **not rare** — ~1 in 7 HIGH alerts carries a pre-market gap meaningfully above what actually
opened, and 1 in 20 by >10%.

## Two regimes (the guard must distinguish them)

Worst inflations:

| ticker | date | stored | open | inflation | read |
|---|---|---|---|---|---|
| WEST | 05-08 | 41.2 | 16.4 | +24.7 | faded, still a big gap |
| IMVT | 05-20 | 35.3 | 15.8 | +19.5 | faded, still big |
| AXTI | 05-01 | 16.8 | **−0.5** | +17.3 | **VANISHED** — opened flat/down |
| DYN | 05-20 | 17.9 | 1.6 | +16.2 | **VANISHED** |
| QURE | 06-17 | 75.2 | 61.4 | +13.8 | real — 61% is still a monster |
| MLTX | 06-22 | 19.1 | 4.2 | +14.9 | mostly vanished |

- **Real-but-faded** (QURE 75→61, WEST 41→16): the pre-market gap was real; it cooled but the name
  still gapped hard. A HIGH here is arguably correct.
- **Gap-VANISHED** (AXTI 16.8→−0.5, DYN 17.9→1.6): the stored gap is essentially fiction at the open —
  these are the false HIGHs. This is the operator's SNX class (a real but unrepresentative thin print).

## Impact — does the inflation COST us? NO (this reverses the hypothesis)

Forward 5-day returns by inflation bucket (HIGH alerts since 5/1, n_sessions_5d ≥ 4):

| bucket | n | avg fwd_5d | win rate |
|---|---|---|---|
| inflated > 10% | 13 | **+12.0%** | **100%** |
| inflated 3–10% | 30 | +9.5% | 90% |
| normal (≤ 3%) | 232 | +10.4% | 92% |

The inflated-gap HIGHs do NOT underperform — the >10% bucket wins MORE than normal. The pre-market
gap, even when it fades by the open (AXTI 16.8 → −0.5), still captures real catalyst energy that
plays out over 5 days; the names recover/run. So the "inflation" is **not a P&L problem.**

## Conclusion — DON'T build the detection guard

The outcome data flips STEP-2. A guard that filtered/down-weighted the inflated-gap HIGHs would
**remove winners** (the >10% bucket is +12% / 100%). The gap LOOKS wrong but trades RIGHT — this is
exactly the case the backtest-before-deploy discipline exists to catch.

- **Detection / score: leave the pre-market gap as-is.** No guard, no CHANGE_PROCESS change. (Small
  samples 13/30 add caution, but the direction is clearly not-worse — there is no edge to recover by
  guarding, and real downside in losing the faded-but-running names.)
- **Display only (safe, no detection change):** the operator's *confusion* was real — optionally show
  both the stored gap and, once available, the open gap, so a faded pre-market reading (the SNX
  thread) doesn't mislead. That's the only fix worth considering, and it's display, not strategy.

**STEP-1 + impact: DONE. Recommendation = NO detection guard (it would cost winners); at most a
display tweak. Operator call.** Re-open only if a larger sample changes the bucket comparison.
