# #702 Consolidation Breakout — backtest runner (P2a: daily stage + minute fetch script)

Plan: `/Users/alvinfung/.claude/plans/soft-singing-hamster.md`. Every decision (universe, watch gates, RS/group
percentiles, phases, cells, entries, exits) is a call into the frozen module
`agents/market_intelligence/consolidation_breakout.py`; the runner only loads, schedules, joins and writes.

```
python3 scripts/probes/_cb_backtest/runner.py daily --data /Users/alvinfung/apollo_data/cb702        # ~45 s on 10 cores
python3 scripts/probes/_cb_backtest/runner.py daily --data ... --step0                                # composition table only
python3 scripts/probes/_cb_backtest/runner.py daily --data ... --check-prescreen 300                  # exhaustive pre-screen proof
python3 scripts/probes/_cb_backtest/fetch_minutes.py --list DATA/out/minute_fetch_list.tsv --dry-run  # P3 runs it for real, in prod
python3 -m pytest tests/test_cb_backtest_runner.py tests/test_consolidation_breakout.py -q
```

## Outputs
| File | Where | What |
|---|---|---|
| `gate_counts.tsv`, `universe_by_date.tsv`, `run_summary.txt`, `step0.txt` | `out/` (small) | the funnel (every ticker-night in exactly one row, by year), universe size N + phases + Apollo regime per date, the printed report, STEP 0 |
| `watch.tsv.gz` | `DATA/out/` | one row per (ticker, D) passing every C0 structural gate: all features + RS/group/phase context + every cell per K |
| `candidates.tsv` | `DATA/out/` | one row per (watch night, K) where high(E) > pivot_K(D); `retrigger` + `first_<cell>` (spec key), `retrigger_chain` + `first_chain_<cell>` + `base_id` (drift-robust key), `overlap_open`, `split`, gap fields, `pole_hi_over_oc` / `pole_bad_high` (data flag), every cell flag |
| `close_variant_discovery.tsv.gz` | `DATA/out/` | CLOSE entry + all 15 exit arms (`st_/r_/adr_/held_/acct_/beabove_<arm>`), DISCOVERY rows only; `fwd_hole` = 1 when the forward walk was cut at a missing session (the walk then ends `degraded`) |
| `minute_fetch_list.tsv` | `DATA/out/` | unique (ticker, E) over all candidates incl. retriggers; `tier` 1 = any of C1..C7 / report cells true on some K |
| `gap_in_bars.tsv` | `DATA/out/` | watch rows with no tradable E (`gap_in_bars` / `no_next_bar`); `pending` (D = last session) is only counted |

