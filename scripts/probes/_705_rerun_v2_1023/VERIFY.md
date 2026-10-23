# #705 v2 re-run — independent verify of RESULT.md: all six checks pass, verdict PASS

Verifier: a separate card (no subagents). Only this file was written in the repo; my scripts and their outputs are in the session scratchpad (`v_parity.py`, `v_recount.py`, `v_recount2.py`, `v_default.py`). Verify time: 2026-10-23 13:08 PDT onward.

| # | check | result |
|---|---|---|
| 1 | default path of all 11 edited scripts unchanged | **PASS** |
| 2 | parity: re-run the diff myself | **PASS** (all four reads, not just two) |
| 3 | no cited file overwritten | **PASS** |
| 4 | recompute a v2 headline number myself | **PASS** |
| 5 | no input dated 2025 or later read | **PASS** |
| 6 | old-vs-new table quotes the right old values | **PASS** |

## 1. Default path — PASS
- Read the full diff (11 files, +139/-67). Every new switch is `os.environ.get(...)` with the old literal as its default: `out_dir()` returns `f"{data}/out"` when `CB_PRE_OUT` is unset, `LOG_DIR` defaults to `HERE`, `PREV_DIR` to `PREV`, the `ERAS`/`DATA` override runs only when `CB_PRE_DIR`/`CB_PRE_OUT` is set, and the era filter in the 03 reports applies only when an argument is given.
- The new asserts are no-ops by default (`PRE_OUT` None and `LOG_DIR == HERE` → passes for both eras).
- `trail_variants/02_build.py`: `n_ctl` keeps the literal `2096517 / 1469399` unless `PREV_DIR != PREV`; the original `02_numbers_2017-21.json` has `ctl.n = 2096517`, so the switch agrees with the literal.
- `02_catch.py`: `ERAS["2017-21"]["data"] = ep01.ERAS[...]` — HEAD's own literal was `/Users/alvinfung/apollo_data/cb702_pre`, identical to `01_episodes.py`'s; `ep01.HERE` is the same directory.
- Every write in the 11 scripts (`to_csv`, `to_parquet`, `open(...,"w")`, `json.dump`) goes through `out_dir()` or `LOG_DIR` (grep: 0 unswitched writes).
- I imported HEAD and working copies side by side with no CB_PRE_* set (`v_default.py`, import-only; the module-level 03 reports were not executed): `ERAS` head == work for `01_episodes`, `bdef 02_build` and `esr_lib`; `out_dir == DATA/out` for both eras; `LOG_DIR == HERE`; `02_catch` 2017-21 data = cb702_pre; `trail 02_build` `PREV_DIR == PREV`.
- No CB_PRE_* in the environment or in `~/.zshrc`, `~/.zprofile`, `~/.zshenv` or `~/.bash_profile`.

