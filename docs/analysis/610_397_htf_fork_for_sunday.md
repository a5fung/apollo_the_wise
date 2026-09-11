# HTF — one decision, for Sunday 2026-09-13

⛔ **FRAMING CORRECTED 2026-09-11, by the operator, and it changes what this page is asking.** His
words: ***"we aren't trading it, we already discussed this over and over, it's a setup we trying to
detect and get right."***

**HTF IS A DETECTION PROBLEM, NOT A MONEY PROBLEM.** The question is whether our detector finds the
setup correctly — not whether trading it pays. Trading it is gated behind EP profitability anyway
(`priority-ep-profitability-before-new-setups`), so a capture rate cannot decide anything here.

**What that does to the replay's number:** 25 of 148 reaching +3R before −1R measures an ENTRY and
an EXIT we are not proposing to use. It is evidence about a bet nobody is placing. It becomes
relevant to detection only in one direction — **if our detector were finding the right setups, a
reasonable entry on them should not be this bad** — and even that reading is blocked by the two
instrument defects below.

**So the decision is: what do we do to get the DETECTOR right.** The options are re-framed on that
axis.

## ⛔ And it goes further than that — HTF is not yet a setup at all

Operator, same turn: ***"we also haven't figured out optimal entry and exit, sizing, etc etc for
HTF."***

CLAUDE.md's own definition: **a SETUP is a named entry with a DEFINED BUY POINT AND STOP. If you
cannot state where it buys and where it stops, it is not a setup.** HTF has neither settled. So the
replay did not test "HTF as written today" — **it tested HTF with a placeholder entry (`base_high`
on the break day), a placeholder exit (+3R/−1R) and no sizing work at all.**

**That is why the capture number cannot carry any weight: R itself is measured against a stop nobody
chose.** Change the stop and every number on this page moves, including the 25% breakeven, because
the breakeven is a property of the bracket rather than of the setup.

**What HTF has today is a detector for a chart CONDITION.** The entry, the exit and the sizing are
unstarted work, and they come after the detector is right — not alongside a graduation decision.

## ⛔ And the metric is backwards for an asymmetric setup

Operator, same turn: ***"similar to with EP, it's asymmetric meaning lower winrate but outsized
winners, at least that's the ideal goal."***

**A +3R/−1R bracket CAPS every winner at +3R.** If the edge is a low hit rate with outsized winners,
that bracket truncates precisely the thing being looked for — and then the measurement reports a low
hit rate as failure, which is what a low-hit-rate setup looks like when it is working.

**So "25 of 148 reached +3R" is not a weak result. It is a measurement taken through an instrument
built for the opposite shape of edge.** A 25% breakeven only applies if every win is exactly 3R and
every loss exactly 1R — the assumption an asymmetric setup violates by design.

**What would actually measure it:** the distribution of maximum favourable excursion — how far the
winners ran when they ran, and what share of total return the top few produced — not a hit rate
against a fixed target. [[measure-the-tail-not-the-median]] · this is the same lesson as the live
book, which reaches +1.8R on average and keeps −0.4R.

⚠ **This compounds the point above rather than replacing it.** The stop was never chosen, AND the
target caps the winners. Two invented parameters, and the metric derived from them decides nothing.

## Method and population

**Rows:** `mi_htf_breakout_shadow` breakouts with a SETTLED outcome — **n = 148** — replayed from
stored minute bars under the rules as written today, not from historical trade rows. Full method and
the per-row table: `docs/analysis/610_htf_replay_2026-09-10.md`.

**Entry** = `base_high` on the break day. **Management** = the shipped fixed +3R / −1R bracket.
**Capture** = the share of breakouts that reached +3R before −1R; **25%** is the breakeven for that
bracket, since 3:1 payoff needs one winner in four.

## What was measured

**148 settled breakouts. Capture 16.9% (25 of 148) against the 25% breakeven.** On that population,
under that entry and that exit, the bet loses.

## What that number is, and is not

⚠ Your own correction, 2026-09-10: *"htf as written today may have no edge, not that htf as a setup
have no edge."* The replay tested **our encoding plus one exit bet**:

| tested | NOT tested |
|---|---|
| our candidate definition | the HTF pattern itself — a sourced, externally established setup |
| entry at `base_high` on the break day | anticipation inside the base, or a post-break pullback |
| the shipped fixed +3R / −1R bracket | the #396 management protocol |
| | whether our detector admits the right names — `htf.md` calls the ADR floor a starting value and the flagpole ratio one interpretation of several |

## Two defects in the instrument that produced the number

1. **Impossible fills.** The recorder credits fills at prices that could not have been had.
2. **Split drift.** The shadow stores raw prices; `mi_daily_closes` is retro-adjusted. Any join
   across a split is nonsense — **already 1 of 16 rows** (CDLX traded 185–194 that week; `mi_splits`
   confirms a 1:4 on 2026-07-02).

## The fork

| | what it means for DETECTION | what it costs |
|---|---|---|
| **A — park #397** | stop spending on the money-graduation thread; it is gated behind EP anyway | nothing is lost — the detector work continues without it |
| **B — fix the recorder, then re-measure** | the outcome join becomes trustworthy, so it can at least be used as a weak sanity check on whether we are finding the right names | a day or two |
| **C — go at the detector directly** | the ADR/ADV floors cut breakouts 91% (#610's own finding) and `htf.md` calls the ADR floor a starting value and the flagpole ratio one interpretation of several — measure what those admit and reject against sourced HTF examples | the real work, and the only option that answers the question he is actually asking |

## My recommendation: C, with A alongside it

**C is the only one that answers the detection question.** The 91% collapse in breakouts came from
two liquidity floors shipped as provisional and never measured — that is a detector defect sitting
in plain sight, and it is upstream of every number on this page.

**A alongside it** because the money-graduation thread cannot decide anything while HTF sits behind
EP, and leaving it open invites exactly the category error this page just had to correct.

**B only if the outcome join is wanted as a sanity check** — it is worth doing, but it is not on the
critical path to a better detector.

⚖ This is your call, not mine, and nothing has been flipped or changed while it waits.

## What this does not answer

- **Whether the HTF pattern has an edge.** It tested our encoding plus one exit bet, on names our
  detector admitted. If the definition is wrong, the number describes our filter.
- **Whether a different entry works** — anticipation inside the base, or a post-break pullback.
  Neither was replayed.
- **Whether the 16.9% is even measured correctly.** Two defects sit in the measuring path (above),
  and that is the whole reason option B exists.
- **Anything about the detector's admission bar.** The ADR and ADV floors that cut breakouts 91%
  (#610's own finding) are upstream of this population — these 148 are what survived them.
