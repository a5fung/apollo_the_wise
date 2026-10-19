# #702 Consolidation Breakout — backtest runner (P2a: daily stage + minute fetch script; P2b: minute stage, STEP 0 entries, holdout guard, report)

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
| `candidates.tsv` | `DATA/out/` | one row per (watch night, K) where high(E) > pivot_K(D) (K = k5 / k10 / full / tl; a K with no level that night, i.e. `tl` with no down-sloping line, has no row); `retrigger` + `first_<cell>` (spec key), `retrigger_chain` + `first_chain_<cell>` + `base_id` (drift-robust key), `overlap_open`, `split`, gap fields, `pole_hi_over_oc` / `pole_bad_high` (data flag), every cell flag |
| `close_variant_discovery.tsv.gz` | `DATA/out/` | CLOSE entry + all 15 exit arms (`st_/r_/adr_/held_/acct_/beabove_<arm>`), DISCOVERY rows only; `fwd_hole` = 1 when the forward walk was cut at a missing session (the walk then ends `degraded`) |
| `minute_fetch_list.tsv` | `DATA/out/` | unique (ticker, E) over all candidates incl. retriggers; `tier` 1 = any of C1..C7 / report cells true on some K |
| `minute_fetch_list_delta.tsv` | `DATA/out/` | #702 P1c: the (ticker, E) pairs the `tl` candidates need that `DATA/minutes/_done.psv` does not hold (the first pull covered k5/k10/full); same columns and tier as `minute_fetch_list.tsv`, so `fetch_minutes.py --list` reads it unchanged. Not a freeze pin (derivable from two pinned artefacts: `candidates.tsv` and the minute tree). The daily stage prints its size |
| `*_com.*` (`watch_com.tsv.gz`, `candidates_com.tsv`, `gap_in_bars_com.tsv`, `minute_fetch_list_com.tsv`, `minute_fetch_list_delta_com.tsv`; small: `run_summary_com.txt`, `step0_com.txt`, ...) | `DATA/out/` | **#702 P4b `--keys com`**: the same stage on the CENTER-OF-MASS level only (`cb.com_level`: the median of the base's highs; his 2026-10-18 rule, chosen on the P4b label read — `docs/analysis/cb_preregistration_2026-10-18.md` §P4b). Same layouts as the pinned files plus the `pivot_com*` / `com_*` columns and `C*_com` cells; `minute_fetch_list_delta_com.tsv` = the `com` breakout days whose minutes are not in `_done.psv` (both eras; `fetch_minutes.py --list` reads it as is). `--no-close-variant` skips the CLOSE walk so the run computes no outcome and `overlap_open` is blank. The pinned names are never written by a `--keys` run; `holdout` refuses `--keys` |
| `*_com_comb.*` / `*_comb.*` (`--keys com,comb`, one pass; `--keys comb` alone) | `DATA/out/` | **#702 P4b step 6b**: `comb` = `com` read only on the nights the stock CLOSED AT OR BELOW the level (C0 additionally needs `close(D) <= pivot_com`; every cell inherits it). One set of files, `K` carrying `com` and `comb`; a `comb` candidate exists only on such a night, and the daily stage asserts the `comb` (ticker, E) pairs are a subset of `com`'s (the check is in `run_summary_com_comb.txt`), so `com`'s minute fetch covers it |
| `regime_report{sfx}.tsv` / `regime_report_holdout.tsv` (+ a `.txt` in the small-summary dir) | `DATA/out/` | **#702 P4b step 6b**: the headline table (orh5, `p33_s3_t10`) split by Apollo's daily regime at D (`apollo_regime`: Bull / Choppy / Correcting / Crisis / missing, + an `ALL` row = the headline row): n / mean R / share >= 5R per (key, cell, K, regime). Written by `report` and, on its one run, by `holdout`; the regime is joined from `candidates{sfx}.tsv` at read time. Reported BESIDE, never deciding. **Apollo's label starts 2025-03-03 (`small_pulls.psv`): every discovery night reads `missing`, so the `report` table is one `missing` column; the split is informative on the holdout only** |
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


