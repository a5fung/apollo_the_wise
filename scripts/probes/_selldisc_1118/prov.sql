SET default_transaction_read_only = on;
SELECT ticker, signal_type, account_mode, (closed_at AT TIME ZONE 'America/New_York')::date d FROM mi_live_trades WHERE status='closed' AND closed_at > now() - interval '2 days' ORDER BY closed_at;
SELECT close_day, ticker, signal_type, account_mode FROM mi_sell_discipline_records WHERE close_day >= current_date - 8 ORDER BY close_day DESC;
