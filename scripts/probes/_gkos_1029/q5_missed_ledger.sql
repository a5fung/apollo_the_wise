SET default_transaction_read_only = on;
-- how the existing missed-trade accounting holds the live infra:no_bar misses
SELECT alert_date, ticker, source, skip_category, left(coalesce(skip_reason,''),50) AS skip_reason, ret_5d, ret_20d, max_high_20d
FROM mi_ep_missed_outcomes WHERE (alert_date, ticker) IN (('2026-08-13','CGEM'),('2026-08-13','CRMD'),('2026-08-13','HLIT'),('2026-08-20','RARE'),('2026-10-29','GKOS'))
ORDER BY alert_date, ticker;
