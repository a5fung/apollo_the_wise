# #508 — What unit should the profit-taking trigger be measured in?

**Date:** 2026-08-01 · **Status:** EVIDENCE ONLY — no rule shipped, no live exit changed.
**THE LINE:** exit discipline is strategy. This document exists so the operator can rule; it does
not rule. Any change needs CHANGE_PROCESS + sign-off + backtest.

## The question

Operator, 2026-07-30: *"in general +3R is a good spot to take partial profit, something like 1/3rd at
3R then move stop to breakeven — however, this requires R to be set correct, too tight or too loose
will mess it up."*

**His caveat was the finding.** R is not a fixed unit here, so "+3R" is not one rule.

## Why R is not a unit

`R` = the distance from entry to the initial stop. Across the 12 live trades that distance spans
**0.15 to 1.17 of the ticker's own 20-day average daily range — a 7.7× spread** (verified 2026-08-01:
for all 12, `stop_pct` equals `risk_per_share / entry × 100` exactly, so this is the ORIGINAL entry
risk, not a trailed stop).

So a single "+2R" trigger fires after:
- **0.31 of a normal day's move** on MANE (stop 0.15 ADR), but
- **2.35 days** on NVCR (stop 1.17 ADR).

The most extreme case is in the paper cohort: **CRSR recorded +12.36R — and 0.06 of a daily range.**
Its stop was 0.01 ADR wide. Twelve R of a hair.

The inverse also holds: **NVCR made the biggest real move of the 12 live trades (2.35 daily ranges)
and scored the LOWEST R of the four that went anywhere (2.00R)** — purely because its stop was widest.

## What the replay says

Engine: `scripts/probes/_508_exit_rule_replay.py` (built 2026-07-30, unchanged contract — limit-at-
level fills, breakeven stops that gap through, bar-covered days replayed bar-by-bar, pessimistic
tie-breaks on ambiguous intra-day ordering). Added 2026-08-01: an ADR-unit trigger family, which is a
pure conversion (`L ADR` = `L / stop_per_adr` in R) so the same validated fill machinery is reused.

**Live cohort, n=12 — mean kept R per trade:**

| rule | fires | mean kept R | vs actual |
|---|---|---|---|
| actual / do nothing | 0 | −0.92 | — |
| deployed day-3 partial | 1 | −0.83 | +0.09 |
| 1/3 at **+2R** + breakeven | 4 | −0.46 | +0.47 |
| 1/3 at **+3R** + breakeven | 3 | −0.51 | +0.41 |
| 1/3 at **1 ADR** + breakeven | 5 | −0.23 | **+0.69** |
| 1/3 at **0.5 ADR** + breakeven | 6 | −0.32 | +0.61 |
| exit ALL at 1 ADR | 5 | +0.49 | +1.42 |

Directionally: **the ADR unit beats the R unit at the same rule shape**, and the operator's +3R is
worse than +2R on this cohort. The deployed day-3 rule is worth almost nothing because it fires once.

## Three caveats that constrain how far this can be read

1. **ZERO winners in the live cohort.** Every number above is loss-cutting, not profit-banking.
   "Exit ALL at 1 ADR" tops the table *because nothing ever ran further* — that line would invert the
   moment one trade runs. **It is not a recommendation and must not be read as one.**
2. **n=12, and the gap between +2R and 1 ADR is one extra trade triggering (5 vs 4).** The ranking is
   directional, not significant.
3. **The paper cohort cannot arbitrate.** No paper trade ever reached even 1 ADR (max 0.64, mean 0.15,
   vs live max 2.35 / mean 0.70), so ADR rules never fire there and the two cohorts are not
   comparable. Paper stop widths are also degenerate in places (CRSR at 0.01 ADR), which is what
   inflates its R to 12.36.

### The gap-day hazard — checked, and it does not apply (but only by accident)

