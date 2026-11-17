SET default_transaction_read_only = on;
SELECT signal_type, account_mode, skip_reason, COUNT(*) FROM mi_live_trades WHERE alert_date=CURRENT_DATE AND status='skipped' AND skip_reason LIKE 'setup:%' GROUP BY 1,2,3 ORDER BY 4 DESC;
SELECT alert_date, signal_type, COUNT(*) FROM mi_live_trades WHERE alert_date>=CURRENT_DATE-14 AND status='skipped' AND skip_reason LIKE 'setup:%' GROUP BY 1,2 ORDER BY 1;
