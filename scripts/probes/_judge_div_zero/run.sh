#!/bin/bash
# usage: run.sh <name> "<SQL>"  -> captures to <name>.out once
set -u
out="$(dirname "$0")/$1.out"
{ echo "-- SQL: $2"; ssh apollo@87.99.134.162 "docker exec apollo-postgres psql -U apollo -d apollo -P pager=off -c \"$2\"" 2>&1; } > "$out"
