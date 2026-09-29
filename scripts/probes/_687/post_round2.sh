#!/usr/bin/env bash
# #687: after the round-2 fetch — copy the held-day capture out and run the FINAL pass (anchor + population + arms).
set -euo pipefail
cd "$(dirname "$0")"
bash copy_out.sh held
cd /Users/alvinfung/apollo_the_wise
python3 scripts/probes/_687/backfill.py --final > scripts/probes/_687/final_run.stdout 2>&1 || { echo "FINAL FAILED"; tail -8 scripts/probes/_687/final_run.stdout; exit 2; }
grep -v "^    " scripts/probes/_687/backfill_out__final.txt | head -80
