SELECT strategy_id, signal_type, phase, enabled, live_real_enabled, position_size_multiplier, max_concurrent_positions FROM mi_strategies ORDER BY phase, strategy_id;
\echo === paper-account trades last 60d by signal_type
SELECT signal_type, status, count(*) FROM mi_live_trades WHERE account_mode='paper' AND alert_date >= '2026-08-10' GROUP BY 1,2 ORDER BY 1,2;
\echo === live magna53 trades last 30 scan days
SELECT count(*) FROM mi_live_trades WHERE account_mode='live' AND signal_type='magna53' AND alert_date >= '2026-08-28';
\echo === HIGH alerts per day (live) 30 days
SELECT count(*) FILTER (WHERE score_tier='HIGH') high, count(*) all_alerts FROM mi_ep_alerts WHERE alert_date >= '2026-08-28' AND alert_date < '2026-10-10' AND coalesce(source,'live')='live';
\echo === safeguard state paper
SELECT safeguard, account_mode, left(state::text,120) FROM mi_safeguard_state WHERE account_mode='paper' ORDER BY 1 LIMIT 30;
