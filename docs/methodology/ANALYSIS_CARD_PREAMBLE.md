# Read this before any analysis. Every card gets it verbatim.

**Why this file exists.** Operator, 2026-08-30: *"can you just internalize the goal and purpose
and not needing me to correct you every time you do an analysis, this is wasting so much time."*
He is right, and the same corrections kept recurring — leading with win rate, testing one entry
and calling it research, running against remembered state, omitting the buy and the stop. A
standard I re-remember per card is a standard that drifts. **This file is pasted into every
analysis card so it cannot be forgotten by whoever writes the prompt, including me.**

---

## THE GOAL — everything below serves this

> **Make EPs profitable: filter the universe on all the factors that matter, not just a gap, so a
> small win rate is carried by winners large enough to give positive expectancy.**

**The number: ~4 converted tail winners over 4½ months — roughly one a month.** At a ~20% win
rate with 1R losers, **the average winner must exceed 4R just to break even.**
**Win rate and reward are ONE target, never two.**

## HOW TO RANK ANY FINDING — in this order, always

1. **RECALL — how many REAL EPs does it catch AT ALL?** (**P1**: a real EP must never be missed.)
   With 1–3 real EPs a quarter, one missed name is a material fraction of the whole objective.
   A method that performs beautifully on 6 names and never fires on the other 49 has failed the
   thing that matters most. Report the count, the share, and **which names it never catches**.
2. **EXPECTED RETURN** — total R and R per event, including the cost of every failed attempt.
   Mean AND median, n on every figure. *"It's not just ratio of winners to losers... more
   important is the expected return, how much we lose with the loser and how much we win with
   winners and is that outcome positive."*
3. **CAPTURE** — of the move that was actually available, how much did we take?
4. **THE TAIL (P3)** — how many reach **4R+**? Hunt the tail, not the average.

## ⚖ WIN RATE — WHICH LAYER OWNS IT (operator 2026-08-30)

> *"win rate is not unimportant, but that is where the filters and ranking come in; buy/sell
> points cannot control winrate."*

**Win rate is a SELECTION measure, not an entry/exit measure.** Which names you take decides how
often you are right; where you buy and sell decides how much you make when you are. So:

| you are evaluating | is win rate a criterion? |
|---|---|
| **filters, ranking, admission, the score** — *which names* | **YES, and a legitimate one.** Judge it in BOTH directions (P14): a filter that lifts win rate by admitting fewer real EPs has failed. |
| **entry, stop, management, re-entry** — *where you buy and sell* | **NO.** These cannot move it, so ranking tactics by it measures the cohort you happened to feed them, not the tactic. Report it as a descriptive column and rank on expected return, capture and the tail. |

⚠ **The common error is applying the wrong one** — reporting an entry tactic's win rate as though
the tactic earned it, or judging a selection change purely on expectancy while its recall quietly
falls. Name the layer you are evaluating before you pick the measure.

A 20% win rate is fine here when the winners are large enough; a high win rate built on small
wins is a worse outcome, not a better one — **but that is an argument about how to READ win rate,
never a reason to stop measuring it.**

## THE FAILURE MODES ARE NOT SYMMETRIC (P14)

- **Admit too much** → overwhelmed. Grading budget, five position slots and his attention are all
  finite. **Visible**: more alerts, more noise, more losers.
- **Admit too little** → the edge is gone. **INVISIBLE** — no row, no skip reason, no trace.

Every instinct and every metric pulls toward tightening, because over-admission is the one you
can see. **So report recall AND cost together, every time. One without the other is not
evidence.**

## THE RULES THAT KEEP GETTING RE-LEARNED

- **Run `scripts/live_rules.py` first and read it before any doc.** Docs go stale; it is generated
  from code and prod. An analysis attributing a result to a rule we deleted is worthless, and that
  has happened.
- **The population IS the analysis.** Most errors are population errors, not arithmetic ones —
  the arithmetic is right about the wrong rows. Era, admission era, live-vs-paper, dead
  strategies, and whether the source table is itself sound.
- **State the BUY and the STOP.** If you cannot, it is a FAMILY, not a setup — and say so.
- **Test the whole campaign, not one shot.** Entries, stop-outs, re-entries, management, exits.
  *"Your analysis is just a lazy one try and done. We are trying to do real research here."*
- **Outcome-conditioned populations flatter everything.** If names are in the set partly because
  they worked, say so **against every headline**, not once in a footnote.
- **Retract, don't patch a fourth time.** A population defect survives any re-run.
- **Dead strategies are not evidence** — check `mi_strategies.enabled/phase` first.
  `9m_day2`, `fishhook_v3`, `flag_continuation` are deprecated.

## ⚖ THE LINE

Strategy, entry/exit discipline, sizing, targets and safeguards are the **operator's sole
authority**. Analysis produces evidence and recommendations. It never flips anything.

## OUTPUT

`docs/methodology/analysis_standard.md` §6 — the decision it serves, method and population,
the numbers with n, **what this does not answer**, and THE LINE where relevant. Gate 6 enforces it.
