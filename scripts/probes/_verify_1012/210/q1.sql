\echo === Q1 mi_job_runs tv_news_shadow last 14
SELECT id, started_at AT TIME ZONE 'America/New_York' AS started_et, scheduled_for AT TIME ZONE 'America/New_York' AS sched_et, status, rows_written, left(coalesce(error_message,''),160) AS err
FROM mi_job_runs WHERE job_id='tv_news_shadow' ORDER BY started_at DESC LIMIT 14;

\echo === Q2 mi_ep_grade_corpus by alert_date (last 10 days)
SELECT alert_date, count(*) AS n, min(captured_at AT TIME ZONE 'America/New_York') AS first_et, max(captured_at AT TIME ZONE 'America/New_York') AS last_et
FROM mi_ep_grade_corpus GROUP BY 1 ORDER BY 1 DESC LIMIT 10;

\echo === Q3 provenance audit rows by day (last 8 days, distinct ticker/alert_date)
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS et_day, count(*) AS rows, count(DISTINCT (detail::json->>'ticker')||'|'||(detail::json->>'alert_date')) AS distinct_ticker_days
FROM mi_audit_log
WHERE event_type='ep_catalyst_provenance' AND created_at >= NOW() - interval '8 days'
  AND detail LIKE '{%'
GROUP BY 1 ORDER BY 1 DESC;

\echo === Q4 today's provenance ticker-days vs grade corpus
WITH p AS (
  SELECT DISTINCT (detail::json->>'ticker') AS ticker, (detail::json->>'alert_date')::date AS alert_date
  FROM mi_audit_log
  WHERE event_type='ep_catalyst_provenance' AND created_at >= (now() AT TIME ZONE 'America/New_York')::date AT TIME ZONE 'America/New_York'
    AND detail LIKE '{%'
)
SELECT p.ticker, p.alert_date, (g.ticker IS NOT NULL) AS has_corpus, g.captured_at AT TIME ZONE 'America/New_York' AS cap_et, g.raw_grade,
       jsonb_array_length(coalesce(g.alpaca_json,'[]'::jsonb)) AS alp_n, jsonb_array_length(coalesce(g.fmp_json,'[]'::jsonb)) AS fmp_n, length(coalesce(g.perplexity_text,'')) AS pplx_len, g.sec_title IS NOT NULL AS has_sec
FROM p LEFT JOIN mi_ep_grade_corpus g ON g.ticker=p.ticker AND g.alert_date=p.alert_date ORDER BY p.ticker;

\echo === Q5 mi_tv_news_shadow all rows summary
SELECT ticker, alert_date, checked_at AT TIME ZONE 'America/New_York' AS chk_et, tv_status, our_corpus_available, our_corpus_source, tv_coverage_reaches_alert_date AS reach_alert, tv_coverage_reaches_period_start AS reach_start, tv_items_on_alert_date AS on_day, tv_items_before_grade AS bef, tv_items_in_repoll_window AS repoll, tv_items_after_cutoff AS aft, (tv_items_we_missed IS NULL) AS missed_null, CASE WHEN tv_items_we_missed IS NULL THEN NULL ELSE jsonb_array_length(tv_items_we_missed) END AS missed_n, our_captured_at IS NOT NULL AS has_cap
FROM mi_tv_news_shadow ORDER BY alert_date DESC, ticker;

\echo === Q6 mi_ep_alerts today and last 3 days
SELECT alert_date, count(*) AS n, count(DISTINCT ticker) AS dt FROM mi_ep_alerts WHERE alert_date >= (now() AT TIME ZONE 'America/New_York')::date - 4 GROUP BY 1 ORDER BY 1 DESC;
