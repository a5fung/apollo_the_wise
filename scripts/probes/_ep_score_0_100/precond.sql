SET default_transaction_read_only = on;
\echo === Q1 side/bar per day since 08-22
SELECT scan_date, score_side, ep_bar, count(*) FROM mi_ep_scan_log WHERE scan_date >= '2026-08-22' GROUP BY 1,2,3 ORDER BY 1,2,3;
\echo === Q2 max alert score
SELECT max(ep_score) FROM mi_ep_alerts WHERE alert_date >= '2026-08-22';
\echo === Q3 min alert score
SELECT min(ep_score) FROM mi_ep_alerts WHERE alert_date >= '2026-08-22';
