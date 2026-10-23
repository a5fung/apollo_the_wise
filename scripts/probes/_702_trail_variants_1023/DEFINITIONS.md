# #705 Track B — the silent spots of BRIEF.md, filled BEFORE any walk ran (2026-10-23 06:40 PDT)

The brief fixes the grid (2 averages × 4 triggers × 2 partials, on S2 close T2, T0 beside). Where it is silent, the plainest reading,
chosen here and not revisited after a number was seen:

- **Averages.** SMA10 / SMA20 = the mean close over the 10 / 20 sessions ending at the session (the stock's own closes), built from the same
  wide close frame with the same rolling call as `esr_lib.Frame.SMA` (SMA20 must equal `F.SMA` exactly; SMA10 is built the same way).
- **Trail live** (every trigger): P1 — once a third has sold OR j ≥ 3 (as `pp`). P0 — once +2R has first been reached OR j ≥ 3 (the P0 mirror
  of "after a third"; it only matters in sessions 1–2). For X4 the level must exist before the session: live at session j iff a third sold
  (P1) / +2R was reached (P0) BEFORE session j, or j ≥ 3.
- **X1 close below** = `pp`: close < SMA while live → everything left sells at the NEXT open (a missing next open → marked at the signal close,
  degraded).
- **X2 decisive** = (close ≤ SMA × (1 − 0.5 × ADR20)) OR (close < SMA on this and the previous readable session), while live → the next open.
  ADR20 = the trade's own ADR20 at its entry (bday − 1; the same object the stop is built from, fixed per trade). The "previous session under"
  flag is tracked on every readable session from the first walked session; a NaN session leaves it untouched.
- **X3 reclaim forgiven**: a close < SMA while live starts a watch at session sj. A close ≥ SMA (not under) at sj + 1 or sj + 2 cancels it
  (a later close under starts a fresh watch). With no reclaim by the sj + 2 close, everything left sells at the open of sj + 3 (the same
  next-open mechanism as X1, read at the sj + 2 step). A missing close inside the window is not a reclaim. The stop, the +2R leg and the
  stall cut keep running inside the window; the horizon mark at 120 wins if sj + 2 > 120 (at sj + 2 = 120 the sale at the next open is
  flagged censored, as X1 does).
- **X4 intraday**: the level = the PRIOR session's average (SMA at j − 1, the one known when the low prints). While live, the effective stop
  for the session = max(stop in force, level); open ≤ level → everything left at the open, else low ≤ level → at the level. A bar touching
  both the level and the +2R target books the exit at the level (the carried exit's pessimistic rule) unless it opened at/above the target
  (the third at the open first, P1). The exit is a TRAIL exit (no retry) unless the stop in force was the binding level (stop ≥ level →
  a STOP exit, which can earn a retry).
- **P1** = `pp`: ⅓ at +2R (at the open if it gapped there), the session-3 third only in profit with no third yet, breakeven from the session
  after the first third. **P0**: no third anywhere (neither at +2R nor at session 3); breakeven (stop = max(stop, fill)) from the session after
  +2R was first reached (high ≥ fill + 2R, or an open at/above it); the stall cut unchanged (+1R not reached by the session-3 close → all
  sold at that close).
- **Unchanged**: entry at the breakout close, S2 = entry − 1.0 × ADR20(t − 1) × entry, up to two re-entries after a STOP exit (the first
  close above the base high within 20 sessions), a bar touching the stop and a level books the stop, the 120-session horizon, the marks.
- **Median sessions held** (P-win) = per base Σ (exit session − entry session) over the chain's trades; median over bases. The first trade's
  beside. A duration, never a time to anything.
- **Worst trade / 5th-percentile trade** = per-trade realized R over every chain trade of the cell (T0: first trades; T2: all). On the
  control: the FULL control's per-trade distribution (the matched cell means cannot give a percentile), and the seed-702 account-view
  sample's worst beside (a book of the same size). No interval on a percentile; the brief's intervals are on the means.
- **The control sample** = the saved seed-702 draw of the 10-22 read (`02_sample_R{1,2}_<era>.tsv`), reused, with the control n asserted
  equal (2,096,517 / 1,469,399) so the saved indices point at the same rows.
- **Parity, before any new cell is read**: (a) SMA20 rebuilt from the close frame equals `F.SMA`; (b) `walk_v(SMA20, X1, P1)` returns every
  array bit-equal to `esr_lib.walk` on P-win, R1 and a control subsample; (c) the whole S2_close cell through `walk_chain_v` reproduces every
  number of `02_numbers_<era>.json['grid']['S2_close']` to the digit; (d) the published `pp` rows re-walked through `walk_v` reproduce
  7,334 / 7,335 and 4,905 / 4,905 as `01_parity.txt` did.
- **Own-code check** (`04_checks.py`): a plain per-trade Python walk of every trigger × partial, independent of the lockstep code, on random
  trades per cell per era at the frame's float32 prices.
