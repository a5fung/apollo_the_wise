-- #584 10-15 VERIFIER: raw bars + shadow reads for the 09-16 gap-day-only hits (DLXY, MEDS, RETO) + BENF (guard drop) + RETO/DLXY split context. Read-only.
BEGIN READ ONLY;
\echo === Z5a: shadow rows
SELECT scan_date, ticker, prev_close, prev_day_volume, gap_pct_first, minutes_since_open_first, gap_pct_at_open, minutes_since_open_at_open, today_price_first, today_price_at_open, today_volume_at_open, today_dollar_volume_at_open, today_price_last, minutes_since_open_last, today_dollar_volume_last
FROM mi_universe_floor_shadow WHERE ticker IN ('DLXY','MEDS','RETO','BENF') AND scan_date BETWEEN DATE '2026-09-14' AND DATE '2026-10-14' ORDER BY ticker, scan_date;
\echo === Z5b: daily bars D-2..D20
SELECT ticker, trade_date, open_price, high_price, low_price, close, volume FROM mi_daily_closes
WHERE ticker IN ('DLXY','MEDS','RETO','BENF') AND trade_date BETWEEN DATE '2026-09-11' AND DATE '2026-10-14' ORDER BY ticker, trade_date;
\echo === Z5c: splits for these tickers (any date)
SELECT * FROM mi_splits WHERE ticker IN ('DLXY','MEDS','RETO','BENF') ORDER BY ticker, execution_date;
ROLLBACK;
