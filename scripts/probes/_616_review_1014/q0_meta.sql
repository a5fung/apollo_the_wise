\pset pager off
\echo == calendar: SPY sessions (maturity clock)
SELECT MAX(trade_date) AS last_spy_bar, COUNT(*) AS spy_sessions_since_0820
FROM mi_daily_closes WHERE ticker='SPY' AND trade_date >= DATE '2026-08-20';
\echo == last trade_date any ticker, and tickers on last date
SELECT MAX(trade_date) AS last_any, (SELECT COUNT(*) FROM mi_daily_closes WHERE trade_date=(SELECT MAX(trade_date) FROM mi_daily_closes)) AS n_tickers_last
FROM mi_daily_closes;
\echo == SPY sessions since 09-01
SELECT string_agg(to_char(trade_date,'MM-DD'), ' ' ORDER BY trade_date) FROM mi_daily_closes WHERE ticker='SPY' AND trade_date>=DATE '2026-09-01';
\echo == table existence + columns
SELECT column_name FROM information_schema.columns WHERE table_name='mi_delayed_entry_trigger' AND column_name IN
 ('rung','reentry_shape','fire_date','ep_date','ticker','realized_r_trail','realized_r_trail_075','realized_r_trail_100','outcome_trail','outcome_trail_075','outcome_trail_100','stop_width_pct','stop_width_pct_075','stop_width_pct_100','settle_version','settle_version_075','settle_version_100','pattern_version','screen_version','ep_adr20_n','reached_4r_075','reached_4r_100','reached_4r') ORDER BY 1;
\echo == versions in play (all post-09-02 rows)
SELECT rung, reentry_shape, pattern_version, settle_version, COUNT(*) FROM mi_delayed_entry_trigger WHERE fire_date>=DATE '2026-09-02' GROUP BY 1,2,3,4 ORDER BY 1,2,3,4;
\echo == predicate value as the YAML reads it
SELECT COUNT(*) FROM mi_delayed_entry_trigger WHERE rung='ep_low_reclaim' AND fire_date>=DATE '2026-09-02' AND realized_r_trail_075 IS NOT NULL;
