\pset format unaligned
\pset fieldsep '|'
\echo === mi_themes ===
SELECT count(*) n, count(distinct name) names, min(theme_date), max(theme_date) FROM mi_themes;
SELECT stage, count(*) FROM mi_themes GROUP BY 1 ORDER BY 2 DESC;
SELECT source, count(*) FROM mi_themes GROUP BY 1;
SELECT count(*) FILTER (WHERE stage='Retired' AND parent_theme IS NOT NULL) retired_with_parent, count(*) FILTER (WHERE stage='Retired') retired, count(*) FILTER (WHERE stage<>'Retired' AND parent_theme IS NOT NULL) live_with_parent FROM mi_themes;
SELECT count(*) names_reached_mainstream FROM (SELECT name FROM mi_themes GROUP BY name HAVING bool_or(stage='Mainstream')) x;
SELECT count(*) names_with_retired_row FROM (SELECT name FROM mi_themes GROUP BY name HAVING bool_or(stage='Retired')) x;
SELECT date_trunc('month', theme_date)::date m, count(*) rows, count(distinct name) names FROM mi_themes GROUP BY 1 ORDER BY 1;
SELECT count(*) FILTER (WHERE rs_avg IS NULL) rs_avg_null, count(*) FILTER (WHERE tickers IS NULL OR cardinality(tickers)=0) empty_tickers, count(*) total FROM mi_themes;
\echo === mi_theme_renames ===
SELECT * FROM mi_theme_renames;
\echo === mi_ep_scan_log ===
SELECT count(*), min(scan_date), max(scan_date), count(*) FILTER (WHERE gap_pct IS NULL) gap_null FROM mi_ep_scan_log;
SELECT date_trunc('month', scan_date)::date m, count(*) rows, count(*) FILTER (WHERE gap_pct >= 9) ge9, count(*) FILTER (WHERE gap_pct >= 10) ge10, round(min(gap_pct)::numeric,2) min_gap FROM mi_ep_scan_log GROUP BY 1 ORDER BY 1;
\echo === mi_ep_alerts ===
SELECT count(*), min(alert_date), max(alert_date) FROM mi_ep_alerts;
\echo === mi_daily_closes ===
SELECT count(*), min(trade_date), max(trade_date), count(distinct ticker) FROM mi_daily_closes;
SELECT count(*) spy_rows, min(trade_date), max(trade_date) FROM mi_daily_closes WHERE ticker='SPY';
\echo === mi_stock_scores ===
SELECT count(*), min(score_date), max(score_date), count(distinct score_date) FROM mi_stock_scores;
\echo === mi_theme_relevance_cohort ===
SELECT stratum, operator_label, count(*) FROM mi_theme_relevance_cohort GROUP BY 1,2 ORDER BY 1,2;
\echo === mi_correlation_clusters ===
SELECT count(*), count(distinct cluster_date), min(cluster_date), max(cluster_date) FROM mi_correlation_clusters;
\echo === mi_audit_log theme events ===
SELECT event_type, count(*), min(created_at)::date, max(created_at)::date FROM mi_audit_log WHERE event_type LIKE 'theme_%' GROUP BY 1 ORDER BY 2 DESC;
\echo === mi_security_types ===
SELECT security_type, count(*) FROM mi_security_types GROUP BY 1 ORDER BY 2 DESC LIMIT 10;
