#!/bin/bash
# Block 5 / P3 — ONE supplementary read-only prod pull: MA warm-up daily bars for the same
# fired names, BEFORE the P0 window (P0 pulled min(fire_date)-65d = 2026-06-21 onward, ~45
# sessions — too short for a 50-DMA / 65-EMA at an August fire). Same query shape as
# extract_p0.sh; mi_daily_closes is continuously adjusted, so this must be pulled on the same
# table state as P0 (pull time recorded in README). $0, gitignored output.
set -euo pipefail
cd "$(dirname "$0")"
HOST="apollo@87.99.134.162"
PSQL='docker exec -i apollo-postgres psql -U apollo -d apollo -v ON_ERROR_STOP=1'

echo "[1/1] mi_daily_closes — every fired name, 2025-12-01 .. (min(fire_date)-65d - 1)"
ssh "$HOST" "$PSQL -c \"\\copy (
  SELECT dc.trade_date, dc.ticker, dc.close, dc.volume, dc.open_price, dc.high_price, dc.low_price
  FROM mi_daily_closes dc
  WHERE dc.ticker IN (SELECT DISTINCT ticker FROM mi_delayed_entry_trigger)
    AND dc.trade_date >= DATE '2025-12-01'
    AND dc.trade_date <  (SELECT MIN(fire_date) - INTERVAL '65 days' FROM mi_delayed_entry_trigger)::date
  ORDER BY dc.ticker, dc.trade_date
) TO STDOUT WITH CSV HEADER\"" > daily_closes_warmup.csv
date -u +"pulled_at_utc=%Y-%m-%dT%H:%M:%SZ" | tee daily_closes_warmup.pulled_at
wc -l daily_closes_warmup.csv; du -sh daily_closes_warmup.csv
