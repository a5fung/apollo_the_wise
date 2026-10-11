-- #146 unpark: POSITIVE CONTROL population - bars for every ticker with a RAW stored TRIGGERED row since 2026-08-14
-- (CHYM, WDAY, XHLD, IOVA, ...), so the replay can show the SHIPPED rule reproduces the real TRIGGERED reads
-- (the 09-29 .. 10-09 scope stored none). SELECT-only, captured once.
SELECT ticker, trade_date, open_price, high_price, low_price, close, volume
FROM mi_daily_closes
WHERE trade_date >= '2025-09-01'
  AND ticker IN (SELECT DISTINCT ticker FROM mi_flag_candidates
                 WHERE scan_date >= '2026-08-14' AND stage = 'TRIGGERED' AND held_from_stage IS NULL)
ORDER BY ticker, trade_date;
