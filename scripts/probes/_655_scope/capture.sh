#!/bin/bash
# #655 scope capture — run ONCE; everything downstream reads capture.raw.gz. Read-only transaction.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -X -q -v ON_ERROR_STOP=1" \
  < "$here/q1_capture.sql" 2> "$here/capture.err" | gzip > "$here/capture.raw.gz"
ls -la "$here/capture.raw.gz"; cat "$here/capture.err"
