#!/usr/bin/env bash
# #624 backfill Polygon helper.  push <localfile> <container-name-under-/tmp/_624bf>  |  run-fg <args>  |  run-bg <args>  |  pull <container-name> [local-name]
set -euo pipefail
HOST=apollo@87.99.134.162; C=apollo-market; R=/tmp/_624bf
cmd="$1"; shift
case "$cmd" in
  push) scp -q "$1" $HOST:/tmp/_624bf_push_$2 && ssh -o ConnectTimeout=25 $HOST "docker exec $C mkdir -p $R && docker cp /tmp/_624bf_push_$2 $C:$R/$2 && rm -f /tmp/_624bf_push_$2" ;;
  run-fg) ssh -o ConnectTimeout=25 $HOST "docker exec -w /app $C python $R/poly_fetch.py $*" ;;
  run-bg) ssh -o ConnectTimeout=25 $HOST "docker exec -d -w /app $C sh -c 'python $R/poly_fetch.py $* > $R/stdout_$(echo $* | tr ' ' '_').txt 2>&1'" ;;
  pull) L="${2:-$1}"; ssh -o ConnectTimeout=25 $HOST "mkdir -p /tmp/_624bf_host && docker cp $C:$R/$1 /tmp/_624bf_host/$1 && gzip -kf /tmp/_624bf_host/$1" && scp -q $HOST:/tmp/_624bf_host/$1.gz ./$L.gz ;;
  status) ssh -o ConnectTimeout=25 $HOST "docker exec $C sh -c 'cd $R && wc -l log_min_* ref_*.jsonl 2>/dev/null; ls done_* 2>/dev/null; ps aux | grep poly_fetch | grep -v grep | wc -l'" ;;
esac
