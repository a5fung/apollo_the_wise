#!/usr/bin/env bash
# #687: after the entry-day fetch — copy both workers' captures out, merge the logs, run the anchor (feed half) and
# pass 1 (line-test day list only), then launch round 2.
set -euo pipefail
cd "$(dirname "$0")"
bash copy_out.sh entry
bash copy_out.sh entry2
cat fetch_log_entry.txt fetch_log_entry2.txt | sort -u > fetch_log_entry_merged.txt && mv fetch_log_entry_merged.txt fetch_log_entry.txt && rm -f fetch_log_entry2.txt
echo "merged log rows: $(wc -l < fetch_log_entry.txt); distinct keys: $(cut -d'|' -f1,2 fetch_log_entry.txt | sort -u | wc -l); zero-RTH-bar days: $(awk -F'|' '$4==0' fetch_log_entry.txt | wc -l)"
cd /Users/alvinfung/apollo_the_wise
python3 scripts/probes/_687/backfill.py --anchor > scripts/probes/_687/anchor_run.stdout 2>&1 || { echo "ANCHOR FAILED"; tail -5 scripts/probes/_687/anchor_run.stdout; exit 2; }
grep "^## ANCHOR\|^   FEED\|^    " scripts/probes/_687/anchor_run.stdout | head -40
python3 scripts/probes/_687/backfill.py --pass1 > scripts/probes/_687/pass1_run.stdout 2>&1 || { echo "PASS1 FAILED"; tail -5 scripts/probes/_687/pass1_run.stdout; exit 2; }
grep "^## DATA\|^## JOIN\|^## PASS 1" scripts/probes/_687/pass1_run.stdout
cd scripts/probes/_687 && bash launch_round2.sh held fetch_list_held.txt
