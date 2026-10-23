# #705 — the four 2017-21 reads re-run on the rebuilt file (cb702_pre_v2): parity on all four, new numbers only for the first step of the recall read; every downstream step is BLOCKED upstream

**Answer.** All four reads reproduce their cited numbers EXACTLY from `cb702_pre` through the new path switches (34 of 34 files identical).
Only `01_episodes.py` (the big-winner list) can run on v2: big winners 994 -> 1,181 (+19%), mix unchanged. Every downstream step (read 1, read 2's catch step, reads 3 and 4) needs
v2 versions of our own fills and trades (`r_decomp_fills`, `entries_pre_tl_com`, `trades_pre_exitpb`) that the minute stage and exit read never produced on v2.
Those two registered stages are freeze-pinned to `cb702_pre` and refuse v2 — not worked around. Nothing a doc cites was overwritten (checked by hash / size+mtime).

## 0. The switches (default = byte-for-byte today)

| variable | meaning | default |
|---|---|---|
| `CB_PRE_DIR` | the 2017-21 data dir (export, sidecars, and the runner-made `out/` tables: watch, entries, trades, r_decomp_*) | `/Users/alvinfung/apollo_data/cb702_pre` |
| `CB_PRE_OUT` | where the tables the READS make are written and read (`wrecall_*`, `bdef_*`, `esr_*`, `trail_*`) | `<data>/out` |
| `CB_PRE_LOG` | where logs, numbers json, report text and sample files go | the probe dir |
| `CB_PRE_ESR` | trail read only: where the entry-stop-retry read's `02_sample_*` / `02_numbers_*.json` are read | `_702_entry_stop_retry_1022` |

- Only the 2017-21 era honours them: the scripts assert `eras == ["2017-21"]` when `CB_PRE_OUT` / `CB_PRE_LOG` are set; the three report scripts take an era argument (`python3 03_report.py 2017-21`).
- Edited (11): winner_recall `01_episodes.py 02_catch.py 03_report.py`; breakout_definition `02_build.py 03_report.py`; entry_stop_retry `esr_lib.py 02_build.py 03_report.py`; trail_variants `trail_lib.py 02_build.py 03_report.py`. `_cb_backtest/` and `_qm_streams/` untouched.
- One real hazard fixed on the way: `trail_variants/02_build.py` hard-codes the control size `2096517`; with `CB_PRE_ESR` set it reads the size from that run's entry-stop-retry numbers instead (default unchanged).
- Default-path proof (`02_default_paths_check.py`, no variable set): 16 of 16 checks ok — every resolved data dir / table dir / log dir equals the original literal (`02_default_paths_check.txt`).

## 1. Parity (inputs = cb702_pre, outputs = `cb702_pre_v2/out/rerun_1023/parity/<read>/`) — `03_parity_compare.py`, receipt `parity_results.txt`

| read | files compared | result |
|---|---|---|
| 1 breakout_definition | 4 tables (`bdef_fills/r1/kvar/control`), checks txt, `03_numbers.json` (2017-21 part), `03_report.md` (2017-21 section) | **diff empty**, 7 of 7 |
| 2 winner_recall | 6 tables (`wrecall_episodes/catch/nights` x200/x150), 3 logs, `03_numbers.json` (2017-21 part), `03_report.md` | **diff empty**, 11 of 11 |
| 3 entry_stop_retry | `esr_win/r1/ctlsample`, `esr_ctl.parquet` (sha256), `02_numbers_2017-21.json`, both `02_sample_*`, `03_headline.json`, `03_report.md` | **diff empty**, 9 of 9 |
| 4 trail_variants | `trail_win/r1/ctlsample`, `trail_ctlmatch.parquet` (sha256), `02_numbers_2017-21.json`, `03_headline.json`, `03_report.md` | **diff empty**, 7 of 7 |

- Compared as: `.tsv.gz` by DECOMPRESSED bytes (gzip headers carry an mtime), parquet by sha256, json by equality (2017-21 part where the cited file also holds 2022-24), logs after masking wall-clock seconds and data paths.
- Read 4's own parity (c) (the `pp` baseline cell must reproduce read 3's numbers to 1e-9) also passed inside the run.
- Reads 3 and 4 read the step-1/2 tables from their own `CB_PRE_OUT` dir: the parity dirs hold symlinks to the parity outputs of reads 1 and 2 (`bdef_r1`, `bdef_control`, `wrecall_episodes_x200`, `wrecall_catch_x200`).
- Same seeds / fixed choices as before (seed 702, 2,000 month-block resamples). No bar dated 2025-01-01 or later was read (both exports end 2022-06-30); no network; no subagents.

