SET default_transaction_read_only = on;
SELECT column_name FROM information_schema.columns WHERE table_name='mi_ep_scan_log' ORDER BY ordinal_position;
SELECT * FROM mi_ep_scan_log WHERE ticker='APP' AND scan_date BETWEEN '2026-11-04' AND '2026-11-07' ORDER BY id DESC LIMIT 3;
