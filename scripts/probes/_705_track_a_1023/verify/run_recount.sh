#!/bin/bash
# Independent recount of #705 Track A join (01_join_labels.py was NOT read when recount.py was first written).
# Date filter is applied AT READ: era B = split 'discovery' and D,E / watch_date <= 2024-12-31; calendars/symbols <= 2024-12-31.
# Only identifier columns are extracted (no price / return / outcome column). No bdef_* table is opened.
set -e
V="$(cd "$(dirname "$0")" && pwd)"; D=/Users/alvinfung/apollo_data
gzip -dc $D/cb702/daily_closes_all.csv.gz | awk -F, '$1=="SPY" && $2<="2024-12-31"{print $2}' | sort -u > $V/spyB.txt
gzip -dc $D/cb702_pre_v2/daily_closes_all.csv.gz | awk -F, '$1=="SPY"{print $2}' | sort -u > $V/spyA.txt
gzip -dc $D/cb702_pre_v2/daily_closes_all.csv.gz | cut -d, -f1 | sort -u > $V/symsA.txt
gzip -dc $D/cb702/daily_closes_all.csv.gz | awk -F, '$2<="2024-12-31"{print $1}' | sort -u > $V/symsB.txt
awk -v want=discovery -v cut=2024-12-31 -f $V/extract_cands.awk $D/cb702/out/candidates.tsv     > $V/candB_main.tsv
awk -v want=discovery -v cut=2024-12-31 -f $V/extract_cands.awk $D/cb702/out/candidates_com.tsv > $V/candB_com.tsv
awk -v want=pre       -v cut=2022-12-31 -f $V/extract_cands.awk $D/cb702_pre_v2/out/candidates_tl_com.tsv > $V/candA.tsv
gzip -dc $D/cb702_pre_v2/out/watch_tl_com.tsv.gz | awk -v want=pre       -v cut=2022-12-31 -f $V/extract_watch.awk > $V/watchA.tsv
gzip -dc $D/cb702/out/watch.tsv.gz               | awk -v want=discovery -v cut=2024-12-31 -f $V/extract_watch.awk > $V/watchB.tsv
python3 $V/recount.py > /dev/null
echo "wrote $V/recount_out.txt and $V/recount_labels.tsv"
