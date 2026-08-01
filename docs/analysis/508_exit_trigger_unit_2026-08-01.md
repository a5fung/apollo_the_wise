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

~~The most extreme case is in the paper cohort: CRSR recorded +12.36R — and 0.06 of a daily range.~~
❌ **RETRACTED 2026-08-01 (adversarial review) — this exhibit was BACKWARDS and it was mine.** CRSR's
recorded `stop_pct` of 0.0276% is not its entry risk; its true `risk_per_share/entry` is **4.2454%**.
Its original stop was **0.77 ADR — mid-range for this cohort — and its move was ~9.5 daily ranges.**
The number was an artifact of the bug in the section below, not evidence for the argument.

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

Directionally on THIS cohort: the ADR unit beats the R unit at the same rule shape, and +3R is worse
than +2R. The deployed day-3 rule is worth almost nothing because it fires once.

## ⚠ THAT CONCLUSION DOES NOT SURVIVE THE DATA REPAIR — read this before ruling

After the recorder bug (caveat 3) was fixed and all 43 rows backfilled, the paper cohort — **which
contains the only 2 winners in the dataset** — became measurable for the first time. It does not
agree with the live table.

**paper/magna53, n=24 — Δ vs actual, and what each rule COSTS the 2 winners:**

| rule | fires | Δactual | cost per winner |
|---|---|---|---|
| 1/3 at **+1R** | 9 | +0.37 | **−0.41** |
| 1/3 at **0.5 ADR** | 9 | +0.38 | −0.03 |
| 1/3 at **1 ADR** | 7 | **+0.22** | −0.26 |
| 1/3 at **+3R** | 6 | +0.29 | **+0.26** |
| 1/3 at **2 ADR** | 6 | +0.32 | **+0.22** |
| exit ALL at 1 ADR | 7 | +0.46 | **−0.78** |

Three things fall out, and they point the opposite way to the live table:

1. **The ADR advantage does not replicate.** `1 ADR` — the best rule on the live cohort (+0.69) — is
   among the WORST here (+0.22), below +2R and +3R. Best-ADR (+0.38) and best-R (+0.37) are a
   rounding error apart. **The unit question is not settled by this evidence; it is contradicted by
   it.**
2. **The zero-winner artifact is now measurable rather than hypothesised.** "Exit ALL at 1 ADR" —
   which topped the live table at +1.42 — costs **−0.78 per winner**. It is the single most
   destructive rule in the grid on trades that actually run, exactly as caveat 1 warned.
3. **Only the FAR triggers leave winners alone**: +3R (+0.26) and 2 ADR (+0.22) are the only two that
   HELP winners. Every near trigger taxes them. The operator's original instinct — take profit far
   out, not close in — is the one thing both cohorts support.

n(winners) = 2. This is directional, not a result. But it is now measured on trades that ran, which
nothing in the first version of this document was.

## Three caveats that constrain how far this can be read

1. **ZERO winners in the live cohort.** Every number above is loss-cutting, not profit-banking.
   "Exit ALL at 1 ADR" tops the table *because nothing ever ran further* — that line would invert the
   moment one trade runs. **It is not a recommendation and must not be read as one.**
2. **n=12, and the gap between +2R and 1 ADR is one extra trade triggering (5 vs 4).** The ranking is
   directional, not significant.
3. **THE MEASUREMENT DESTROYS ITSELF ON WINNERS — the most important finding in this document, and
   it arrived from the adversarial review rather than from me.** The recorder derived stop width from
   the trade row's `stop_price`, which by the time a trade CLOSES is the **trailed** stop. So every
   trade that RAN — i.e. every winner, the only trades that can price an exit rule's cost — recorded
   a stop width of ~0, and every ADR field derived from it is garbage.

   Verified across all 43 rows: **every paper trade above +1.02R is corrupted.** BW, FTRE, RCAT, TEAM,
   KURA, SMCI, QURE, PURR all recorded `stop_pct = 0.0000` against true entry risk of 0.78–10.56%;
   GOOGL recorded −3.47 vs a true 0.83; FPS −10.96 vs 11.42. The 11 rows I excluded as "unusable" are
   not a random gap — **they are precisely the 11 biggest movers in the dataset.**

   So the earlier claim "no paper trade ever reached 1 ADR" is FALSE. The true statement is that the
   recorder could not SEE their excursion. GOOGL, recomputed from its implied ADR, reached ~2.8 daily
   ranges.

   **Consequence for the ruling: combined with zero live winners, the ADR trigger family has been
   scored against losing trades ONLY — everywhere in the dataset, not just live.** That is a stronger
   limitation than caveats 1 and 2 admit on their own.

   **Consequence going forward, which is worse:** the moment any breakeven or trailing rule ships, the
   stop moves on exactly the trades #508 needs to measure — so the defect would have kept
   regenerating. ✅ **FIXED 2026-08-01**: the recorder now derives stop width from `risk_per_share`
   (the original entry risk, already the basis of `realized_r`) and stores `adr_20_pct` RAW, so
   nothing downstream reconstructs the ticker's range from a stop-derived ratio. The 12 live rows were
   clean only by luck — all 12 lost, so no stop ever trailed above entry, and the bug was invisible in
   the money cohort. **The 43 historical rows still carry the corrupt values and need a backfill
   before any cohort number here is re-quoted.**

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

**C. Rule nothing yet; fix the measurement gate first.** ✅ **DONE 2026-08-01** — this needed no
ruling, because it changes when we LOOK, never what we trade. `exit_tune_cohort_review`'s runner term
was `peak_r >= 4` (1 trade), i.e. keyed in the very unit this review exists to interrogate. Now
`peak_adr >= 1.5` (2 trades), chosen to preserve the original intent — 4R was ~2× a 2R candidate
trigger, so 1.5 ADR is 1.5× the 1-ADR candidate — rather than to manufacture readiness. (`peak_adr`,
not `peak_atr`: peak_adr is what the recorder stores; no `peak_atr` column exists.)

⚠ **The re-key does NOT open the gate**, which is worth stating because the opposite was assumed: the
predicate is a `LEAST()` and the FIRST term still binds — 12 closed live trades against a threshold of
20. Verified against prod: the predicate returns 12 both before and after. The runner term simply
stops being the artificial blocker, so cohort size — the honest constraint — governs again.

## Recommended sequencing (mine, not a ruling)

**Do not rule A vs B on this cohort.** Every candidate here has been scored only against trades that
lost; none has ever met a trade that ran. Optimising an exit on loss-cutting evidence alone risks
fitting a mean-reversion exit into a momentum strategy — capping precisely the fat right tail the
whole method depends on.

⚠ **But gate the decision on EXCURSION, not on WINS.** The operator broke exactly that catch-22 on
2026-07-30: *"if our sell rules need improvement, current 3-day profit take may not yield 2 winners
for a long time."* A gate that waits for winners waits on the outcome the rule under test structurally
prevents, and can never open. A gate that waits for trades which RAN — regardless of how they closed —
is satisfiable and gives a complete price path to measure both benefit and cost. That distinction is
the difference between a gate that opens and one that never does, and the re-keyed
`peak_adr >= 1.5` term is already the excursion form.
