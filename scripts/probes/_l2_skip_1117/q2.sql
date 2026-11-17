SET default_transaction_read_only = on;
SELECT split_part(skip_reason, ':', 1) cat, COUNT(*) FILTER (WHERE NOT (signal_type = 'breakout_v1' AND skip_reason LIKE 'setup:stop_too_wide%')) new_n, COUNT(*) old_n FROM mi_live_trades WHERE alert_date=CURRENT_DATE AND status='skipped' GROUP BY 1;
