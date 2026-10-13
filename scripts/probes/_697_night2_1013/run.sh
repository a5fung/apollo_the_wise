#!/usr/bin/env bash
# usage: run.sh <file.sql> [psql -v args...]   -> writes <file>.out next to it. READ-ONLY prod, one capture per file.
# Remote file name is UNIQUE per capture: the shared /tmp/x.sql was overwritten by a parallel session between scp and
# docker cp on the first hold run (the .out held someone else's lowcap-lane script) - see the CONTAMINATED_* file.
set -uo pipefail
f="$1"; shift
vars=""
for v in "$@"; do vars="$vars -v $v"; done
r="x_697n2_$(basename "${f%.sql}").sql"
scp -q "$f" apollo@87.99.134.162:/tmp/$r && ssh apollo@87.99.134.162 "docker cp /tmp/$r apollo-postgres:/tmp/$r && docker exec apollo-postgres sh -c \"psql -U \\\$POSTGRES_USER -d \\\$POSTGRES_DB -A -F '|' $vars -f /tmp/$r\"" > "${f%.sql}.out" 2>&1
echo "exit=$? -> ${f%.sql}.out"