7. **K = `tl`, the down-sloping trendline (#702 P1c; his note 2026-10-17 in `docs/methodology/operator_shared_notes.md`).** The module draws the line from the pole top through the flattest base high, bars <= D only, and `pivot_tl` is its value on E = D + 1 (projected one session ahead; the other three levels are fixed levels). `tl` is tested BESIDE k5/k10/full: the same `cell_flags(k="tl")`, the same one-trade-per-base keys (spec key `(ticker, pole_date, K)`, chain key unchanged), a breakout is `high(E) > pivot_tl(D)`. Three things to know when reading it: (a) a night where a base high sits above the pole high has no line (`pivot_tl` empty, no `tl` cell, no `tl` candidate) - so the `tl` C0 population is a SUBSET of the horizontal ones (the review counted 118 of 385 fixture watch nights with no line) and a tl-vs-k5 difference is the level AND the population; the daily stage prints a per-split table (watch nights, C0_k5, C0_tl, no-line nights, of which base high over pole high) under the cell-count table, and the P4 read quotes it beside any tl-vs-k5 comparison; (b) the line is a LOWER level than the base high, so `tl` breaks earlier and far more often (MRNA: first `tl` break of the 08-19 base is D 09-03, eight sessions before the k5/k10/full break on D 09-16, and 5 `tl` rows against 1 each) - which also means more retriggers and more `tl` rows that are not the base's first; (c) the level can sit UNDER D's close or E's open, in which case the `pivot` entry fills at the open and the `orh` entries at the opening-range high - not at the line (the watch table carries `close` and `pivot_tl` to count how often). `tl_*` telemetry in `watch.tsv.gz` (`tl_slope_pct`, `tl_touch_*`, `tl_interior_touches`) never gates.
---

# P2b — the minute stage (`minute`, `step0-entries`, `holdout`, `report`)

```
python3 scripts/probes/_cb_backtest/runner.py daily         --data DATA --keys com [--no-close-variant]                         # #702 P4b: the com level, *_com outputs
python3 scripts/probes/_cb_backtest/runner.py minute        --data DATA [--minutes DIR] [--workers N] [--no-close] [--no-apollo]   # DISCOVERY outcomes
python3 scripts/probes/_cb_backtest/runner.py step0-entries --data DATA [--minutes DIR]                                           # HOLDOUT composition, NO outcome
python3 scripts/probes/_cb_backtest/runner.py report        --data DATA                                                          # the DISCOVERY read
python3 scripts/probes/_cb_backtest/runner.py holdout       --data DATA --dry-run [--no-freeze-check] | --print-pins | (the real run)  # BUILT, NOT RUN; the real run = the minute engine, then the P5 pass (below)
```
`--minutes` defaults to `DATA/minutes`; `--limit-dates N` takes the first N minute dates on disk (dev). Every decision is still the frozen module's:
`entry_variants` (four minute entries per K) -> `day0_result_to_outcome` on a day-0 stop-out, else `walk_exit` on EVERY `cb.ARMS` arm
(`closes_before[-1] == close(E)` asserted, `fwd` = E+1 .. E+1+horizon cut at the first missing session, as `close_variant_rows` does).

## Outputs (`DATA/out/` unless noted)
| File | What |
|---|---|
| `trades_discovery.tsv.gz` | one row per (candidate, K, variant, arm): `realized_r` (units of fill - the entry's own stop), `pnl_adr`, `acct_pct`, `status`, `sessions_held`, `mature` / `open_mark`, every cell flag, spec + chain retrigger stamps, `gap_over_1adr`, `width_pct`, `adr20`, `atr14`, `median_dollar_vol20`, phase flags, `year`, `month`(E). A `too_wide` / other abstain or a no-trigger gets ONE row with no arm. Sensitivity columns ride on it (below). 17 arms per filled minute variant (15 `cb.ARMS` + 2 controls); the `close` variant is the daily stage's 15 arms, joined (nothing re-walked). |
| `entries_discovery.tsv.gz` | one row per (candidate, K, variant incl. `close`): status, reason, `minutes_state`, level, fill, stop, width, fill minute, day-0 result, the `first_*` / `first_chain_*` stamps, every cell flag. |
| `entries_holdout_composition.tsv` | STEP 0: status / reason / width / fill minute per (holdout candidate, K, variant) + stamps + cells. No fill price, stop, day-0 or exit column exists in it. |
| `discovery_report.tsv` (here: `DATA/out/`, full, ~30 MB) and `out/discovery_report.{txt,tsv}` (repo, the `all` slices, 6 decimals) | the report. `trades_holdout.tsv.gz` / `entries_holdout.tsv.gz` only after the guarded `holdout` run. |
| `out/minute_summary_discovery.txt`, `out/step0_entries.txt` | the printed summaries (coverage, data gate, entry counts). |

## Rules the minute stage enforces
- **Minutes**: `<date>.psv.gz` read as one multi-member gzip stream; a BLOCK is a run of consecutive lines for one ticker inside ONE gzip member (the fetcher writes one member per symbol per fetch), so a ticker that appears again - in a later member, including the one right after its own after a crash lost its done-line - is a re-fetch and the LAST block per (date, ticker) REPLACES the earlier. A truncated tail member is dropped, every complete member before it kept (`gzip.open` would lose its read buffer). `_done.psv` says what was fetched: a pair that is **not** in it is `pending` — skipped and counted, **never** an abstain; `empty` / a lost block -> `no_minutes` abstain; an unusable block (duplicate minutes ...) -> `invalid` -> `no_minutes`. Without a `_done.psv`, a ticker with rows in the date file counts as fetched.
- **Data gate**: `no_minutes + minute_daily_mismatch + minute_high_below_pivot` over fetched candidates is printed with the minute-vs-daily match rate; > 5% prints `BLOCKS THE READ`.
- **Maturity** (`is_mature`): terminal (`stopped`, `stopped_day0`, `trailed`, `target`, `time_exit`) or `censored` with >= horizon + 1 forward sessions = mature; `degraded`, or a `censored` mark with fewer, = `open_mark` — recorded, never in a number. Family A: mature when 5 forward bars existed or it was out before the last available forward day. Apollo control: `settled` / `horizon` mature, `pending` (a hole, data end) / `abstain` (an unorderable day-0 bar) are open marks with no R.
- **One trade per base**: retriggers stay in the table, stamped; the report keeps `retrigger == 0` (spec key) and prints `retrigger_chain == 0` beside it.
- Deterministic: workers return gzip members in date order (mtime 0); 1 vs 10 workers give byte-identical outputs (checked).

## The two controls (comparable to the cb arms: same entry, same stop, R in the same unit)
- `ctl_family_a_settle` — Family A's `SETTLE_RULE` (+1R half, +3R half, day-5 stop) through `anticipation.build_mixed_path` (the day-0 minutes AFTER the fill bar, then the first 5 forward daily bars) -> `anticipation.simulate(..., 'pess')`. It walks day 0 itself, so it is never short-circuited by the module's day-0 stop-out.
- `ctl_apollo_today` — the live MAGNA53 ladder through `live_fill_counterfactuals.walk_arm`. **THE FRAME IS AN ADAPTATION, stated, not hidden**: `walk_arm` is parameterised in ORB-R (stop = entry - 2 ORB-R, partial +8 ORB-R, breakeven +3 ORB-R) and a CB fill is not an opening-range entry, so the ladder is anchored on the trade's own placed risk, the live relation (1 placed-risk R = 2 ORB-R, `recut.py`): the ORB-low stand-in is the midpoint of fill and the CB stop, so `fill - 2 x (fill - orb_low)` IS the CB stop. Result: same entry, same stop, same R unit; partial at fill + 4R, breakeven armed at fill + 1.5R, SMA trail with the depth exit. Built by `live_fill_counterfactuals.stack_walk_inputs(rule_eras.exit_rules_as_of(DEPTH_EXIT_LIVE_DATE, 'magna53', 'depth'), ...)` so the stamped and walked stacks cannot differ (precedent: `scripts/probes/_runner_recut_1017/recut.py` `CONTROL_KW`). Two further choices: HORIZON 120 (a data window, not a rule; the recorder's 40 is its own cap), and the fill bar's LOW is neutralised (the CB stop is the low of the day INCLUDING the fill bar's own low, so `walk_arm`'s fill-bar test abstains on a breakout bar that is also the low of the day — 20% of walks on a synthetic-minute rehearsal, the real rate depends on how often that happens — while the module's own day-0 walk starts after the fill minute; the bar's high and close are kept, they post-date a buy that triggered inside it, so `walk_arm`'s fill-bar target / breakeven tests stay live). `prior_closes` = own closes in the 40 calendar days before E (#548). If the frame is not accepted, `--no-apollo` drops the arm (`minute` only; the holdout's setting is fixed in the pinned runner).

## Sensitivities (recorded per row, none decides)
- `cap_*` (on the `too_wide` abstain row): stop = fill x (1 - adr20), `day0_walk` on it, then the primary arm. `r_h60` / `st_h60` / `mature_h60` (on the primary-arm row): the primary arm re-walked at horizon 60 on a 61-bar window. `atr14_wide` (width > ATR14(D)), `floor_0 .. floor_1` (width < f x ADR20 for f = 0, .25, .5, .75, 1: 1 = a report may drop the row). `acct_pct` = min(20%, 1% / width) x pnl / fill = R x min(0.20 x width, 0.01) (`acct_pct()`, the one formula the daily and minute stages share).

## The holdout (BUILT, NOT RUN)
- `step0-entries` — entry-time facts only, per cell x K x variant under BOTH base keys. It opens no daily bar and calls no walker (`cb.entry_variants` computes a `day0` inside a filled entry — module-internal — which is dropped unread); a test makes `walk_exit`, `day0_result_to_outcome`, `simulate` and `walk_arm` raise and runs it.
- `holdout` — the `minute` engine on the holdout, once (also walks the CLOSE variant, which the daily stage never did for the holdout). It runs only in its registered form: **exit 2** on `--out` other than `DATA/out`, `--small-out` other than the repo `out/`, `--limit-dates`, `--no-close` or `--no-apollo` (an `--out` elsewhere read an unpinned `candidates.tsv` and looked for "already joined" there; the others run a part of the holdout) - so the Apollo control is ON or OFF in the pinned runner, decided before the freeze. The tables are written as `<name>.partial` and renamed only after every date is walked; a `.partial` on disk (a crashed run) refuses a re-run until the operator removes it by hand. `read_candidates` re-derives every row's `split` from `D` and raises on a mismatch (a relabelled file cannot carry holdout rows into `minute`). `freeze_check()` (the #686 pattern) reads the registration doc `docs/analysis/cb_preregistration_*.md` (exactly one, or `--prereg`): `<!-- FREEZE -->` marker, then one `- <label> sha256: \`hex\`` line per pin. **exit 2** on a missing doc / marker / pin / file or any mismatch; `--no-freeze-check` is honoured only with `--dry-run`; it also refuses if `trades_holdout.tsv.gz` already exists. `--print-pins` prints the footer lines for P4 to paste.
- Pins (the labels): `module`, `runner`, `code/constants.py` (`ENTRY_SLIPPAGE_PCT` sets every minute fill), `code/anticipation.py` (Family A control), `code/live_fill_counterfactuals.py` + `code/rule_eras.py` + `code/exit_logic.py` (the Apollo control and the ladder it settles through) - derived by a test that walks the call graph from the worker entry points (the detection code, `flag_detector` etc., is not on the outcome path: what it found is already frozen as `candidates.tsv` / `cell table`); `agents/market_intelligence/db.py` is the one repo module reached and NOT pinned (`walk_arm` takes only the one-line float helper `_f` from a 1 MB live-DB file) - `cell table` (= `watch.tsv.gz`), `data/<file>` for every file directly in `DATA/` (the export, SIC, splits, VIX, small pulls, liquid list), `minutes (tree)` (all `*.psv.gz` + `_done.psv`), `candidates.tsv`, `minute_fetch_list.tsv`, `gap_in_bars.tsv`, `close_variant_discovery.tsv.gz`, `trades_discovery.tsv.gz`, `entries_discovery.tsv.gz`, `entries_holdout_composition.tsv`, `discovery_report.tsv`, `discovery_report.txt`, and `doc body` (everything above the marker).

## The report
Mature, non-retrigger rows (spec key; the chain key printed beside) grouped by cell x K x variant x arm: n, open marks, mean R with a month-block bootstrap 95% CI (calendar month of E, 2,000 resamples, seed 702 mixed with the group key), share >= 3R / 5R / 10R, mean without the five best, median, win rate, mean `pnl_adr`, mean `acct_pct`; sliced by year, QQQ 10/20 phase at D, gap over 1 ADR, dollar-volume and ADR terciles (cuts on the discovery C0 distribution), and sum of R per month. The headline block (every cell C0..C7 + the two report cells, K = k5 / k10 / full / tl, entry `orh5`, arm `p33_s3_t10`) puts the tail first. Also: too_wide skips per cell, all arms for C0 / C1, the sensitivity table.

---

# His exit (#702, 2026-10-18) — the `exits` and `exits-report` stages (DISCOVERY only, new files only)

```
python3 scripts/probes/_cb_backtest/runner.py exits        --data DATA --levels tl         # the trendline from the pinned candidates.tsv
python3 scripts/probes/_cb_backtest/runner.py exits        --data DATA --keys com,comb     # both center-of-mass levels from candidates_com_comb.tsv
python3 scripts/probes/_cb_backtest/runner.py exits-report --data DATA --levels tl | --keys com,comb
```
His correction of the sell rule (sell 1/3 at +2R, breakeven, trail the 10-day for faster stocks / the 20-day for slower, "it may be a
combo") as 25 arms `cb.HIS_EXIT_ARMS` (`<trigger>_p33_<trail>`: r2 / d3 / d5 / c3 / c5 x t10 / t20 / tspd / td1 / td2), each walked
under the five `cb.STOP_VARIANTS` (lod = registered, lod_cap05, lod_floor05, level_m05, base_low; each too_wide beyond one ADR),
beside the registered `p33_s3_t10` — on the spec key's FIRST breaks at the headline entry (orh5), the split hard-coded to discovery
(`holdout` refuses `--levels`). The +2R touch is read on the MINUTES on the breakout day (`cb.day0_walk_target`) and on daily bars
after (a bar touching both the stop and the target books the stop unless it opened above the target). `base_low` and `range_recent5`
are recomputed from the bars with `explain_watch`'s formulas (not candidates.tsv columns; `base_low` is cross-checked against
`base_depth`). Outputs: `DATA/out/trades_discovery_exits<tag>.tsv.gz` (`EXITS_COLS`: one row per entry x stop variant x arm, an
abstain row per unusable stop), `DATA/out/exits_report<tag>.tsv` + the repo copies `out/exits_report<tag>.{tsv,txt}` and
`out/exits_summary<tag>.txt`; tag = `_tl` / `_com_comb`. The report ranks combos on mean P&L in ADR units (R's unit changes with the
stop) among the combos that kept >= 95% of the registered row's trades; a stop that abstains on most trades gets the registered arm on
exactly its own trades (`matched`) instead of a rank; plus the tightness fifths (range_recent5 / ADR20 and tightening_ratio, cut per
level on its C0 filled population) under the registered row and the best two combos. The read: `docs/analysis/cb_his_exit_2026-10-18.md`.
Nothing pinned is written: the four default-key stages hash identically before and after the change.


---

# P5 — the holdout read's primary: HIS exit with the stalled breakouts cut (#702, 2026-10-18) — the `p5` stage and `holdout`'s second pass

```
python3 scripts/probes/_cb_backtest/runner.py p5      --data DATA                 # DISCOVERY: the walk + the report (new files only)
python3 scripts/probes/_cb_backtest/runner.py holdout --data DATA                 # BUILT, NOT RUN: the minute engine, then THIS pass, once
```
The arm `c3_p33_t20_cut3` (module: `CUT_EXIT_ARMS`) = `c3_p33_t20` (sell 1/3 at +2R or at the close of session 3, breakeven,
trail the 20-day, next-open fill) + the stall cut (no +1R by the close of session 3 and not stopped -> everything sold at that
close; status `time_exit`). The stage walks it with three arms beside it (`p33_s3_t10` the article's, `c3_p33_t20` uncut, `r2_p33_t20`
+2R only) on the `lod` stop at ORH5 over the spec key's first breaks of `tl` (`candidates.tsv`) and of `com` / `comb`
(`candidates_com_comb.tsv`), through `evaluate_exits(stops=("lod",), arms=P5_ARMS)` - the SAME function on discovery and on the
holdout. The registered arm inside the table is then compared, per (ticker, D, K), with the minute stage's own table (status, maturity,
realized R to 1e-9): the discovery run passed on 8,989 `tl` and 17,447 `com` / `comb` rows; a difference exits 3 (and, on discovery,
blocks the report).

