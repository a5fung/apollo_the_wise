#!/usr/bin/env bash
# #687: copy a finished fetch (tag) out of the container: minutes_<tag>.tsv.gz + fetch_log_<tag>.txt
set -euo pipefail
TAG="${1:-entry}"; HOST=apollo@87.99.134.162
ssh -o ConnectTimeout=25 $HOST "docker cp apollo-market:/tmp/_687_minutes_$TAG.tsv /tmp/_687_minutes_$TAG.tsv && docker cp apollo-market:/tmp/_687_fetch_log_$TAG.txt /tmp/_687_fetch_log_$TAG.txt && gzip -f /tmp/_687_minutes_$TAG.tsv"
scp -q $HOST:/tmp/_687_minutes_$TAG.tsv.gz ./minutes_$TAG.tsv.gz
scp -q $HOST:/tmp/_687_fetch_log_$TAG.txt ./fetch_log_$TAG.txt
rm -f ./minutes_$TAG.tsv
date -u +"copied_at_utc=%Y-%m-%dT%H:%M:%SZ" > fetch_$TAG.copied_at
echo "$TAG: $(gzip -dc minutes_$TAG.tsv.gz | wc -l) bar rows, $(wc -l < fetch_log_$TAG.txt) log rows, statuses: $(cut -d'|' -f5 fetch_log_$TAG.txt | sort | uniq -c | tr '\n' ' ')"