## 2. Parity — PASS (my own compare, `v_parity.py`)
- Byte-equal (`filecmp`, not size): `entry_stop_retry/02_numbers_2017-21.json`, `trail_variants/02_numbers_2017-21.json`, `02_sample_R1/R2_2017-21.tsv`, `winner_recall/02_reverse_2017-21.txt`, `breakout_definition/02_build_checks_2017-21.txt`.
- The logs differ only in wall-clock seconds (`02_catch` 12s vs 13s; the esr and trail build logs ±1s) and in the output path (`01_episodes`); no count differs.
- JSON subsets: winner_recall `03_numbers.json` has 40 old keys, 23 of them 2017-21, 0 naming neither era, so the subset filter drops nothing. The new key set equals the old 2017-21 keys and the values are equal. The same holds for breakout_definition (33 / 15 / 0, equal). Both `03_headline.json` 2017-21 blocks are equal.
- Tables, decompressed sha256, re-run vs the `cb702_pre/out` originals: all 13 EQUAL (6 `wrecall_*`, `bdef_fills/r1/kvar`, `esr_win/r1`, `trail_win/r1`). Not re-hashed by me: `bdef_control` (245 MB) and the two parquets (RESULT's receipt covers them).
- The originals are what the docs cite: the probe-dir numbers files are tracked and have no diff against HEAD (commits dd557852, 3881e019, 46019230, 0eb6f1b2). The `cb702_pre/out` tables date from 10-22 17:47–21:11, plus `trail_*` from 10-23 06:52, which matches the committed trail `02_numbers` (06:52:41).

## 3. Nothing a doc cites was overwritten — PASS
- `cb702_pre/out`: **0 files modified after 13:00 PT**, and none after 06:52:41 today (the only files touched today are the four `trail_*_2017-21` files from the original 06:52 trail run). The edits started at 12:48:55 and the re-runs ran 12:49–13:07.
- `cb702/out`: only `trail_*_2022-24`, at 06:49 (the original run).
- `git status`: in the four probe dirs only the 11 `.py` files are modified, plus new untracked `rerun_1023/` dirs; every tracked json/md/txt/tsv/log has no diff against HEAD. `find -newermt 12:00` in those dirs lists only the 11 scripts and the `rerun_1023/` files.
- `_cb_backtest/` and `_702_r_decomposition_1022/`: 0 files newer than 12:00. The untracked `_cb_backtest/out/h60_*` files date from 2026-10-19 17:05–17:09.
- Outside `rerun_1023`, the other changes in `apollo_data` since 12:00 are not files these four reads open or cite:
  - the `survivorship_1023` minute fetch (last write 12:17:14) and the `cb702_pre_v2/out` daily stage (12:18), both before the first edit;
  - `cb702/qm_streams/vision` (last write 12:31:55), also before the first edit;
  - `cb702/qm_streams/track_a_1023` (`labels_joined.tsv` / `matched_events.tsv` at 13:03:51), which is concurrent Track A work (#705 frame check).

## 4. Recompute from the v2 output — PASS (`v_recount.py`, `v_recount2.py` on `cb702_pre_v2/out/rerun_1023/winner_recall/`)
- +100% set: 1,204 rows, 23 excluded, **1,181 kept** (881 tickers); breakout classes measurable breakout 594 (50.3%), late base 477 (40.4%), EP gap 100 (8.5%), other 5, no consolidation 5. RESULT matches.
- Trough in 2020: 889 (75.3%). By year 2017 40, 2018 55, 2019 54, 2021 143; growth 2017 +54%, 2019 +35%. Matches.
- Measurable-breakout share under the span ≤ 4 / ≤ 7 / shortest-base variants: 51.4% / 42.8% / 58.9%. Expansion-day test passes 192 (32.3%); base contains the trough 496 (83.5%). Late base: median share of gain at the breakout close 0.502, median base depth 0.332. Median gain 1.4245. All match.
- +50% set: 4,946 kept; measurable breakout 2,215, late base 2,420, EP gap 197. Matches.
- No mixed inputs: every input of `01_episodes.py` is relative to `data` (`daily_closes_all`, `daily_raw_close`, `symbol_guard.tsv`, `small_pulls.psv`, `cb702_sic.psv`; `splits=None`), and all of them exist in `cb702_pre_v2`. The v2 log shows the v2 export path with 12,005,007 rows and 12,532 tickers, which equals `export_stats.tsv`.

## 5. No input dated 2025 or later — PASS
- `sessions.txt` in cb702_pre and cb702_pre_v2: 2016-01-04..2022-06-30, 1,635 sessions each. The v2 log reads the export at 2016-01-04..2022-06-30.
- Latest date in the v2 episode table: peak 2022-06-07. Latest v2 minute file: 2022-01-03 (not read by these steps).
- Every input the libraries read is the daily export or a table derived from it (grep). Every run took the `2017-21` argument; the asserts refuse 2022-24 whenever a switch is set. No path containing `holdout` is opened.

## 6. Old values in RESULT's tables match the docs — PASS (doc text, plus the committed json for the exact decimals)
- Read 2, step 1 (`cb_big_winner_recall_2026-10-22.md`):
  - 994 / 489 / 408 / 89 / 751 (doc L21-23, L181).
  - Variant shares from 495 / 420 / 575 of 994 (L337).
  - 403 (82%), 161 (33%), late base 0.51 and 0.33, gain 1.42 (L345-347, L328).
  - +50% set 4,182 / 1,864 / 2,064 / 162 (L73, L535-537).
  - 1,015 found / 21 excluded: committed `01_episodes_2017-21.txt`.
  - My recount of the old table gives the same exact values.
- Read 1 (`cb_breakout_definition_2026-10-22.md` and `03_numbers.json`):
  - 13,363 fills; first close above the base high 1,548 / 4,989 / 8,110 / 10,214 / 3,149; fill distance 1.16 with 1,098 (8.2%) at or above it (L129, L136).
  - Big movers 5,756: 5,675 / 57 / 24, median sessions 6 and 26 (L146).
  - R1 (n = 9,281): 0.43638 vs 0.42548, +0.01090 (−0.00687..+0.02924); 60-session return +0.17494 (+0.00133..+0.39043) on n = 9,191.
  - R2 (n = 1,582): +0.03103 (+0.00552..+0.05545).
- Read 2, catch (recall doc L37-39, L363, L365): 481 / 240 / 237 / 25 / 3.
- Read 3 (`cb_entry_stop_retry_2026-10-22.md` L45, L211; `03_headline.json`):
  - Big winners, S2 with two retries: 213 / 8 / 121, mean retries 0.657.
  - R1 S2, no retry: +0.05180 vs +0.04642; +0.00538 (−0.03546..+0.04957); per 100 trades 1.905 vs 1.426; hit rate 0.1782 vs 0.1871.
  - R1 S2, two retries: 0.11089 vs 0.03973; +0.07116 (+0.01564..+0.13556); 3.507 vs 2.124.
  - n = 9,239 = the bases complete at 120 sessions (doc L58, L376). It is a different population from read 1's 9,281, and both counts are real.
- Read 4 (`cb_trail_variants_2026-10-23.md` L50-63, L203, L208; `03_headline.json`):
  - `pp` cell: 213 / 8 / 121, median share kept 0.054, median 18 sessions held.
  - A20_X3_P0 cell: 256 / 92 / 191, median share kept 0.0863, median 25 sessions held.
  - R1 with no retry: `pp` +0.0054 and +0.478; A20_X3_P0 +0.0095 and +0.600.

## Verdict: **PASS** — no fix needed
- Not re-hashed by me: `bdef_control` and the two parquets. RESULT's own receipt passes them, and every file built from them compares byte-equal or json-equal.
