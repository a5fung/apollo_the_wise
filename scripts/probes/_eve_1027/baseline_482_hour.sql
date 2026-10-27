-- #482 hour lane: the pre-deploy baseline (its SSoT EXPECT, docs/setups/magna53_ep.md 2026-10-27). Run right BEFORE the 21:15 ET deploy.
SET default_transaction_read_only = on;
\echo '== (a) bar sizes in the window'
SELECT bar_size_minutes, COUNT(*) FROM mi_orb_shadow_trades WHERE alert_date >= CURRENT_DATE - 14 GROUP BY 1;
\echo '== (b) snapshot of every 5-minute row of the window'
SELECT id, ticker, alert_date, status, skip_reason, entry_price, hard_stop, entry_shares, orb_high, orb_low, trigger_minute_et, total_pnl,
       CASE WHEN jsonb_typeof(running_closes) = 'array' THEN jsonb_array_length(running_closes) ELSE -1 END AS n_closes
FROM mi_orb_shadow_trades WHERE bar_size_minutes = 5 AND alert_date >= CURRENT_DATE - 14 ORDER BY id;
