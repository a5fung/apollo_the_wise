# The extension-cap loosening, re-run on corrected data

**Date:** 2026-08-29 (PT) · **Task:** #577 / #595 follow-up · **Status:** read-only re-run. No
change proposed. The cap is operator-signed and live; this restates its evidence, nothing else.

**Why:** the 50% → 75% extension cap was signed on 2026-08-21 — one of only two admission
loosenings ever shipped — on evidence drawn from `mi_ep_missed_outcomes`. #595 established that
**43% of that table's `extension_gate` "winners" were never setups at the open.** So the
headline the decision rested on needed re-checking.

---

## The headline, corrected

| | claimed on 08-21 | corrected |
|---|---|---|
| blocked rows | 179 | 179 |
| winners the gate cost us | **21** | **12** |
| of those, never a setup at the open | — | **9** |

The number was overstated by nearly half. But that is not the finding.

## The finding: only 3 of the 12 real winners are in the band the change admits

The loosening moved the cap from 50% to 75%, so it admits names that had run **50–75%** in the
prior five days. Nothing else changes. Of the 12 genuine winners the gate blocked:

| ticker | date | had run | 5d return |
|---|---|---|---|
| MXL | 04-24 | 59% | +43% |
| ERNA | 05-07 | 64% | +37% |
| AKTX | 05-22 | 68% | +35% |
| AKAN | 04-23 | **226%** | +286% |
| DFNS | 07-28 | **236%** | +131% |
| WETO | 08-17 | **128%** | +172% |
| ASTC | 05-28 | **506%** | +77% |
| SDOT | 06-08 | **345%** | +64% |
| AKAN | 04-29 | **438%** | +59% |
| PIII | 05-19 | **157%** | +58% |
| PN | 07-24 | **151%** | +57% |
| AIOS | 05-01 | **2,264%** | +57% |

**Nine of the twelve had run 128% or more — they are still blocked at 75%.** The change recovers
**three names in four months**, and the biggest winners in the list (+286%, +172%, +131%) are
untouched by it.

## What the admitted band actually contains

All real setups that had run 50–75%, with a scored 5-day outcome:

| | |
|---|---|
| names admitted | **17** |
| big winners (≥+20%) | **3** |
| up / down | **4 / 13** |
| average 5-day return | **−15.3%** |
| **median** | **−21.7%** |

**The band the loosening opens loses 22% at the median and goes down three times out of four.**
Above 75%, what stays blocked is no different: n=74, median −33.0%. The gate is not
discriminating badly at 50 — the whole extended cohort is bad, at every level.

Across all 87 blocked real setups: average −14.7%, median −31.3%, 18 up against 69 down.

---

## What this means

**The loosening was signed on a number that was 43% inflated, and it buys 3 winners against 13
losers in the band it opens.** That is not a claim it was wrong — the operator signed it knowing
the evidence was thin (the doc it rested on says *"the only recoverable winner with minute bars
(MXL 04-24) fills at −1R"*), and conversion, not admission, was always the open question.

But the case for it is weaker than it looked on 08-21, and it is the only live change any of the
#595-affected analyses produced.

⚖ **Admission is entry discipline — THE LINE.** Reverting to 50% is the operator's call and is
NOT proposed here. What this document does is put the corrected numbers in front of him.

## Expectancy in R — the operator's question, answered on real minute bars

He pushed back on the win-rate framing: *"it's not just ratio of winners to losers... more
important is the expected return, how much we lose with the loser and how much we win with
winners and is that outcome positive."* Right — and the missed-outcomes table cannot answer it,
because its returns carry **no stop**: a −57% row reads as a catastrophe when the live bracket
would have closed it at −1R.

Only 2 of the 17 had minute bars stored, so the cohort was fetched from Alpaca and replayed
through the live bracket: **entry = stop-buy at the 9:30 bar's high, stop = that bar's low**,
walked minute by minute in sequence, with the +2R half-off rule (shipped 2026-08-16) applied.

**Result: −0.71R per trade.** 14 triggered and scored (3 never traded through the ORB high),
2 winners at +1.00R, 12 losers at −1.00R.

**The band is not worth admitting.** That answers the question, and it does not depend on the
win-rate framing at all.

### But the reason is not that these names don't move

| ticker | best it reached | what we'd have made |
|---|---|---|
| AKTX | **+15.2R** | −1R |
| HCAI | +5.3R | −1R |
| SILC | +4.0R | **+1R** |
| WYHG | +3.4R | −1R |
| ERNA | +3.3R | −1R |
| WSHP | +3.1R | **+1R** |
| BRUNW | +2.9R | −1R |

**Five names ran 2.9R to 15.2R and still paid −1R**, because the 9:30 bar's low was taken out
first. The cohort moves; our bracket gets shaken out of it before it does.

That is a **geometry** finding, not an admission one — the same conclusion #482/#468b reached
independently (*"a 1-min-range stop shakes out winners"*), and the same thing the original 08-21
document said in its own caveat: *conversion, not admission, decides whether a recovered winner
pays*. Loosening the cap admits names our stop cannot hold.

⚠ **Three method errors were made and corrected before this number** — the first pass ignored
that the stop stays live past day 0 (losers averaged an impossible −1.43R), and the second
ignored **order**, marking a name that ran +3R at 10:00 and drifted back at 15:00 as a flat −1R
(it produced a suspicious 14-of-14 stop-out). The figure above is the order-aware run.

## What this does not answer

- **n=14 is small.** Two winners is two names. The direction is clear and the mechanism is
  visible in the MFE column, but this is not a distribution.
- **The +2R half-off rule is applied as designed, not as it behaved.** No live trade in this
  cohort ever ran; the rule shipped 2026-08-16, after every name here.
- **Whether the cap belongs at some other number.** Nothing between 50 and 75 was tested; the
  cohort is bad throughout, so no threshold in that range looks defensible on this data.
- **Live effect since 08-21.** Eight days, no admitted-and-traded name yet.
