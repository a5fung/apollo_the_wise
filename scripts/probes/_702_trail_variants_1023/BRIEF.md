# #705 Track B — the trail-variant exit read (brief written 2026-10-22, run 2026-10-23)

His words (2026-10-22, verbatim, `docs/methodology/operator_shared_notes.md`):

> "On trailing the 10/20, we can test a decisive break vs quick reclaim, close below, etc. as stop"

> "We need to attack from both ends, we need to filter to less breakouts, trade reasonable amount and have better way to keep
> winners without taking major losses"

**Why:** the stop / re-entry read (`docs/analysis/cb_entry_stop_retry_2026-10-22.md`) showed the exit is what loses the winners.
- The 1-ADR stop with up to two retries holds ~44–48% of the good-setup doublers to half their move.
- But it keeps a median 5% of the gain: the ⅓ sold at +2R and the first close under the 20-day end the trades.

## Reuse, don't rebuild

The harness is `scripts/probes/_702_entry_stop_retry_1022/esr_lib.py` (`walk`, `walk_chain`, `race`, `month_block_ci`,
`account_view`), with the same populations, matched control, eras and scope rules.
- **Populations:** P-win = the 481 / 258 covered measurable-breakout doublers. P-all = R1 and its R2 subset. P-ctl = matched ordinary
  stocks.
- **Eras:** 2017–21 and 2022–24 only; no bar after 2024-12-31.
- **Read-only:** do not edit `esr_lib.py`. Import it, or copy the walk into this dir with a parity test that reproduces the
  stop / re-entry read's `pp` numbers to the digit before any new arm is read.

## The grid — FIXED HERE, before any outcome (every cell reported, none picked)

- **Entry / stop / retry held fixed at the best-holding cell of the last read:** entry at the breakout close, S2 = entry − 1.0
  ADR20, T2 = up to two re-entries. T0 is reported beside.
- **Trail average:** the 10-day and the 20-day (two values).
- **Trail trigger (the exit fires at the NEXT open after the signal):**
  - **X1 close below** — the first close under the average (today's `pp`).
  - **X2 decisive** — a close at least 0.5 × ADR20 under the average, OR two consecutive closes under it.
  - **X3 reclaim forgiven** — after a close under the average, exit only if no close back above the average within the next 2
    sessions (exit at the open after the 2nd session).
  - **X4 intraday** — the first session whose LOW trades under the average (exit at that average, or at the open if it gapped
    under).
- **Partial:** P1 ⅓ at +2R (as `pp`) / P0 no partial (the whole position trails).
- **Unchanged from `pp`:**
  - the session-3 stall cut (+1R not reached by the session-3 close → sell all);
  - breakeven after the third (P1), or after +2R is first reached (P0);
  - a bar touching the stop and a level books the stop.
- **Cells:** 2 averages × 4 triggers × 2 partials = 16 per era, plus the `pp` baseline row.

## Measures (n on every row, tail first)

- **P-win:**
  - still in at half the move;
  - kept ≥ ½ and ≥ ¼ of the episode's gain;
  - the median share of the gain kept;
  - the median sessions held.
- **P-all and P-ctl:**
  - trades per week;
  - mean R per trade and per base (retries summed);
  - win rate;
  - ≥ 5R and ≥ 10R per 100;
  - the WORST trade and the 5th-percentile trade (his "without taking major losses");
  - P-all minus P-ctl with month-block intervals (seed 702, 2,000).
- **Account view beside:** 0.5% risk per trade, the total and worst drawdown.
- **Retry rows:** state the control-retry caveat from the last read. Only the no-retry comparisons against the control are clean.

## Plain-words rules (the 10-22 lesson)

- Every lead sentence names the quantity exactly as computed. A time to REACH a gain is never "the start".
- A share forced by geometry is never evidence.
- The doublers say what a rule HOLDS, never whether it pays; that is P-all vs P-ctl only.

## Output

`docs/analysis/cb_trail_variants_2026-10-23.md`. It must pass `scripts/check_analysis_doc.py`. Probes go in this dir; large tables in
`apollo_data/<era>/out/trail_*`. Measurement only; the exit rule is his call (THE LINE). Two independent verifiers follow (recount +
logic), as on 10-22.
