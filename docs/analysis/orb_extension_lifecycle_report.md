# ORB-window extension impact — lifecycle analysis

**Question**: For orders cancelled at 10:00 ET (placed in the 9:31–9:35 ET window but never crossed limit), is there evidence to extend the cutoff?

## Method

- Universe: `mi_live_trades` rows with `status IN ('cancelled','expired')`, `entry_price IS NOT NULL`, `proposed_at` between 9:31–9:35 ET. Excludes `window:out_of_orb` (separate question).
- Day 1: minute-bar entry at limit + same-day stop check + same-day re-entry (max 2 attempts, mirrors `attempt_day1_reentry`).
- Day 2+: production `apply_daily_exit_step` (hard_stop, SMA10/20 trail, Day 3–5 partial 1/3, breakeven) through today.
- Open positions marked-to-market at last close.

## Result — N=5 (below 20-trade significance threshold)

```
cutoff    fills  wins  losses  still open    total $    mean $   median $  avg hold
10:00         2     1       1           2       +364      +182       +182       1.5d
11:00         2     1       1           2       +364      +182       +182       1.5d
12:00         2     1       1           2       +364      +182       +182       1.5d
13:00         2     1       1           2       +364      +182       +182       1.5d
14:00         3     1       2           2       +127       +42       -237       1.0d
16:00         3     2       1           3      +1228      +409       +616       2.0d

ticker date         10:00     11:00     12:00     13:00     14:00     16:00  final
SIRI   2026-04-23      —         —         —         —         —         —  never crossed
TEVA   2026-04-30      —         —         —         —         —         —  never crossed
TWLO   2026-05-01      —         —         —         —      -237      +864  still open 3d
CCC    2026-05-01   -253      -253      -253      -253      -253      -253  still open 3d
TEAM   2026-05-04   +616      +616      +616      +616      +616      +616  still open 0d
```

## Findings

1. **N=5 is too small to decide.** Variance dominates — the 14:00→16:00 swing (+$1,101) is a single TWLO leg.
2. **Sim over-permissive on entry.** CCC + TEAM show "fill at 10:00" but in reality didn't cross (limit-buffer fix + Polygon vs Alpaca SIP timing). Real-world fills would be fewer.
3. **3 of 5 cases (SIRI, TEVA, TWLO at ≤13:00) get nothing from extension.** Two truly never crossed; TWLO needed a 4-hour wait for the second cross.
4. **TWLO is a single anecdote.** With multi-day momentum (now +$864 unrl), it's the only case that materially benefits — and only at 16:00 cutoff.

## Recommendation

**Don't change the cutoff yet. Ship telemetry, accumulate, decide at N≥20.**

Concretely:
- Add a `mi_orb_extension_shadow` table or audit-event stream. On every 10:00 ET cancellation, fork a "what if" simulation: would the limit have crossed by 11/12/13/14/16:00? If so, run the production exit logic forward through completion and record (entry_at, exit_at, exit_reason, total_pnl, hold_days).
- Sunday weekly digest surfaces accumulating counterfactual: "N=12 cancelled-extension shadow trades, mean P&L $X at 14:00 cutoff vs $0 baseline."
- Re-evaluate when N≥20 cancellation events accumulate (~5–10 weeks at current rate).

**Why telemetry first**: a cutoff change touches every ORB entry. Single-anecdote evidence (TWLO) doesn't justify the regression risk to the steady-state HIGH-alert pipeline. Shadow recording costs nothing and produces the decisional dataset.
