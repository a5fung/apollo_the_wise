\pset pager off
\echo === zero-alert trading days, 30 scan days before 10-10 (trading days = scan_date in mi_ep_scan_log)
WITH d AS (SELECT DISTINCT scan_date FROM mi_ep_scan_log WHERE scan_date < '2026-10-10' ORDER BY scan_date DESC LIMIT 30),
a AS (SELECT alert_date, count(*) n, count(*) FILTER (WHERE score_tier='HIGH') hi FROM mi_ep_alerts WHERE alert_date >= (SELECT min(scan_date) FROM d) GROUP BY 1)
SELECT count(*) days, count(*) FILTER (WHERE a.n IS NULL) zero_alert_days, count(*) FILTER (WHERE COALESCE(a.hi,0)=0) zero_high_days, min(d.scan_date) from_d, max(d.scan_date) to_d,
       string_agg(CASE WHEN a.n IS NULL THEN to_char(d.scan_date,'MM-DD') END, ',' ORDER BY d.scan_date) zero_dates
FROM d LEFT JOIN a ON a.alert_date=d.scan_date;
