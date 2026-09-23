# #572 Offline geometry sweep — re-entry, established-low entry, ATR/structure stops vs the live 1-minute bracket

**2026-08-18 · read-only · $0 · probe: `scripts/probes/geometry_sweep_572.py`**
(real captured minute bars from `mi_intraday_bars`; capture SQL and every rule in the probe
docstring; nothing on prod written; no strategy-path code touched. Extends the 2026-08-18 #482
read — `bracket_geometry_read_482_2026-08-18.md` — and reuses its capture and helpers.)

## The answer, up front

**No variant earned a live shadow arm.** Sweeping the three #482 variants (plus sub-variants,
six lanes total) offline against real minute bars, on the same trades the live system actually
entered: every lane is negative, and no lane beats the simulated 1-minute baseline in both R
and ADR units. The operator's INTC re-entry example is REAL and reproduces in-sim (+7.32R) —
but it is one row; the other 13 re-entry days gave it all back. The established-low entry
mostly refuses to trade (19 of 30 days) and loses more per trade when it does. Wider stops
(ATR-1.0, prior-day-low) lose more money while looking better in R units — the R-unit mirage
at full strength. The bracket running live today (era C, 2R stop) still has ZERO closed
trades in any lane; letting it accrue remains the highest-value evidence.

## What was swept, and against what

**Denominator (stated, per the standing rule):** the **46 closed, FILLED live magna53
trades** — the population the live system entered. 30 of them have a full captured day-0
minute session (24 era A, 6 era B, 0 era C) and form the sweep cohort; 11 have only the
09:30 ORB bar and 5 have no bars (excluded, listed in the probe output); CRMD 2026-05-14's
real fill printed below its own ORB low, so ORB-anchored lanes run n=29. **Names the live
system skipped never enter this read — it measures geometry on trades TAKEN, not
selectivity.** Minute bars: `mi_intraday_bars` (217,778 bars, 553 tickers, back to
2026-04-13); dailies: `mi_daily_closes` from 2026-02-17 (≥20 prior sessions for every row).

**Design — sim-vs-sim.** Every lane, including the baseline bracket, replays through ONE
engine with ONE uniform era-C-like exit policy (+2R partial at half in the lane's own unit →
breakeven → SMA10/20-max daily-close trail → 20-day time stop) on the same bars. The #482
read showed sim-vs-live comparisons carry a one-directional optimism (SYRE); here the
optimism cancels because both sides of every comparison are the same engine. Calibration on
identical trades: **B0 sim reads +11.94R rosier than live realized (29 trades)** — so no
absolute level below is expectancy; only lane-vs-lane deltas are readable.

