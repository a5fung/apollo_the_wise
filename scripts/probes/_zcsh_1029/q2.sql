SET default_transaction_read_only = on;
SELECT count(*) AS watch_rows_ever FROM mi_consolidation_breakout_watch WHERE ticker='ZCSH';
SELECT count(*) AS coil_rows_ever, max(scan_date) FROM mi_anticipation_consolidation WHERE ticker='ZCSH';
SELECT security_type, count(*) FROM mi_security_types WHERE security_type IN ('ETV','ETF','ETN','ETS') GROUP BY 1;
