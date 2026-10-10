#!/bin/bash
# #655(a) replay capture — run ONCE; the replay reads cap_rows_30d.jsonl. Read-only transaction.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -X -q -v ON_ERROR_STOP=1" \
  < "$here/capture.sql" > "$here/cap_rows_30d.jsonl" 2> "$here/capture.err"
wc -l "$here/cap_rows_30d.jsonl"
