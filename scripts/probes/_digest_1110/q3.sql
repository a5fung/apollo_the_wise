SET default_transaction_read_only = on;
SELECT scan_date, count(*) FILTER (WHERE stage IN ('TIGHTENING','COILED','TRIGGERED') AND base_low > 0) pool, count(*) total
FROM mi_flag_candidates WHERE scan_date >= '2026-08-20' GROUP BY 1 ORDER BY 1 DESC LIMIT 60;
