-- READ-ONLY. Why the 10-name long-carry set rotated 10-12 -> 10-13: last stored TIGHTENING-or-better label per rotating name,
-- and its session lag from each night (aging, not flapping, is the expected mechanism).
SET default_transaction_read_only = on;
SET statement_timeout = '30s';
WITH sess AS (SELECT DISTINCT scan_date FROM mi_flag_candidates WHERE scan_date >= DATE '2026-08-01'
              AND EXISTS (SELECT 1 FROM mi_daily_closes d WHERE d.trade_date = mi_flag_candidates.scan_date)),
last_lab AS (
  SELECT ticker, max(scan_date) AS last_tight_plus FROM mi_flag_candidates
  WHERE ticker IN ('FIVN','RUM','PURR','TEAM') AND stage IN ('TIGHTENING','COILED','TRIGGERED') GROUP BY 1)
SELECT l.ticker, l.last_tight_plus,
       (SELECT count(*) FROM sess WHERE sess.scan_date > l.last_tight_plus AND sess.scan_date < DATE '2026-10-12') + 1 AS lag_on_1012,
       (SELECT count(*) FROM sess WHERE sess.scan_date > l.last_tight_plus AND sess.scan_date < DATE '2026-10-13') + 1 AS lag_on_1013
FROM last_lab l ORDER BY 1;
