-- #146 unpark: raw daily bars for every ticker with a stored flag row on any scan date >= 2026-09-29 (the replay
-- universe), 2025-09-01 on (262 trading rows of history for the last replayed day). SELECT-only, captured once.
SELECT ticker, trade_date, open_price, high_price, low_price, close, volume
FROM mi_daily_closes
WHERE trade_date >= '2025-09-01'
  AND ticker IN (SELECT DISTINCT ticker FROM mi_flag_candidates WHERE scan_date >= '2026-09-29')
ORDER BY ticker, trade_date;
