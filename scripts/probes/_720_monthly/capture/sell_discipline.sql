SET default_transaction_read_only = on;
-- #720: peak / capture / giveback / hold per closed trade, every account mode.
\copy (SELECT s.* FROM mi_sell_discipline_records s JOIN mi_live_trades t ON t.id = s.trade_id WHERE t.filled_at IS NOT NULL AND (t.filled_at AT TIME ZONE 'America/New_York')::date >= DATE '2026-08-16' ORDER BY s.trade_id) TO STDOUT WITH CSV HEADER