| File | Where | What |
|---|---|---|
| `trades_{discovery,holdout}_p5.tsv.gz` | `DATA/out/` | `EXITS_COLS` layout: one row per filled first break x arm (4 arms x `lod`), K in tl / com / comb. The holdout one is written as `.partial` and renamed after every date; it joins `holdout_existing_outputs` (a second run refuses, a crashed run's partial refuses until removed by hand) |
| `p5_report_{discovery,holdout}.tsv` (+ `.txt`, and a 6-decimal 'all'-slice copy of the `.tsv`, in `out/`) | `DATA/out/`, `out/` | per (key spec / chain, cell C0..C7 + the 3 report cells, K, arm): n, n_open, mean R + month-block interval, shares >= 3/5/10R, mean without the top 5, median, win, ADR P&L, acct %, `n_cut`, `mean_held`; spec key also by year of E, QQQ 10/20 phase and Apollo regime at D (`all` / each label; the label starts 2025-03-03). The text adds the filled-entries table (the STEP 0 counts to reproduce) and THE CUT'S OWN EFFECT (the primary against its uncut twin on the same trades) |
| `regime_report_holdout.{tsv,txt}` (appended) | `DATA/out/`, `out/` | after the minute stage's own rows, the P5 arm x level rows it does not carry (never a duplicate of its `tl` / `p33_s3_t10` rows) |
| `p5_summary_{discovery,holdout}.txt` | `out/` | the run log: coverage, the entry tally, the cross-check lines |

Recovery corner: if the holdout's minute pass completes and the P5 pass crashes, the once-only guard refuses a re-run through the CLI
(the `.partial` / the finished minute tables are on disk); the operator inspects, removes the P5 `.partial`, and calls
`run_p5_stage(args, "holdout")` directly - the minute tables are not walked twice.

Nothing existing is written: the default-key stages hash identically and the `exits` / `exits-report` outputs are byte-identical
(the pre-registration §P5 and the SSoT change log carry the proof). The pins gained `candidates_com_comb.tsv`, `watch_com_comb.tsv.gz`,
`entries_holdout_composition_com_comb.tsv`, `trades_discovery_p5.tsv.gz` and `p5_report_discovery.{tsv,txt}` (the holdout now reads the
com / comb candidates; the discovery P5 numbers are what the registration quotes).


# The selection test (#702, 2026-10-19) — are HIS picks better than the average base? Build + population only; the read is written, not run

Registration: `docs/analysis/cb_selection_test_prereg_2026-10-19.md`. Data dir `/Users/alvinfung/apollo_data/cb702_pre/` (outside the repo).

```
python3 scripts/probes/_cb_backtest/selection_pre.py export        # Alpaca-era export (alp_flat.npz of the P4b extension) -> cb702_pre/
python3 scripts/probes/_cb_backtest/runner.py daily --data cb702_pre --keys tl,com --no-close-variant --era-label pre \
    --raw-close cb702_pre/daily_raw_close.csv.gz --breaks cb702_pre/symbol_guard.tsv --watch-start 2017-03-01 --watch-end 2021-12-31 \
    --out cb702_pre/out --small-out cb702_pre/out/small                                  # the C0 first breaks; NO outcome of any kind
python3 scripts/probes/_cb_backtest/selection_pre.py join          # picks, controls (a)/(b), selection_population.txt (keys only)
python3 scripts/probes/_cb_backtest/selection_read.py --data cb702_pre     # THE READ - run only after the population is checked
```
The `daily` flags `--raw-close / --breaks / --watch-start / --watch-end / --era-label` are additive (a default run hashes identically:
`candidates.tsv`, `watch.tsv.gz` and `close_variant_discovery.tsv.gz` of the pinned run). `selection_pre.py join` reads the candidate
table through a column whitelist that holds no price of the breakout day or later. `selection_read.py` is the only script that opens
a post-breakout bar; its numbers and verdict rule are in its docstring and `tests/test_cb_selection.py` (synthetic data only).
