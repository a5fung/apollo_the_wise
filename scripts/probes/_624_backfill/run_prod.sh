#!/usr/bin/env bash
# #624 backfill: run a READ-ONLY .py inside apollo-market, capture stdout to <out> ONCE.
# usage: bash run_prod.sh <local.py> <out.txt>
set -euo pipefail
PY="$1"; OUT="$2"; HOST=apollo@87.99.134.162; B=$(basename "$PY")
scp -q "$PY" $HOST:/tmp/_624bf_$B
ssh -o ConnectTimeout=25 $HOST "docker cp /tmp/_624bf_$B apollo-market:/tmp/_624bf_$B && docker exec -e APOLLO_CALL_ORIGIN=probe -w /app apollo-market python /tmp/_624bf_$B" > "$OUT" 2> "${OUT%.txt}.err"
date -u +"pulled_at_utc=%Y-%m-%dT%H:%M:%SZ" > "${OUT%.txt}.pulled_at"
