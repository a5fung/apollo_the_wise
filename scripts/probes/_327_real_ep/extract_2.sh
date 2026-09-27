#!/bin/bash
# #327 real-EP rerun (2026-09-26) — pull 2 of 2, read-only, $0: 1-min bars for every (ticker, ET session)
# inside a campaign window (2 warm-up sessions + EP day + 20 forward sessions) that mi_intraday_bars
# holds (window_pairs.tsv, from mincov.tsv). Same columns as the 09-01 backfill's _562bf_minute.tsv.gz
# (ticker|d|t_ms|o|h|l|c|v) so the backfill probe's own loader reads it. Output gzipped + gitignored.
set -euo pipefail
cd "$(dirname "$0")"
HOST="apollo@87.99.134.162"
PSQL='docker exec -i apollo-postgres psql -U apollo -d apollo -A -v ON_ERROR_STOP=1'
VALS=$(awk -F'|' 'NR>1 {printf "%s('\''%s'\'',DATE '\''%s'\'')", (NR>2?",":""), $1, $2}' window_pairs.tsv)
{
  echo "WITH p(ticker, d) AS (VALUES $VALS)"
  echo "SELECT b.ticker, p.d, (extract(epoch FROM b.bar_time)*1000)::bigint AS t_ms, b.open AS o, b.high AS h, b.low AS l, b.close AS c, b.volume AS v"
  echo "FROM p JOIN mi_intraday_bars b ON b.ticker = p.ticker AND b.bar_time >= (p.d::timestamp AT TIME ZONE 'America/New_York') AND b.bar_time < ((p.d + 1)::timestamp AT TIME ZONE 'America/New_York')"
  echo "ORDER BY b.ticker, b.bar_time;"
} > minute_pull.sql
ssh "$HOST" "$PSQL" < minute_pull.sql | gzip > minute.tsv.gz
date -u +"pulled_at_utc=%Y-%m-%dT%H:%M:%SZ" | tee extract_2.pulled_at
du -sh minute.tsv.gz; gzcat minute.tsv.gz | tail -1; gzcat minute.tsv.gz | head -2
