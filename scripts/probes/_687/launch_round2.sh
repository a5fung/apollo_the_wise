#!/usr/bin/env bash
# #687 round-2 fetch: the line-test days from pass 1 (fetch_list_held.txt), same paced fetcher, tag "held".
set -euo pipefail
TAG="${1:-held}"; LIST="${2:-fetch_list_held.txt}"
HOST=apollo@87.99.134.162
scp -q "$LIST" $HOST:/tmp/_687_fetch_list_$TAG.txt
ssh -o ConnectTimeout=25 $HOST "docker cp /tmp/_687_fetch_list_$TAG.txt apollo-market:/tmp/_687_fetch_list_$TAG.txt && docker exec -d -w /app apollo-market sh -c 'python /tmp/fetch_minutes.py $TAG > /tmp/_687_fetch_$TAG.stdout 2>&1'"
date -u +"started_at_utc=%Y-%m-%dT%H:%M:%SZ" > fetch_$TAG.started_at
echo "launched $TAG with $(wc -l < "$LIST") keys"
