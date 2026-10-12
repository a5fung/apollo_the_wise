\echo === mi_audit_log cols
SELECT column_name FROM information_schema.columns WHERE table_name='mi_audit_log' ORDER BY ordinal_position;
\echo === mi_ep_alerts cols (strategy-ish)
SELECT column_name FROM information_schema.columns WHERE table_name='mi_ep_alerts' AND (column_name ILIKE '%strat%' OR column_name ILIKE '%signal%' OR column_name ILIKE '%account%' OR column_name ILIKE '%mcap%' OR column_name ILIKE '%market_cap%' OR column_name ILIKE '%lane%') ORDER BY 1;
\echo === mi_live_trades cols (account-ish)
SELECT column_name FROM information_schema.columns WHERE table_name='mi_live_trades' AND (column_name ILIKE '%strat%' OR column_name ILIKE '%signal%' OR column_name ILIKE '%account%' OR column_name ILIKE '%order%' OR column_name ILIKE '%alert%') ORDER BY 1;
\echo === lane table cols
SELECT column_name FROM information_schema.columns WHERE table_name='mi_lowcap_paper_lane_alerts' ORDER BY ordinal_position;
