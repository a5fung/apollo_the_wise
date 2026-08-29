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

## The recommendation

**Revert the extension cap to 50%** — and treat that as the small half of the finding.

**What reverting costs, measured:** 18 names blocked over 5 months, 3 of which reached +20% on paper. All three stopped out at −1R on real bars. **Under the bracket that existed, the band returned −1.00R on 15 of 15.** There is nothing there to lose.

**What it does not fix, and this is the real finding:** five names in that band ran 2.9R to 15.2R and every one paid −1R, because the 9:30 bar's low was taken out first. **The cap is not the binding constraint — the stop is.** Reverting stops us paying −1R to discover that; it does not make the cohort tradeable. The lever is bracket geometry (#482, now un-blocked with 55 closed shadow trades), not admission.

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

**Under the bracket that actually existed at the time — 15 of 15 stopped out. −1.00R every
single one. Zero winners.**

The +2R half-off rule shipped 2026-08-16, *after* every name in this cohort. Applying it anyway
lifts the cohort to **−0.60R** with three "winners" at +1.00R — but those three are
**constructed by that assumption, not observed**: SILC, WSHP and UBXG each touched +2R and are
scored as half-banked. No trade in this cohort ever ran under that rule.

| replay | n | winners | expectancy |
|---|---|---|---|
| **the bracket as it was** (plain ORB) | 15 | **0** | **−1.00R** |
| with the +2R rule applied retrospectively | 15 | 3 (constructed) | −0.60R |

**The band is not worth admitting on either basis**, and that verdict does not depend on the
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

⚠ **Scope check:** this replay is the **50–75% band only** — every name in it had run 50–75%
in the prior five days, which is exactly what the cap change admits. The nine winners that had
run 128%+ are excluded because the change never touches them.

⚠ **Four method errors were made and corrected before this number** — the fourth was dropping
UBXG, whose `ret_5d` was NULL in the table, from the first replay list. — the first pass ignored
that the stop stays live past day 0 (losers averaged an impossible −1.43R), and the second
ignored **order**, marking a name that ran +3R at 10:00 and drifted back at 15:00 as a flat −1R
(it produced a suspicious 14-of-14 stop-out). The figure above is the order-aware run.

## What this does not answer

- **n=15 is small.** Zero observed winners is a clean result, but it is fifteen names. The direction is clear and the mechanism is
  visible in the MFE column, but this is not a distribution.
- **The +2R half-off rule is applied as designed, not as it behaved.** No live trade in this
  cohort ever ran; the rule shipped 2026-08-16, after every name here.
- **Whether the cap belongs at some other number.** Nothing between 50 and 75 was tested; the
  cohort is bad throughout, so no threshold in that range looks defensible on this data.
- **Live effect since 08-21.** Eight days, no admitted-and-traded name yet.
