\pset format unaligned
\pset fieldsep '|'
\pset footer off
-- one-shot shape census for step 3
SELECT count(*) AS rows, count(DISTINCT cluster_date) AS dates, min(cluster_date), max(cluster_date), count(DISTINCT (cluster_date, cluster_hash)) AS clusters FROM mi_correlation_clusters;
SELECT date_trunc('month', cluster_date)::date AS m, count(DISTINCT cluster_date) AS dates, count(DISTINCT (cluster_date, cluster_hash)) AS clusters, round(avg(member_count)::numeric,1) AS avg_members FROM mi_correlation_clusters GROUP BY 1 ORDER BY 1;
SELECT member_count, count(DISTINCT (cluster_date, cluster_hash)) FROM mi_correlation_clusters GROUP BY 1 ORDER BY 1;
SELECT count(*) AS alert_rows, min(alert_date), max(alert_date), count(DISTINCT ticker) FROM mi_ep_alerts;
SELECT count(*) AS shadow_rows, min(alert_date), max(alert_date) FROM mi_theme_axis_shadow;
SELECT count(DISTINCT score_date) AS score_dates, min(score_date), max(score_date) FROM mi_stock_scores WHERE score_date >= '2026-01-15';