Parity command lines (`P=/Users/alvinfung/apollo_data/cb702_pre`, `R=/Users/alvinfung/apollo_data/cb702_pre_v2/out/rerun_1023`, `D=$R/parity/<read>`):
```
winner_recall:        CB_PRE_DIR=$P CB_PRE_OUT=$D CB_PRE_LOG=$D python3 01_episodes.py 2017-21 | 02_catch.py 2017-21 | 03_report.py 2017-21
breakout_definition:  CB_PRE_DIR=$P CB_PRE_OUT=$D CB_PRE_LOG=$D python3 02_build.py 2017-21 ; CB_PRE_OUT=$D CB_PRE_LOG=$D python3 03_report.py 2017-21
entry_stop_retry:     CB_PRE_DIR=$P CB_PRE_OUT=$D CB_PRE_LOG=$D python3 02_build.py 2017-21 ; CB_PRE_LOG=$D python3 03_report.py 2017-21
trail_variants:       CB_PRE_DIR=$P CB_PRE_OUT=$D CB_PRE_LOG=$D CB_PRE_ESR=$R/parity/entry_stop_retry python3 02_build.py 2017-21 ; CB_PRE_LOG=$D python3 03_report.py 2017-21
```

## 2. Read 2, step 1 (the ONLY step that runs on v2) — big winners, old (cb702_pre) | new (v2) | change