Raised against option B: Episodic Pivots are defined by large gap-ups, and ATR uses TRUE range, so if
the stored `atr_14` window includes the alert day the unit is inflated and a "1 ATR" target sits much
further away than "1 ADR".

**The size of the hazard is real.** Recomputing both ways over the 12 live trades, including the
alert day inflates the unit by up to **57%** (WDFC 6.75 → 10.61; THC 7.56 → 10.70; NVCR 0.88 → 1.12).

**But the stored value excludes it.** For all 12, `atr_14` matches the EXCLUDING-alert-day
recomputation to three decimals and differs from the including version. Reason, per
`backtester/filters.py::compute_atr_14`: the live path computes ATR at 9:31, and `mi_daily_closes`
does not yet carry today's bar — so the window is strictly pre-alert.

⚠ **That exclusion is INCIDENTAL, not enforced.** It holds because of ingest timing, not because any
code asserts it. If the daily-bar ingest ever moved earlier, or ATR were ever recomputed for a trade
after the close (a re-entry path, a backfill), the same function would silently start including the
gap day and inflate the unit by up to 57% — with no error. **If a rule ships on this unit, that
property needs a test pinning it**, or the rule's trigger distance quietly drifts on exactly the
gappiest names, which are the ones the strategy exists to trade.

Peak is also **understated for very short holds** — the instrumentation reads `highest_price_seen`,
which is blind under ~10 minutes (CRCL's true intraday peak was +1.62R against a recorded 0.00).
That biases every candidate DOWN, so the measured edge is a floor.

## The fork — operator's call

**A. Keep the trigger in R.** Familiar, matches how the stop is set, and no new machinery. Accepts
that the same rule fires at 7.7× different real distances across names.

**B. Move the trigger to ADR** (e.g. 1/3 at 1 daily range). One consistent distance for every ticker;
best on this cohort at every matched shape.

⚠ **The obvious objection to B — "the exit path can't see ADR intraday, so this is a rule plus an
unbuilt data dependency" — was raised and does NOT hold. Checked 2026-08-01:**

- `mi_live_trades` already carries an **`atr_14`** column, written **at entry** by
  `entry_pipeline.py:562/575` from a value `process_new_alerts_live` computes
  (`live_tracker.py:392`, `compute_atr_14`). It is persisted on the trade row before the position
  ever needs an exit decision.
- **Coverage on the money path is complete: 12 of 12 filled live trades have it** (paper 24 of 32).
- So the exit path does not need to compute or fetch anything at trigger time — it reads a column on
  a row it already loads. That is a one-column change, not a data build.

**Two honest gaps in that, which is why B still is not free:**

1. **ATR-14 is not the ADR-20 this analysis used.** ATR uses true range (gaps included) over 14 days;
   the recorder's `adr_20_pct` is `(high−low)/close` over ~20. Measured across the 12 live trades they
   track at **0.82–1.14×** (mean ≈0.98) and the ORDERING is preserved — NVCR stays the widest stop,
   MANE the tightest. But a rule shipped in ATR should have the replay re-run in ATR before sign-off;
   it is the same one-line conversion, so this is cheap, not hard.
2. Historical coverage is imperfect (11 of 43 recorder rows lack a usable ADR ratio — all paper, all
   with stops recorded at/above entry), which limits backtest depth, not live implementability.

**C. Rule nothing yet; fix the measurement gate first.** ⚠ Note that the #508 review gate I set is
itself written in R (`peak_r >= 4`, currently 1 trade). In ADR terms the same cohort has 5 trades past
1 daily range. **The gate inherits the flaw it was meant to study** and should be re-keyed before it
is used to decide anything.

## Recommended sequencing (mine, not a ruling)

Re-key the gate (C) regardless of A-vs-B — it costs nothing and it is currently miscounting the
evidence 1-vs-5. Then rule A or B on the next cohort with at least one winner in it, since no
candidate here has ever been tested against a trade that ran.
