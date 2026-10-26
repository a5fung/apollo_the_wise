#!/bin/bash
# #705 v2 re-run, STAGE 6 + STAGE 4 (docs/analysis/cb_2017_21_rerun_v2_prereg_2026-10-25.md §3 rows 4 / 6, §4 B4): reads 1-4 on cb702_pre_v2, run ONCE,
# after stages 1-3 (runner.py v2-pre-read / v2-h60-read / v2-exit-read) and stage 5 (02_build_paths.py with CB_PRE_DIR) have written their tables.
#   - FIRST the §8 freeze re-check (v2_chain.py freeze-recheck = runner.py v2-exit-read --dry-run: every footer pin, this script included): exit 2
#   - every prerequisite is checked against the chain manifest ($V/out/v2_chain_manifest.tsv, hash-chained, append-only) BEFORE anything runs: exit 2
#   - stage 5's checks file (_702_r_decomposition_1022/rerun_v2_1025/02_build_checks_2017-21.txt, its CB_PRE_LOG) must carry the calendar line (B6): exit 2
#   - outputs go to rerun_v2_1025/ only ($V/out/rerun_v2_1025/<read>/ and each probe dir's rerun_v2_1025/) - rerun_1023/ keeps the 10-23 v2 episode
#     tables as a check target; an existing rerun_v2_1025/ dir refuses (once-only): exit 2
#   - read 2's episode step must equal the 10-23 v2 tables by decompressed bytes: exit 2
#   - after each step that builds its own calendar from the export (read 2's episodes and catch, reads 1 / 3 / 4's builds), its log must carry the
#     calendar line 1635 sessions (2016-01-04..2022-06-30) (B6; each script's own spelling): exit 2
#   - every read's main tables must carry rows on restored tickers (B8): exit 3
#   - after read 4: its pp cell (A20_X1_P1) must equal read 3's S2 cell to 1e-9 (§3 row 6, parity (c); v2_chain.py pp-parity): exit 2
#   - each read's tables AND its numbers / report files (the read dir's rerun_v2_1025/03_*: what stage 7 reads) are appended to the manifest,
#     labels derived from the path by v2_chain.chain_label (the one rule stage 7 checks them by)
#   - at the END: stage 4 = G8 (trade_impact.py --kind c0 on trades_pre_exitpb, --kind r1 on read 4's R1 cells) + B9 (the degraded-walk report on
#     stage 3's trades_pre_exitpb (pp) AND stage 1's trades_pre_p5 (c3_p33_t20_cut3, the old file's "5 of 13,368")) - a REPORT, nothing decides;
#     consoles under $LOGROOT/stage4/
# The overrides V2_DIR, PROBES, LOGROOT are honoured ONLY in test mode (V2_CHAIN_TEST=1, which also replaces the freeze re-check by
# V2_TEST_FREEZE_CMD and REFUSES the real cb702_pre_v2); on the real run any of them set refuses (exit 2) and the paths are the literals below.
# `04_relaunch.sh --check-log LOG...` runs the calendar check alone.
set -euo pipefail
REAL_B=/Users/alvinfung/apollo_the_wise/scripts/probes; REAL_V=/Users/alvinfung/apollo_data/cb702_pre_v2
real_of() { (cd "$1" 2>/dev/null && pwd -P) || echo "/nonexistent/$1"; }
if [ "${V2_CHAIN_TEST:-}" = 1 ]; then
  B=${PROBES:-}; V=${V2_DIR:-}
  [ -n "$V" ] && [ -d "$V" ] && [ -n "$B" ] && [ -d "$B" ] \
    || { echo "REFUSED: test mode (V2_CHAIN_TEST=1) needs V2_DIR and PROBES, a scratch data dir and a scratch code tree"; exit 2; }
  [ "$(real_of "$V")" != "$(real_of "$REAL_V")" ] \
    || { echo "REFUSED: test mode (V2_CHAIN_TEST=1) with the REAL $REAL_V - test mode never touches the real chain"; exit 2; }
  [ "$(real_of "$B")" != "$(real_of "$REAL_B")" ] \
    || { echo "REFUSED: test mode (V2_CHAIN_TEST=1) with the REAL $REAL_B - its rerun_v2_1025/ dirs are the real run's (once-only)"; exit 2; }
  LOGROOT=${LOGROOT:-$B/_705_rerun_v2_1023/rerun_v2_1025}
  echo "TEST MODE (V2_CHAIN_TEST=1): PROBES=$B V2_DIR=$V LOGROOT=$LOGROOT; the freeze re-check runs V2_TEST_FREEZE_CMD"
else
  for o in PROBES V2_DIR LOGROOT; do
    [ -z "${!o:-}" ] || { echo "REFUSED: $o is set - a test-only override (V2_CHAIN_TEST=1); the real run uses its literal paths"; exit 2; }
  done
  B=$REAL_B; V=$REAL_V; LOGROOT=$REAL_B/_705_rerun_v2_1023/rerun_v2_1025
