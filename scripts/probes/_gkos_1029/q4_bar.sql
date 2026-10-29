SET default_transaction_read_only = on;
SELECT (bar_time AT TIME ZONE 'America/New_York')::time(0) AS et, open, high, low, close, volume FROM mi_intraday_bars
WHERE ticker = 'GKOS' AND bar_time >= '2026-10-29 09:30-04' AND bar_time < '2026-10-29 09:36-04' ORDER BY bar_time;
SELECT atr_14, orb_high, orb_low, status, skip_reason FROM mi_live_trades WHERE ticker='GKOS' AND alert_date='2026-10-29';
