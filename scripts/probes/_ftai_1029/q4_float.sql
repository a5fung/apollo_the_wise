SET default_transaction_read_only = on;
-- how often the float points are actually awarded (scored scan rows, last 30 days)
SELECT count(*) AS scored_rows, count(*) FILTER (WHERE (score_breakdown->>'float')::numeric > 0) AS float_points_awarded,
       count(DISTINCT ticker) FILTER (WHERE (score_breakdown->>'float')::numeric > 0) AS names_awarded
FROM mi_ep_scan_log WHERE scan_date >= CURRENT_DATE - 30 AND score_breakdown IS NOT NULL;
SELECT max(scan_date) AS last_awarded FROM mi_ep_scan_log WHERE (score_breakdown->>'float')::numeric > 0;
