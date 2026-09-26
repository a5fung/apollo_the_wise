#!/bin/bash
# Block 5 / P0 — one prod extract, read-only, $0. Regenerate any time; CSVs are gitignored.
set -euo pipefail
cd "$(dirname "$0")"
HOST="apollo@87.99.134.162"
PSQL='docker exec -i apollo-postgres psql -U apollo -d apollo -v ON_ERROR_STOP=1'

echo "[1/5] mi_delayed_entry_trigger — all columns, all rows"
ssh "$HOST" "$PSQL -c \"\\copy (SELECT * FROM mi_delayed_entry_trigger ORDER BY id) TO STDOUT WITH CSV HEADER\"" > trigger.csv

echo "[2/5] mi_delayed_entry_watch — all columns, all rows"
ssh "$HOST" "$PSQL -c \"\\copy (SELECT * FROM mi_delayed_entry_watch ORDER BY ticker, ep_date, session_idx) TO STDOUT WITH CSV HEADER\"" > watch.csv

echo "[3/5] mi_daily_closes — every fired name, (min(fire_date)-65d) .. today"
ssh "$HOST" "$PSQL -c \"\\copy (
  SELECT dc.trade_date, dc.ticker, dc.close, dc.volume, dc.open_price, dc.high_price, dc.low_price
  FROM mi_daily_closes dc
  WHERE dc.ticker IN (SELECT DISTINCT ticker FROM mi_delayed_entry_trigger)
    AND dc.trade_date >= (SELECT MIN(fire_date) - INTERVAL '65 days' FROM mi_delayed_entry_trigger)::date
    AND dc.trade_date <= CURRENT_DATE
  ORDER BY dc.ticker, dc.trade_date
) TO STDOUT WITH CSV HEADER\"" > daily_closes.csv

echo "[4/5] mi_intraday_bars — per-fire day-0 coverage (aggregated: no raw bars pulled)"
ssh "$HOST" "$PSQL -c \"\\copy (
  WITH fires AS (
    SELECT DISTINCT ticker, fire_date FROM mi_delayed_entry_trigger
  )
  SELECT f.ticker, f.fire_date,
         COUNT(b.*) AS n_bars,
         MIN(b.bar_time AT TIME ZONE 'America/New_York') AS first_et,
         MAX(b.bar_time AT TIME ZONE 'America/New_York') AS last_et
  FROM fires f
  LEFT JOIN mi_intraday_bars b
    ON b.ticker = f.ticker
   AND b.bar_time AT TIME ZONE 'America/New_York' >= (f.fire_date::timestamp + interval '9 hour 30 min')
   AND b.bar_time AT TIME ZONE 'America/New_York' <  (f.fire_date::timestamp + interval '16 hour')
  GROUP BY f.ticker, f.fire_date
  ORDER BY f.ticker, f.fire_date
) TO STDOUT WITH CSV HEADER\"" > intraday_day0_coverage.csv

echo "[5/5] mi_intraday_bars — RAW day-0 1-min bars, ONLY for (ticker,fire_date) pairs that HAVE coverage"
ssh "$HOST" "$PSQL -c \"\\copy (
  WITH fires AS (SELECT DISTINCT ticker, fire_date FROM mi_delayed_entry_trigger),
  covered AS (
    SELECT f.ticker, f.fire_date FROM fires f
    WHERE EXISTS (
      SELECT 1 FROM mi_intraday_bars b
      WHERE b.ticker = f.ticker
        AND b.bar_time AT TIME ZONE 'America/New_York' >= (f.fire_date::timestamp + interval '9 hour 30 min')
        AND b.bar_time AT TIME ZONE 'America/New_York' <  (f.fire_date::timestamp + interval '16 hour')
    )
  )
  SELECT b.ticker, b.bar_time, b.open, b.high, b.low, b.close, b.volume
  FROM mi_intraday_bars b
  JOIN covered c ON c.ticker = b.ticker
   AND b.bar_time AT TIME ZONE 'America/New_York' >= (c.fire_date::timestamp + interval '9 hour 30 min')
   AND b.bar_time AT TIME ZONE 'America/New_York' <  (c.fire_date::timestamp + interval '16 hour')
  ORDER BY b.ticker, b.bar_time
) TO STDOUT WITH CSV HEADER\"" > intraday_day0_raw.csv

echo "done"
wc -l trigger.csv watch.csv daily_closes.csv intraday_day0_coverage.csv intraday_day0_raw.csv
du -sh trigger.csv watch.csv daily_closes.csv intraday_day0_coverage.csv intraday_day0_raw.csv