fi
CHAIN="python3 $B/_cb_backtest/v2_chain.py"
cal_check() { $CHAIN calendar-check "$@" || { echo "REFUSED (B6): a read's calendar is not sessions.txt - the chain stops"; exit 2; }; }
if [ "${1:-}" = "--check-log" ]; then shift; cal_check "$@"; exit 0; fi
R=$V/out/rerun_v2_1025; M=$V/out/v2_chain_manifest.tsv
L() { echo $B/$1/rerun_v2_1025; }
# 0a. the §8 freeze re-check: every footer pin still holds (this script, the read scripts, v2_chain.py, the data, the doc body)
$CHAIN freeze-recheck $V || { echo "REFUSED: the freeze re-check failed - nothing runs"; exit 2; }
# 0b. the prerequisites, each against its manifest line (B4 / B5)
$CHAIN manifest-check-paths $M $V/out/entries_pre_tl_com.tsv.gz $V/out/trades_pre_p5.tsv.gz $V/out/trades_pre_exitpb.tsv.gz \
  $V/out/r_decomp_fills_2017-21.tsv.gz $V/out/r_decomp_control_2017-21.tsv.gz \
  || { echo "REFUSED: a prerequisite is not the table its stage wrote (manifest) - nothing runs"; exit 2; }
for d in $R $(L _702_winner_recall_1022) $(L _702_breakout_definition_1022) $(L _702_entry_stop_retry_1022) $(L _702_trail_variants_1023) $LOGROOT; do
  [ ! -e $d ] || { echo "REFUSED: $d exists - the relaunch runs ONCE (the operator inspects and removes it by hand)"; exit 2; }
done
cal_check $B/_702_r_decomposition_1022/rerun_v2_1025/02_build_checks_2017-21.txt     # stage 5's log (B6): its own CB_PRE_LOG dir
mkdir -p $R/{winner_recall,breakout_definition,entry_stop_retry,trail_variants} $(L _702_winner_recall_1022) $(L _702_breakout_definition_1022) \
  $(L _702_entry_stop_retry_1022) $(L _702_trail_variants_1023) $LOGROOT/stage4
export CB_PRE_DIR=$V
step() { local dir=$1 log=$2; shift 2; ( cd $B/$dir && "$@" ) 2>&1 | tee $LOGROOT/$log; }
b8() { $CHAIN restored-count $V "$@" || { echo "REFUSED (B8): no restored-ticker row in $1 - the chain stops"; exit 3; }; }
add() { local stage=$1; shift; $CHAIN manifest-add-paths $M "$stage" "$@"; }     # labels derived from the paths (v2_chain.chain_label)
# 2 winner recall: episodes (must equal the 10-23 v2 tables), catch, report
W="env CB_PRE_OUT=$R/winner_recall CB_PRE_LOG=$(L _702_winner_recall_1022)"
step _702_winner_recall_1022 read2_01_episodes.log $W python3 01_episodes.py 2017-21
cal_check $LOGROOT/read2_01_episodes.log
for t in x200 x150; do
  $CHAIN gz-equal $R/winner_recall/wrecall_episodes_2017-21_$t.tsv.gz $V/out/rerun_1023/winner_recall/wrecall_episodes_2017-21_$t.tsv.gz \
    || { echo "REFUSED: the episode step does not reproduce the 10-23 v2 table ($t)"; exit 2; }
done
step _702_winner_recall_1022 read2_02_catch.log $W python3 02_catch.py 2017-21
cal_check $LOGROOT/read2_02_catch.log
step _702_winner_recall_1022 read2_03_report.log $W python3 03_report.py 2017-21
b8 $R/winner_recall/wrecall_catch_2017-21_x200.tsv.gz
add "read 2 (winner recall)" $R/winner_recall/wrecall_episodes_2017-21_x200.tsv.gz $R/winner_recall/wrecall_catch_2017-21_x200.tsv.gz \
  $R/winner_recall/wrecall_nights_2017-21_x200.tsv.gz $(L _702_winner_recall_1022)/03_numbers.json $(L _702_winner_recall_1022)/03_report.md
# 1 breakout definition
D1="env CB_PRE_OUT=$R/breakout_definition CB_PRE_LOG=$(L _702_breakout_definition_1022)"
step _702_breakout_definition_1022 read1_02_build.log $D1 python3 02_build.py 2017-21
cal_check $LOGROOT/read1_02_build.log
step _702_breakout_definition_1022 read1_03_report.log $D1 python3 03_report.py 2017-21
b8 $R/breakout_definition/bdef_fills_2017-21.tsv.gz
b8 $R/breakout_definition/bdef_r1_2017-21.tsv.gz
add "read 1 (breakout definition)" $R/breakout_definition/bdef_fills_2017-21.tsv.gz $R/breakout_definition/bdef_r1_2017-21.tsv.gz \
  $R/breakout_definition/bdef_control_2017-21.tsv.gz $(L _702_breakout_definition_1022)/03_numbers.json $(L _702_breakout_definition_1022)/03_report.md
