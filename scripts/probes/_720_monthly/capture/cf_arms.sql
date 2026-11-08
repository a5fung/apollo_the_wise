SET default_transaction_read_only = on;
-- #720: every recorder row (all arms incl. fill_facts) for the fills in trades.sql. L1 only by construction (signal_type = 'magna53').
\copy (SELECT c.* FROM mi_live_fill_counterfactuals c JOIN mi_live_trades t ON t.id = c.trade_id WHERE t.filled_at IS NOT NULL AND (t.filled_at AT TIME ZONE 'America/New_York')::date >= DATE '2026-08-16' ORDER BY c.trade_id, c.arm) TO STDOUT WITH CSV HEADER
