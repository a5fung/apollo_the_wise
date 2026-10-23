#!/bin/bash
# #705 v2 re-run: reads 1-4 on cb702_pre_v2, to run ONCE the three upstream tables exist under $V/out/ (see RESULT.md "BLOCKED"):
#   r_decomp_fills_2017-21.tsv.gz + r_decomp_control_2017-21.tsv.gz   (_702_r_decomposition_1022/02_build_paths.py)
#   entries_pre_tl_com.tsv.gz                                          (runner pre-read)
#   trades_pre_exitpb.tsv.gz                                           (runner exit-read --period pre)
# Same command shapes as the parity runs (all 34 files identical); outputs only under $R and each probe dir's rerun_1023/. NOT YET RUN on v2.
set -euo pipefail
V=/Users/alvinfung/apollo_data/cb702_pre_v2; R=$V/out/rerun_1023; B=/Users/alvinfung/apollo_the_wise/scripts/probes
for f in r_decomp_fills_2017-21.tsv.gz r_decomp_control_2017-21.tsv.gz entries_pre_tl_com.tsv.gz trades_pre_exitpb.tsv.gz; do
  [ -f $V/out/$f ] || { echo "BLOCKED: $V/out/$f is missing"; exit 2; }
done
L() { echo $B/$1/rerun_1023; }
mkdir -p $R/{winner_recall,breakout_definition,entry_stop_retry,trail_variants} $(L _702_winner_recall_1022) $(L _702_breakout_definition_1022) $(L _702_entry_stop_retry_1022) $(L _702_trail_variants_1023)
export CB_PRE_DIR=$V
# 2 winner recall: episodes, catch, report (read 1 below does not need it, reads 3 and 4 do)
( cd $B/_702_winner_recall_1022; CB_PRE_OUT=$R/winner_recall CB_PRE_LOG=$(L _702_winner_recall_1022) python3 01_episodes.py 2017-21
  CB_PRE_OUT=$R/winner_recall CB_PRE_LOG=$(L _702_winner_recall_1022) python3 02_catch.py 2017-21
  CB_PRE_OUT=$R/winner_recall CB_PRE_LOG=$(L _702_winner_recall_1022) python3 03_report.py 2017-21 )
# 1 breakout definition
( cd $B/_702_breakout_definition_1022; CB_PRE_OUT=$R/breakout_definition CB_PRE_LOG=$(L _702_breakout_definition_1022) python3 02_build.py 2017-21
  CB_PRE_OUT=$R/breakout_definition CB_PRE_LOG=$(L _702_breakout_definition_1022) python3 03_report.py 2017-21 )
# 3 and 4 read the step-1/2 tables from their own CB_PRE_OUT dir: link them in
for r in entry_stop_retry trail_variants; do
  for f in bdef_r1_2017-21.tsv.gz bdef_control_2017-21.tsv.gz; do ln -sf $R/breakout_definition/$f $R/$r/$f; done
  for f in wrecall_episodes_2017-21_x200.tsv.gz wrecall_catch_2017-21_x200.tsv.gz; do ln -sf $R/winner_recall/$f $R/$r/$f; done
done
# 3 entry x stop x retry (about 3 min)
( cd $B/_702_entry_stop_retry_1022; CB_PRE_OUT=$R/entry_stop_retry CB_PRE_LOG=$(L _702_entry_stop_retry_1022) python3 02_build.py 2017-21
  CB_PRE_LOG=$(L _702_entry_stop_retry_1022) python3 03_report.py 2017-21 )
# 4 trail variants (about 3 min); CB_PRE_ESR = read 3's rerun logs (its seed-702 control draw and numbers, and the control size)
( cd $B/_702_trail_variants_1023; CB_PRE_OUT=$R/trail_variants CB_PRE_LOG=$(L _702_trail_variants_1023) CB_PRE_ESR=$(L _702_entry_stop_retry_1022) python3 02_build.py 2017-21
  CB_PRE_LOG=$(L _702_trail_variants_1023) python3 03_report.py 2017-21 )
