# #595 — Two thirds of our "missed winners" were never setups

**Date:** 2026-08-29 (PT) · **Task:** #595 · **Trigger:** the operator, 2026-08-25, looking at a
name we had ranked as a big miss: *"i don't see gap on 7/8."*

He was right, and the problem is larger than the one row.

---

## The case

**VEEE, 2026-07-08.** `mi_ep_missed_outcomes` credited it **+354% over 5 sessions** and ranked it
among our biggest misses.

| | |
|---|---|
| what the SCAN saw | gap **16.5–20.8%** (three ticks), skipped `adv_too_low` |
| what actually happened at the bell | prior close 5.63 → **open 5.86 = +4.1%** |
| that day | closed **4.64, −21%** |
| where the +354% comes from | **2026-07-13** — open 12.24 against a 4.82 close, three sessions later and a different event |

**The arithmetic was never wrong.** `ret_5d` correctly measures the 5th session's close against
the day-0 open. The premise was wrong: 07-08 was not a setup. The scan saw a **pre-market print
that faded before the open**, and the forward window then ran from that open and swept up an
unrelated move.

## The scale

Every row in the table, open-basis gap = (open − prior close) / prior close:

| | rows | of which ranked "big winners" (≥+20%) |
|---|---|---|
| **did not gap at the open — not a setup** | **2,654** | **203** |
| gapped ≥9% at the open — a real setup | 1,366 | 128 |
| no bar — unscoreable | 2 | 0 |

**66% of the table, and 61% of the ranked winners, sit on days with no setup at the bell.**

Worst offenders — the biggest credited moves on days that never gapped:

| ticker | date | opened | that day | credited 5d |
|---|---|---|---|---|
| VEEE | 07-08 | +4.1% | −20.8% | **+354%** |
| XNDU | 04-13 | +4.8% | +22.4% | +194% |
| POEL | 05-04 | +7.9% | −12.3% | +193% |
| HQ | 06-15 | +6.5% | +53.4% | +187% |
| CUE | 04-30 | +1.2% | +12.0% | +172% |
| JLHL | 04-29 | **−3.4%** | +34.5% | +114% |

JLHL opened **down**. It was ranked as a winner we missed.

## The fix

The same test the operator applied to the sustain rule two days earlier — *"those stocks that we
turned away has to be theoretically traded before we count them"*.

- **`open_gap_pct`** and **`setup_at_open`** are now written on every row, derived from the prior
  session's close (strictly earlier — no lookahead) against `MIN_GAP_PCT`, **imported** from
  `ep_detector` rather than restated, so the flag cannot answer by an obsolete floor (it moved
  10.0 → 9.0 on 08-19).
- **The row is still written.** A pre-market print that faded is real telemetry about our own
  scan; suppressing it would be the same mistake pointing the other way. What changes is that it
  **no longer ranks** — `/scanned` prints what the name did and then says *"but no setup at the
  open (+4%), not ranked"*.
- **NULL means not computed** — every pre-existing row, and any with no prior bar. Those keep
  ranking exactly as before. Treating NULL as "no setup" would have silently emptied the
  rankings the moment this shipped; a mutation test pins that specific failure.

## ⚠ Which past conclusions this invalidates — measured per gate

26 documents in `docs/analysis/` read this table. Rather than guess, here is the corruption rate
**by skip category**, since each of those analyses argues about one specific gate. Read your
analysis's category to know whether its "missed winners" number survives:

| gate the analysis is about | winners it claimed | never a setup | wrong |
|---|---|---|---|
| **pm_rvol_low** | 14 | 12 | **86%** |
| **catalyst_downgrade** | 12 | 10 | **83%** |
| **cooldown** | 12 | 9 | **75%** |
| **adv_low** | 28 | 16 | **57%** |
| high_unentered | 9 | 5 | 56% |
| score_below_50 | 26 | 12 | 46% |
| **extension_gate** | 21 | 9 | **43%** |
| atr_high | 12 | 4 | 33% |
| window_missed | 6 | 2 | 33% |
| moderate_tier | 4 | 1 | 25% |
| duplicate_scan | 21 | 4 | 19% |
| ma_filter | 3 | 0 | 0% |

**The pattern is not random.** The three worst — premarket RVOL, catalyst downgrade, cooldown —
are gates that fire *early*, on pre-market information. They are exactly the gates whose
"victims" are pre-market prints that then faded, so almost everything they were accused of
missing was never tradeable.

**Concretely at risk** (highest corruption × a decision actually taken):

- **`adv_floor_556_2026-08-20`** — argued the ADV floor's cost. `adv_low` is **57% fake** and has
  the largest claimed-winner count in the table.
- **`cooldown_cost_557_2026-08-21`** and **`cooldown_60d_effectiveness_2026-07-26`** — `cooldown`
  is **75% fake**.
- **`gates_extension_top20_577_2026-08-22`** and **`conviction_floor_extension_2026-08-03`** —
  `extension_gate` is **43% fake**.
- **`orb_window_587_2026-08-23`** — `window_missed` at 33%, on a small base (6).

**Not at risk:** anything reasoning over ALERTS rather than skips. An alert gapped by definition,
so the open-basis filter cannot move it. That covers the judge, rubric and score-separation work.

None of these is re-run here — flagged, not corrected, and filed on #595.

## What this does not answer

- **Whether the 1,366 real setups are correctly measured.** They are not touched here.
- **Whether a faded pre-market print is worth acting on separately.** It is a real signal about
  our scan timing; it is simply not a missed EP.