**Fill limit (stated every time):** B0/A/C lanes start from the REAL live entry fill; every
exit is simulated; lane W's entry is simulated too. Daily-resolution days use gap-at-open
stop fills (open below stop fills at the open — worse-than-full losses ARE expressible,
unlike the #482 shadow lane). Daily-resolution re-entry days cannot sequence the low against
the trigger, so lane A prints a conservative/optimistic bracket. Offline gives breadth; only
a live arm gives fill realism.

## Per-variant verdicts (n, R, ADR, tail — paired vs the simulated baseline B0)

B0 (baseline sim, ORB-low stop): n=29, sum −11.22R / −8.55 ADR, med −1.00R, p90 +1.00R.

| lane | n | sum R | med R | p90 / max R | sum ADR | paired dR vs B0 | paired dADR vs B0 | verdict |
|---|---|---|---|---|---|---|---|---|
| **(a) re-entry ≤2×, ORB-low stop** | 29 | −14.02 | −1.00 | +1.00 / +2.78 | −12.73 | **−2.80** | **−4.18** | worse both units — earned nothing |
| **(a′) re-entry ≤2×, prior-day-low stop** | 29 | −9.50 | −1.00 | +1.00 / **+7.32** | −11.17 | +1.73 | −2.62 | one tail row (INTC); ex-INTC re-entries −6.59R over 13 — not promotable |
| **(b) established-low entry** | 11 traded / 30 | −5.86 | −1.00 | +0.71 / +1.06 | −8.44 | −6.64 (11 pairs) | **−7.90, med −1.17** | trades a third as often, worse where it trades — geometry earned nothing |
| **(c) ATR-0.5× stop** | 30 | −13.11 | −1.00 | +1.00 / +2.43 | −5.58 | −0.88 | **+3.45, med +0.10** | the lone ADR-positive delta — marginal, and it points the wrong way (below) |
| **(c) ATR-1.0× stop** | 30 | −14.89 | −1.00 | +1.00 / +2.21 | −13.81 | −2.67 | −4.31 | worse both units |
| **(c) prior-day-low stop** | 30 | −8.58 | **−0.31** | +0.45 / +1.66 | **−23.70** | +3.51, med +0.28 | **−12.63, med −0.82** | the R-unit mirage in its purest form |

(A conservative/optimistic bracket exists for the re-entry lanes — the daily-resolution
ambiguity; the optimistic reads are A −12.02R/−10.36 ADR and A′ −7.50R/−8.79 ADR. No verdict
changes anywhere in the bracket.)

### (a) Re-entry after a stop-out — the INTC example is real, and it is one row

Re-entries triggered on 14 of 30 name-days. With the same ORB-low stop, the re-entry
attempts alone sum **−2.80R**: the re-break of the ORB high usually fails again. With the
prior-day-low stop — the exact shape of the operator's INTC example, day-0 low as the day-1
invalidation — the sim reproduces his trade almost exactly: stopped −1R on 04-24, re-entered
04-27, survived the 04-28 dip *because* the wider structure stop held where the ORB stop
gap-stopped, partialed at +2R on 04-29, trailed out 05-15 → **+7.32R** (he quoted +6.89R).
But across the other 13 re-entry days the same rule lost **−6.59R**, and the lane is still
ADR-negative vs baseline even WITH INTC. A mechanical re-entry rule funds one INTC with
thirteen losers. What his example actually demonstrates is not "always re-enter" — it is
that *the day-0 low held as an invalidation line on a name that then worked*, which is the
structure model's claim (`docs/methodology/structure_model.md`), a **selectivity** question:
which stopped-out names deserve a second look. That is #468b/#508 territory, not bracket
geometry.

### (b) Wait-for-established-intraday-low — a filter wearing an entry's clothes

The rule (session low un-breached 30 min arms a buy-stop at the high-of-day; a new low
re-arms; stop = the established low) found **no entry on 19 of 30 days** — verified against
raw bars: those are the all-day fade days (NET 08-07: HOD frozen at 10:00, new lows printing
until 14:54). On the 11 days it DID trade it was **worse than the baseline on 5 of 11 pairs,
median −1.17 ADR per pair** — it enters later, wider (median stop 7.6% vs 3.1%), into the
same names, and its partial almost never fires (1/11; 5 baseline partials destroyed). As a
portfolio over all 29 common days (no-entry = 0) it looks better in R units (−5.86 vs
−11.22) **but that is the R-unit mirage again — in ADR units it is a wash (−8.44 vs −8.55)**:
it concentrates the same dollar loss into fewer, fatter trades. The genuinely interesting
residue: 15 of the 18 days it declined were baseline losers. The established-low CONDITION
has value as a *fade-day detector* (selectivity/exit work), not as entry geometry.

### (c) ATR / structure stops — mechanism 5, now measured across a full width ladder

The partial-fired rate falls monotonically as the stop widens — the wider unit lifts the +2R
target out of reach exactly as the 08-06 and 08-18 reads predicted:

| stop | median width (% of entry) | partial fired | baseline partials destroyed |
|---|---|---|---|
| ATR-0.5× | 2.5% | 9/30 | 2 |
| ORB low (B0) | 3.1% | 8/29 | — |
| ATR-1.0× | 4.9% | 6/30 | 3 |
| prior-day low | **19.5%** | **1/30** | **8** |

- **ATR-0.5×** is the only lane with a positive ADR delta (+3.45 sum, +0.10 median across 29
  pairs): same entries, tighter stop, less paid per stop-out. But it is marginal, it buys
  MORE shakeouts on a cohort #468b already showed is shaken out to death, and it moves in the
  OPPOSITE direction from the operator-signed era-C bracket (2R ≈ 6.5% stop, target
  unmoved). Promoting a 2.5% stop while live runs a 6.5% one would be incoherent without
  first seeing era C's closed trades.
- **Prior-day-low** is the extreme object lesson: best median R of the sweep (−0.31), worst
  ADR sum (−23.70, median −0.82/pair, 2.8× the baseline's dollar losses), because a 19.5%
  stop makes every R multiple tiny while every stop-out costs a fifth of the position. Its
  tail (+6.61 ADR = INTC held a month through the shakeout) is real and is the same
  hold-through-structure effect as (a′). Six of its 30 sims were still open at the
  20-day/data horizon — its numbers are the least settled. Unsizeable as a live stop.

## What this sweep cannot see (selection, stated)

- Only trades the live gates ADMITTED — no declined names, no counterfactual universe. The
  operator's "trade the declined names too" question is a different (selectivity) study; the
  bar material for it now exists (`alert_day_path_persist`, 96 skipped name-days with full
  sessions).
- 16 of 46 filled trades lack usable day-0 bars (mostly May–June, before full-session
  persist) — the cohort skews toward July–August names.
- Era C — the bracket live TODAY — has zero closed trades in every lane; everything above is
  era A/B alert-days replayed under one uniform policy.
- All exits simulated; entry fills real only where live actually filled (B0/A/C lanes).

## The fork (his to rule — geometry is entry discipline, THE LINE; this doc decides nothing)

1. **Promote nothing; let era C accrue** (recommended). Third consecutive read where
   geometry fails to be the edge lever; the signed 2R stop already embodies the one
   defensible width move without moving the target.
2. If any offline finding routes anywhere, it is the two **selectivity** residues — the
   established-low condition as a fade-day detector, and "day-0 low held next morning" as a
   second-look trigger on stopped-out names — into the #508 exit/selectivity program, not
   into a bracket arm.

---

## Appendix — probe output (key blocks, verbatim)

Full output regenerable: `python3 scripts/probes/geometry_sweep_572.py --data-dir <capture>`.

```text
DENOMINATOR: 46 closed FILLED live magna53 trades; 30 with full day-0 sessions
(era A=24 B=6 C=0); excluded: 11 ORB-bar-only + 5 no-bars; CRMD odd fill -> n=29
for ORB-anchored lanes.

1. CALIBRATION (same trades, same entries):
   LIVE realized  n=29 sum -23.16 med -1.00 p90 -0.23 max +3.83 win 3/29
   B0 sim         n=29 sum -11.22 med -1.00 p90 +1.00 max +2.78 win 8/29
   per-trade (sim - live): sum +11.94  median +0.03

2. SWEEP (R own-unit | ADR common-unit), sums:
   B0    -11.22 | -8.55      A_cons -14.02 | -12.73     Apdl_c -9.50 | -11.17
   W(11) -5.86  | -8.44      C05    -13.11 | -5.58      C10   -14.89 | -13.81
   CPDL  -8.58  | -23.70     LIVE   -23.16 | -15.16

3. PAIRED vs B0 (dR sum / dADR sum, med):
   A_cons -2.80 / -4.18      Apdl_c +1.73 / -2.62      Apdl_o +3.73 / -0.24
   W      -6.64 / -7.90 (med -1.17, 11 pairs)
   C05    -0.88 / +3.45 (med +0.10)   C10 -2.67 / -4.31   CPDL +3.51 / -12.63 (med -0.82)
   W PORTFOLIO (no-entry=0, 29 days): R -5.86 vs B0 -11.22; ADR -8.44 vs -8.55 (wash)
   B0 on the 18 days W declined: -12.00R, 15 losers

4. MECHANISM 5 (partial fired / median stop width / B0-partials destroyed):
   C05 9/30 2.5% 2 · B0 8/29 3.1% — · C10 6/30 4.9% 3 · CPDL 1/30 19.5% 8 · W 1/11 7.6% 5

5. RE-ENTRY DETAIL: triggered 14/30. ORB-stop re-entries alone sum -2.80R.
   PDL-stop re-entries: INTC +8.32R, other 13 sum -6.59R (net +1.73R).
   INTC Apdl chain (verified vs raw bars): -1.00R 04-24 stop; re-enter 04-27 @84.00
   stop 79.62 (04-24 low); survives 04-28 low 80.80 (ORB-stop lane gap-stopped here);
   partial 92.76 on 04-29; trail out 05-15 @108.77 -> +7.32R total (operator quoted +6.89R).

6. ERA SLICES: verdicts unchanged in era A alone (n=23-24 per lane); era B n=6
   not decision-grade; era C n=0 everywhere.
```