Command: `V=/Users/alvinfung/apollo_data/cb702_pre_v2; CB_PRE_DIR=$V CB_PRE_OUT=$V/out/rerun_1023/winner_recall CB_PRE_LOG=scripts/probes/_702_winner_recall_1022/rerun_1023 python3 01_episodes.py 2017-21`
(table made by `01_episodes_old_vs_new.py`, which calls the read's own `composition()` unchanged; full list in `episodes_old_vs_new.md` / `.json`). Export: 12,005,007 rows, 12,532 tickers (old 10,320,661 / 9,944), 1,635 sessions, same calendar.

The +100% set (a close at least doubled from its trough within 63 sessions):

| number (named as computed) | old | new | change |
|---|---|---|---|
| episodes found (all) | 1,015 | 1,204 | +189 (+18.6%) |
| excluded (artifact jump or identity break) | 21 | 23 | +2 |
| **big winners kept (n)** | **994** | **1,181** | **+187 (+18.8%)** |
| class_p = measurable_breakout (n) | 489 (49.2%) | 594 (50.3%) | +105 (+21.5%) |
| class_p = late_base (n) | 408 (41.0%) | 477 (40.4%) | +69 (+16.9%) |
| class_p = ep_gap (n) | 89 (9.0%) | 100 (8.5%) | +11 (+12.4%) |
| class_p = other / no_consolidation (n) | 4 / 4 | 5 / 5 | +1 / +1 |
| measurable breakouts under span <= 4 ADR / <= 7 ADR / shortest base (share of kept) | 49.8% / 42.3% / 57.8% | 51.4% / 42.8% / 58.9% | +1.6 / +0.5 / +1.1 pts |
| measurable breakouts that pass the expansion-day test (n; share of measurable) | 161 (32.9%) | 192 (32.3%) | +31 |
| measurable breakouts whose base contains the trough (n; share) | 403 (82.4%) | 496 (83.5%) | +93 |
| episodes with the trough in 2020 (n; share of kept) | 751 (75.6%) | 889 (75.3%) | +138 |
| late-base: share of the gain already made at the breakout close, median | 0.505 | 0.502 | -0.003 |
| late-base: base depth, median | 0.332 | 0.332 | 0.000 |
| gain trough -> peak, median | 1.423 | 1.425 | +0.002 |

The +50% sensitivity set: kept 4,182 -> 4,946 (+18.3%); measurable breakout 1,864 (44.6%) -> 2,215 (44.8%); late base 2,064 (49.4%) -> 2,420 (48.9%); EP gap 162 (3.9%) -> 197 (4.0%).

## 3. BLOCKED — what the other reads need from v2 and who makes it (verified by running each first step on v2: all stop on `FileNotFoundError`, logs `scripts/probes/<dir>/rerun_1023/02_blocked_run_2017-21.txt`)

| read | first missing v2 file | made by (not run on v2) |
|---|---|---|
| 2 winner_recall `02_catch.py` | `out/trades_pre_exitpb.tsv.gz`, `out/entries_pre_tl_com.tsv.gz` | `runner.py exit-read --period pre` (needs `trades_pre_p5` from `pre-read` AND `trades_pre_h60` from `h60-read --period pre`; freeze check pins cb702_pre's files by hash, so v2 exits 2 — read from `exitpb_frozen_files` / `run_exit_read`, not executed); `runner.py pre-read` |
| 1 breakout_definition `02_build.py` | `out/r_decomp_fills_2017-21.tsv.gz` (+ `r_decomp_control_2017-21.tsv.gz`, `entries_pre_tl_com.tsv.gz`) | `_702_r_decomposition_1022/02_build_paths.py` — **a fifth read the task list omitted**; it reads `trades_pre_exitpb` |
| 3 entry_stop_retry `02_build.py` | reads 1 and 2 outputs (`bdef_r1`, `bdef_control`, `wrecall_episodes/catch` x200) | reads 1 and 2 |
| 4 trail_variants `02_build.py` | the same, plus read 3's `02_sample_*` / `02_numbers_*.json` | reads 1, 2, 3 |

- `pre-read` itself is ready on v2: `runner.py pre-read --data cb702_pre_v2 --dry-run` (counts only, nothing opened) reads 45,142 first-break rows (tl 20,650, com 24,492; old 38,054 = tl 17,405 + com 20,649) needing 33,884 date-ticker minute pairs on 1,219 dates, **0 pairs missing from `_done.psv`**, verdict "complete". It has no freeze check but writes to `<data>/out` only and is once-only.
- `exit-read` / `h60-read` are registered once-only reads whose freeze map pins `cb702_pre/out/*` and both minute trees by hash; on v2 they would exit 2 (from the code; not executed). Running them is a registration decision, not a mechanical re-run.
- Ready for the day it unblocks: `04_relaunch.sh` (same command shapes as the parity runs; checks the four prerequisites first, exits 2 while they are missing; NOT YET RUN on v2).

Old numbers each blocked read will have to be compared against (named as computed; new = blocked):

| read | number | old (cb702_pre) | new (v2) |
|---|---|---|---|
| 1 | published C0 tl ORH5 fills with a readable E bar (n) | 13,363 | blocked |
| 1 | `A_sc`: first close above the base high on E / by 5 / by 20 / by 60 / never (of n = 13,363) | 1,548 / 4,989 / 8,110 / 10,214 / 3,149 | blocked |
| 1 | fill distance below the base high, median ADR20 (fills at/above it) | 1.16 (1,098 = 8.2%) | blocked |
| 1 | `A_big` +5 ADR movers (n): closed above first / after / never; median s_c; median s\* | 5,756: 5,675 / 57 / 24; 6; 26 | blocked |
| 1 | R1 (n = 9,281) share >= 5 ADR within 60: entries vs matched control; difference (95% interval) | 0.4364 vs 0.4255; +0.0109 (-0.0069 .. +0.0292) | blocked |
| 1 | R1 mean close return +60 (ADR): difference | +0.1749 (+0.0013 .. +0.3904), n = 9,191 | blocked |
| 1 | R2 (n = 1,582) share >= 5 ADR within 60: difference | +0.0310 (+0.0055 .. +0.0554) | blocked |
| 2 | measurable breakouts covered / watched / triggered / still in at half / kept half (of 481 covered, x200) | 481 / 240 / 237 / 25 / 3 | blocked |
| 3 | P-win S2 two retries (n = 481): still in at half / kept half / kept a quarter / retries mean | 213 / 8 / 121 / 0.657 | blocked |
| 3 | R1 S2 no retry (n = 9,239): r_per_trade vs control; r_per_base difference; any >= 5R per 100 vs control; race +5R hit | +0.0518 vs +0.0464; +0.0054 (-0.0355 .. +0.0496); 1.905 vs 1.426; 0.1782 vs 0.1871 | blocked |
| 3 | R1 S2 two retries: r_per_base vs control; difference; any >= 5R per 100 vs control | +0.1109 vs +0.0397; +0.0712 (+0.0156 .. +0.1356); 3.507 vs 2.124 | blocked |
| 4 | `pp` cell A20_X1_P1 (n = 481): still in at half / kept half / kept a quarter; median share kept; median sessions held | 213 / 8 / 121; 0.054; 18 | blocked |
| 4 | best-holding cell A20_X3_P0: still in at half / kept half / kept a quarter; median share kept; median sessions held | 256 / 92 / 191; 0.0863; 25 | blocked |
| 4 | the same two cells on R1, no retry: r_per_base difference vs control; any >= 5R per 100 difference | pp +0.0054, +0.478; A20_X3_P0 +0.0095, +0.600 | blocked |

## 4. What holds, what moves

- **Holds (the one thing measurable):** the recall doc's population picture is stable on the corrected list — about half of big winners start with a measurable breakout (49.2% -> 50.3%), about 4 in 10 are late bases (41.0% -> 40.4%), roughly 1 in 11 start with an EP gap, 3 in 4 doublers trough in 2020, and the expansion-day test still passes on one in three; the sensitivity variants move 0.5-1.6 points.
- **Moves:** the absolute counts. 994 big winners becomes 1,181 (+19%) and the three big classes grow 12-22%, in line with the survivorship measurement (26% of liquid +100% runners absent from the old file); every count the doc quotes (994, 489, 408, 89, 751 ...) is survivors-only until redone, and the 2017 and 2019 troughs grow fastest (+54%, +35%).
- **Cannot be said yet:** whether we saw / triggered / kept the winners (481 covered, 240 watched ...), whether our trigger was early, the stop x retry cells, and every trail cell — all of them need the v2 fills and trades. Their conclusions stay labelled survivors-only.
- **The fork for the main loop (operator-facing, one line):** run the registered `pre-read` (ready, 0 missing pairs) -> `h60-read --period pre` -> `exit-read --period pre` on v2 — the last two need a v2 freeze registration — plus `_702_r_decomposition_1022/02_build_paths.py`, then `04_relaunch.sh`; or keep the 2017-21 doc numbers labelled survivors-only.

## 5. Safety receipts and files

- Before / after hashes (probe dirs, `_cb_backtest`, `_702_r_decomposition_1022`) and size+mtime (`cb702_pre/out`, `cb702/out`, `cb702_pre_v2` outside `out/rerun_1023`): the only changes are the 11 edited scripts.
- New outputs: `cb702_pre_v2/out/rerun_1023/parity/<read>/` (about 2.0 GB, deletable once the receipt is kept), `cb702_pre_v2/out/rerun_1023/winner_recall/` (v2 episodes, 1 MB), `scripts/probes/_702_*/rerun_1023/` (v2 episode log, blocked-run logs), this directory.
- This directory: `RESULT.md`, `01_episodes_old_vs_new.{py,md,json}`, `02_default_paths_check.{py,txt}`, `03_parity_compare.py` + `parity_results.txt`, `04_relaunch.sh`.
- Not done: reads 1, 2 (catch), 3, 4 on v2 (blocked above); `_702_r_decomposition_1022/02_build_paths.py` got no switch (outside the four named reads; it is the prerequisite for read 1). No commit made.
