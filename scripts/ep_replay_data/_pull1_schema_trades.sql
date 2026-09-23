\echo === SCHEMA mi_live_trades ===
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_live_trades' ORDER BY ordinal_position;
\echo === SCHEMA mi_ep_alerts ===
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_ep_alerts' ORDER BY ordinal_position;
\echo === SCHEMA mi_intraday_bars ===
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_intraday_bars' ORDER BY ordinal_position;
\echo === SCHEMA mi_daily_closes ===
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_daily_closes' ORDER BY ordinal_position;
\echo === SCHEMA mi_market_regime ===
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_market_regime' ORDER BY ordinal_position;
\echo === COUNTS ===
SELECT 'live_trades_closed_magna53' k, count(*) FROM mi_live_trades WHERE signal_type='magna53' AND status='closed'
UNION ALL SELECT 'ep_alerts_live', count(*) FROM mi_ep_alerts WHERE COALESCE(source,'live')='live'
UNION ALL SELECT 'intraday_bars', count(*) FROM mi_intraday_bars
UNION ALL SELECT 'daily_closes', count(*) FROM mi_daily_closes;