# 3 and 4 read the step-1/2 tables from their own CB_PRE_OUT dir: link them in
for r in entry_stop_retry trail_variants; do
  for f in bdef_r1_2017-21.tsv.gz bdef_control_2017-21.tsv.gz; do ln -sf $R/breakout_definition/$f $R/$r/$f; done
  for f in wrecall_episodes_2017-21_x200.tsv.gz wrecall_catch_2017-21_x200.tsv.gz; do ln -sf $R/winner_recall/$f $R/$r/$f; done
done
# 3 entry x stop x retry
step _702_entry_stop_retry_1022 read3_02_build.log env CB_PRE_OUT=$R/entry_stop_retry CB_PRE_LOG=$(L _702_entry_stop_retry_1022) python3 02_build.py 2017-21
cal_check $LOGROOT/read3_02_build.log
step _702_entry_stop_retry_1022 read3_03_report.log env CB_PRE_LOG=$(L _702_entry_stop_retry_1022) python3 03_report.py 2017-21
b8 $R/entry_stop_retry/esr_win_2017-21.tsv.gz
b8 $R/entry_stop_retry/esr_r1_2017-21.tsv.gz
add "read 3 (entry stop retry)" $R/entry_stop_retry/esr_win_2017-21.tsv.gz $R/entry_stop_retry/esr_r1_2017-21.tsv.gz \
  $(L _702_entry_stop_retry_1022)/03_headline.json $(L _702_entry_stop_retry_1022)/03_report.md
# 4 trail variants; CB_PRE_ESR = read 3's rerun logs (its seed-702 control draw and numbers, and the control size)
step _702_trail_variants_1023 read4_02_build.log env CB_PRE_OUT=$R/trail_variants CB_PRE_LOG=$(L _702_trail_variants_1023) CB_PRE_ESR=$(L _702_entry_stop_retry_1022) python3 02_build.py 2017-21
cal_check $LOGROOT/read4_02_build.log
step _702_trail_variants_1023 read4_03_report.log env CB_PRE_LOG=$(L _702_trail_variants_1023) python3 03_report.py 2017-21
b8 $R/trail_variants/trail_win_2017-21.tsv.gz
b8 $R/trail_variants/trail_r1_2017-21.tsv.gz
add "read 4 (trail variants)" $R/trail_variants/trail_win_2017-21.tsv.gz $R/trail_variants/trail_r1_2017-21.tsv.gz \
  $(L _702_trail_variants_1023)/03_headline.json $(L _702_trail_variants_1023)/03_report.md
$CHAIN pp-parity $(L _702_entry_stop_retry_1022)/03_headline.json $(L _702_trail_variants_1023)/03_headline.json \
  || { echo "REFUSED (4.0): read 4's pp cell is not read 3's S2 cell - the chain stops"; exit 2; }
# STAGE 4 (a report; nothing decides): G8 on the C0 list and read 4's two R1 cells, then B9
TI="python3 $B/../backtest_data_audit/trade_impact.py --flags $V/audit_1023/price/A_flags.tsv --export $V/daily_closes_all.csv.gz"
$TI --trades $V/out/trades_pre_exitpb.tsv.gz --kind c0 --label v2 2>&1 | tee $LOGROOT/stage4/g8_c0.txt
for c in A20_X3_P0 A20_X1_P1; do
  $TI --trades $R/trail_variants/trail_r1_2017-21.tsv.gz --kind r1 --cell $c --label v2 2>&1 | tee $LOGROOT/stage4/g8_r1_$c.txt
done
DG="python3 $B/_705_rerun_v2_1023/v2_degraded.py --export $V/daily_closes_all.csv.gz --raw $V/daily_raw_close.csv.gz --guard-new $V/symbol_guard.tsv \
  --guard-old $V/../cb702_pre/symbol_guard.tsv --sessions $V/sessions.txt --export-last 2022-06-30"
$DG --trades $V/out/trades_pre_exitpb.tsv.gz --arm pp --entry orh5 --label "stage 3 (exit read, pp)" 2>&1 | tee $LOGROOT/stage4/b9_degraded.txt
$DG --trades $V/out/trades_pre_p5.tsv.gz --arm c3_p33_t20_cut3 --entry '' --label "stage 1 (pre-read, c3_p33_t20_cut3)" 2>&1 | tee $LOGROOT/stage4/b9_degraded_p5.txt
echo "RELAUNCH DONE: reads 1-4 under $R and */rerun_v2_1025/; stage 4 consoles under $LOGROOT/stage4/; next: v2_compare.py (stage 7)"
