\pset format unaligned
\pset fieldsep '|'
\pset footer off
-- ticker_overrides coverage
SELECT count(*) AS n, count(industry) FILTER (WHERE industry<>'') AS with_industry, count(sector) FILTER (WHERE sector<>'') AS with_sector, count(DISTINCT industry) AS n_industries, count(DISTINCT sector) AS n_sectors FROM mi_ticker_overrides;
-- shadow table shape
SELECT source, grade, themeless_flag, count(*) FROM mi_theme_axis_shadow GROUP BY 1,2,3 ORDER BY 1,2,3;
SELECT min(alert_date), max(alert_date), count(*), count(DISTINCT ticker) FROM mi_theme_axis_shadow;
SELECT count(*) FILTER (WHERE theme_name_7d IS NOT NULL) AS themed_7d, count(*) FILTER (WHERE bounded_matches_unbounded IS NOT NULL) AS captured_7d, count(*) FILTER (WHERE theme_stage_7d IN ('Accelerating','Mainstream')) AS active_7d FROM mi_theme_axis_shadow;
-- mi_ep_alerts
SELECT score_tier, in_active_theme, count(*) FROM mi_ep_alerts GROUP BY 1,2 ORDER BY 1,2;
SELECT date_trunc('month', alert_date)::date AS m, count(*) FROM mi_ep_alerts GROUP BY 1 ORDER BY 1;
-- alert tickers' industry coverage (shadow live_scan + ep_alerts)
SELECT count(DISTINCT s.ticker) AS alert_tickers, count(DISTINCT s.ticker) FILTER (WHERE o.industry<>'' ) AS with_industry, count(DISTINCT s.ticker) FILTER (WHERE o.sector<>'') AS with_sector FROM mi_theme_axis_shadow s LEFT JOIN mi_ticker_overrides o ON o.ticker=s.ticker;
SELECT count(DISTINCT a.ticker) AS alert_tickers, count(DISTINCT a.ticker) FILTER (WHERE o.industry<>'') AS with_industry, count(DISTINCT a.ticker) FILTER (WHERE o.sector<>'') AS with_sector FROM mi_ep_alerts a LEFT JOIN mi_ticker_overrides o ON o.ticker=a.ticker;
-- scan-log control candidates' coverage (all distinct tickers in scan log)
SELECT count(DISTINCT l.ticker) AS scan_tickers, count(DISTINCT l.ticker) FILTER (WHERE o.industry<>'') AS with_industry, count(DISTINCT l.ticker) FILTER (WHERE o.sector<>'') AS with_sector FROM mi_ep_scan_log l LEFT JOIN mi_ticker_overrides o ON o.ticker=l.ticker;
-- industry sizes among names that have closes (how big are peer sets)
SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY n) AS med, percentile_cont(0.9) WITHIN GROUP (ORDER BY n) AS p90, max(n) FROM (SELECT industry, count(*) AS n FROM mi_ticker_overrides WHERE industry<>'' GROUP BY 1) x;
-- how many closes rows for override tickers since 2026-03-01
SELECT count(*), count(DISTINCT ticker) FROM mi_daily_closes WHERE trade_date >= '2026-03-01' AND ticker IN (SELECT ticker FROM mi_ticker_overrides WHERE industry<>'' OR sector<>'');
-- scan log columns
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_ep_scan_log' ORDER BY ordinal_position;
SELECT column_name FROM information_schema.columns WHERE table_name='mi_theme_axis_shadow' ORDER BY ordinal_position;
SELECT column_name FROM information_schema.columns WHERE table_name='mi_theme_relevance_cohort' ORDER BY ordinal_position;
