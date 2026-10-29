SET default_transaction_read_only = on;
\echo == open rows
SELECT id, ticker, account_mode, signal_type, status, alert_date, entry_price, remaining_shares, hard_stop, stop_price,
       breakeven_active, partial_taken, coalesce(exit_rule,'') AS exit_rule, coalesce(running_closes::text,'[]') AS running_closes
FROM mi_live_trades WHERE status IN ('filled','partial') AND remaining_shares > 0 ORDER BY account_mode, alert_date, id;
\echo == closes
SELECT c.ticker, c.trade_date, c.close FROM mi_daily_closes c
WHERE c.ticker IN (SELECT ticker FROM mi_live_trades WHERE status IN ('filled','partial') AND remaining_shares > 0)
  AND c.trade_date >= DATE '2026-06-01' ORDER BY c.ticker, c.trade_date;
