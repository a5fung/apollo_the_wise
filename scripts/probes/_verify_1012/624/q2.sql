\echo === strategy row
SELECT * FROM mi_strategies WHERE strategy_id IN ('magna53_smallcap','magna53_ep') ORDER BY 1;
\echo === live scan log today (screened / cap-only)
SELECT filter_reason, count(*) FROM mi_ep_scan_log WHERE scan_date = (now() AT TIME ZONE 'America/New_York')::date GROUP BY 1 ORDER BY 2 DESC;