## Rules the runner enforces (all asserted)
- Calendar = SPY's sessions; every bar date is on it; dates strictly ascending per ticker; every value finite; QQQ carries every session (phase join is by DATE).
- **A ticker's bars are NOT assumed consecutive** (6,018 of 20,285 tickers have a missing session inside their span: halts, thin names, reused tickers glued into one series). A night is admitted only if its 130 bars are consecutive SPY sessions (`contiguous_window_mask`; one test covers the 130-bar history, RS 21/63/126, SMA50, the pole window and ADR20); a night failing only that counts under the `history` funnel row. The CLOSE-variant forward walk stops before the first bar that follows a missing session (`fwd_end`), so it ends `degraded` instead of being booked on another company's prices (`fwd_hole`).
- **Splits executing after the last session (2026-10-16) are dropped** from the RAW-price factor (`load_splits(through=)`): the adjusted series does not contain them yet, so multiplying them in makes the raw price of every bar of that ticker wrong (85 splits, 26 tickers in the file).
- **Exchange test symbols are never members** (`is_test_symbol`: ZVZZT, ZTEST, NTEST, PTEST, ZBZX, ... and the Z?ZZ[TC] family; 18 tickers in the export). The module's `universe_ok` admits an unknown-type ticker by design, so the runner drops them before it.
- `bars.dates[i] == D` for every watch row; `E` = the ticker's next bar AND the next SPY session, else it is recorded as a gap and never traded.
- Universe: `cb.universe_ok` with `cb.raw_factor_for` (split ratio = `split_to / split_from`; factor evaluated once per run between split dates, equal to the per-bar call — tested). Security type: `mi_security_types`, else the SIC pull's `type`, else unknown (admitted).
- Pre-screen: skip `explain_watch` only when `max(high[i-45..i-10]) / min(low[i-85..i-10]) - 1 < 0.30` — a proof, not a heuristic (the pole gate is the first gate after history, and both bounds are outside-in); `--check-prescreen` runs the real gate on every night of 300 tickers and asserts every skip failed at `prior_move`.
- **One trade per base**, under TWO keys (STEP 0 prints both): the SPEC key (ticker, pole_date, K) - first breakout `retrigger=0`, later ones `retrigger=1` - and the CHAIN key (`retrigger_chain`, `base_id`): a ticker's distinct watch-row poles within 3 sessions of each other are ONE base (the module's pole top drifts 1-3 sessions inside one consolidation, and alternates between two poles night to night, which re-keys the same base under the spec key). The chain key is a coarsening of the spec key by construction and the run asserts it. Plus `first_<cell>` / `first_chain_<cell>` = the first breakout of the base on which THAT cell held (see Flags).
- **Holdout (D > 2024-12-31) gets no outcome here.** `overlap_open` is therefore computed for discovery non-retrigger rows only (CLOSE-variant primary-arm exit as the proxy) and left blank for holdout.
- `overlap_open` keeps the LATEST-ENDING open trade (max), not the most recent one: a short trade opened inside a long one must not hide the long one.
- Discovery walks near 2024-12-31 read forward bars from 2025 (`fwd_last_date` shows it; 4,409 filled rows cross the line). Selection is by D, so no holdout trade is chosen with hindsight, but a discovery R can contain holdout-era prices.

## Flags carried to P4 (decisions, not defects)
1. **The spec's base-level retrigger rule vs a cell's own first entry.** C1's holdout trades are 33/33/33 (k5/k10/full) under the literal rule but 70/58/43 as "first breakout where C1 held" — a base that broke out once while C1 was off loses its later, valid C1 entry to the literal rule. Both are in `candidates.tsv`; which one is the decisive population is a P4 call.
1b. **Spec key vs chain key — decides the k5 go/no-go.** Holdout C1 trades: spec key 33/33/33, chain key 26/33/33 (k5/k10/full). Seven of the 33 k5 trades re-enter a base whose pole top drifted 1-3 sessions after an earlier break (NUTX, SATS, IREN, NEXA, INTC, APPN, DINO); k10/full have none. At the plan's >= 30 bar k5 passes under one key and fails under the other: P4 rules which key is decisive BEFORE the go/no-go is read.
1c. **C1 is sensitive at the margin.** Two borderline names (AKRO 2025-06-25, DINO 2026-10-02) sit at RS 97.9 -> 98.0 after the cross-section was cleaned (holes, test symbols, split fix move every percentile by ~0.1); each is one trade in a count of 33.
2. The module's `breakout_key` is `(ticker, pivot_k_date)`; the spec and harvest row 1 say `(ticker, pole_date, K)`. The runner follows the spec and never calls `breakout_key` (module untouched).
3. Cell flags do not depend on K except that the pivot must exist; K changes only WHICH nights break out.
4. SIC is one row per ticker (2026-10-16, or the delisting date), so group membership is constant in time; 19% of watch rows have no group (no SIC, or fewer than 10 universe members in the group on that night).
5. `be_above_close` (partial sold under the fill, so the breakeven stop takes it out at the next open) fires in ~7% of filled partial-arm trades — the hidden one-day time stop the module's docstring describes (`beabove_<arm>`).
6. **Suspect high prints (data flag, not a gate).** 640 watch rows on 51 tickers have a pole bar whose high is > 1.25x max(open, close) (NVDA 2024-06-10 high 195.95 vs open 120.37 / close 121.79 becomes `pole_high`); the module's pole-artifact guard looks only at close jumps. Candidate rows carry `pole_hi_over_oc` / `pole_bad_high`; 0 non-retrigger C1 trades are affected in either split, so the go/no-go is untouched. The clean fix is in the module (P4/P6 revision), not a runner-side clip of price inputs.
