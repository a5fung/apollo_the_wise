SET default_transaction_read_only = on;
\echo == AXG split rows (all)
SELECT ticker, execution_date, split_from, split_to, adjustment_applied, adjustment_outcome, applied_factor, applied_at AT TIME ZONE 'America/New_York' AS applied_et FROM mi_splits WHERE ticker IN ('AXG','ENHA','JZ') ORDER BY ticker, execution_date;
\echo == AXG stored closes around the two dates
SELECT trade_date, close FROM mi_daily_closes WHERE ticker='AXG' AND trade_date BETWEEN '2026-10-20' AND '2026-10-30' ORDER BY trade_date;
\echo == the 4th phantom row
SELECT ticker, execution_date, applied_at AT TIME ZONE 'America/New_York' FROM mi_splits WHERE adjustment_outcome='phantom' ORDER BY applied_at;
