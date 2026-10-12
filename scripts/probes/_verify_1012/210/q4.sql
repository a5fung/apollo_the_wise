\echo === S1 tv_news_shadow job_runs since 10-09
SELECT id, started_at AT TIME ZONE 'America/New_York' AS started_et, finished_at AT TIME ZONE 'America/New_York' AS fin_et, duration_s, status, rows_written, left(coalesce(error_message,''),200) AS err FROM mi_job_runs WHERE job_id='tv_news_shadow' AND started_at >= '2026-10-09' ORDER BY started_at;

\echo === S2 tv_news_shadow_run audit events since 10-09
SELECT event_type, created_at AT TIME ZONE 'America/New_York' AS at_et, left(detail,400) AS detail FROM mi_audit_log WHERE event_type IN ('tv_news_shadow_run','tv_news_shadow_error','tv_news_endpoint_error','tv_news_shadow_endpoint_error') AND created_at >= '2026-10-09' ORDER BY created_at;

\echo === S3 all shadow rows with new-frame columns
SELECT ticker, alert_date, checked_at AT TIME ZONE 'America/New_York' AS chk_et, tv_status, catalyst_quality AS raw, our_acting_grade AS acting, our_acting_rule, our_corpus_available AS corp, our_corpus_source AS src, our_captured_at AT TIME ZONE 'America/New_York' AS cap_et, tv_coverage_reaches_alert_date AS r_alert, tv_coverage_reaches_period_start AS r_start, tv_items_on_alert_date AS on_day, tv_items_before_grade AS bef, tv_items_in_repoll_window AS repoll, tv_items_after_cutoff AS aft, (tv_items_we_missed IS NULL) AS missed_null, tv_match_summary::text AS msum, our_polygon_count AS poly
FROM mi_tv_news_shadow WHERE alert_date >= '2026-10-07' ORDER BY checked_at DESC, ticker;

\echo === S4 ep_scan durations (07:00-10:00 ET ticks) per day last 6 days
SELECT (started_at AT TIME ZONE 'America/New_York')::date AS d, count(*) AS ticks, round(avg(duration_s)::numeric,2) AS avg_s, round(max(duration_s)::numeric,2) AS max_s
FROM mi_job_runs WHERE job_id='ep_scan' AND started_at >= '2026-10-02'
  AND (started_at AT TIME ZONE 'America/New_York')::time BETWEEN '07:00' AND '10:00'
GROUP BY 1 ORDER BY 1 DESC;

\echo === S5 grade-corpus coverage at query time
SELECT count(*) FROM mi_ep_grade_corpus WHERE alert_date='2026-10-12';
\echo === S6 alerts on 10-12
SELECT ticker, catalyst_quality FROM mi_ep_alerts WHERE alert_date='2026-10-12';
