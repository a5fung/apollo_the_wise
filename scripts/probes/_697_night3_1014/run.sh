#!/usr/bin/env bash
# usage: run.sh <name> [psql -v args...]   reads <name>.sql in this folder, writes <name>.out. READ-ONLY prod, one capture per file.
# Remote file name is UNIQUE per capture (c697_<name>.sql) - a shared /tmp/x.sql was overwritten by a parallel card on 10-13.
set -uo pipefail
cd "$(dirname "$0")"
n="$1"; shift
vars=""
for v in "$@"; do vars="$vars -v $v"; done
r="c697_${n}.sql"
scp -q "$n.sql" "apollo@87.99.134.162:/tmp/$r" && ssh apollo@87.99.134.162 "docker cp /tmp/$r apollo-postgres:/tmp/$r && docker exec apollo-postgres sh -c \"psql -U \\\$POSTGRES_USER -d \\\$POSTGRES_DB -A -F '|' $vars -f /tmp/$r\"" > "$n.out" 2>&1
echo "exit=$? -> $n.out"
