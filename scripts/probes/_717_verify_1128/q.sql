SET default_transaction_read_only = on;
SELECT scan_date, count(*), count(*) FILTER (WHERE gates->>'setup_version' IS NOT NULL) stamped, min(gates->>'setup_version') v FROM mi_breakout_v1_list WHERE scan_date >= '2026-11-23' GROUP BY 1 ORDER BY 1;
SELECT id, ticker, account_mode, created_at AT TIME ZONE 'America/New_York' et, setup_version FROM mi_live_trades WHERE created_at >= '2026-11-23' ORDER BY id;
