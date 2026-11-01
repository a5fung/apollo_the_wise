SET default_transaction_read_only = on;
SELECT COUNT(*) AS rows, COUNT(DISTINCT trade_id) AS trades, COUNT(DISTINCT arm) AS arms, MIN(fill_day), MAX(fill_day) FROM mi_live_fill_counterfactuals;
SELECT date_trunc('week', fill_day)::date AS wk, COUNT(DISTINCT trade_id) FROM mi_live_fill_counterfactuals WHERE fill_day >= '2026-09-01' GROUP BY 1 ORDER BY 1;
