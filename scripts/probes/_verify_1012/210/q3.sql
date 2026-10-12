\echo === R1 alerts 10-05..10-12 with shadow presence and corpus presence
SELECT a.alert_date, a.ticker, a.catalyst_quality AS acting, (s.ticker IS NOT NULL) AS in_shadow, (g.ticker IS NOT NULL) AS in_grade_corpus, (m.ticker IS NOT NULL) AS in_metrics
FROM mi_ep_alerts a
LEFT JOIN mi_tv_news_shadow s ON s.ticker=a.ticker AND s.alert_date=a.alert_date
LEFT JOIN mi_ep_grade_corpus g ON g.ticker=a.ticker AND g.alert_date=a.alert_date
LEFT JOIN mi_ep_catalyst_metrics m ON m.ticker=a.ticker AND m.alert_date=a.alert_date
WHERE a.alert_date >= '2026-10-05' ORDER BY a.alert_date DESC, a.ticker;

\echo === R2 todays provenance detail (has_direct_source, sources) vs corpus sec_title
SELECT detail::json->>'ticker' AS ticker, detail::json->>'catalyst_quality' AS cq, detail::json->>'has_direct_source' AS hds, detail::json->>'sources' AS sources, created_at AT TIME ZONE 'America/New_York' AS prov_et
FROM mi_audit_log WHERE event_type='ep_catalyst_provenance' AND created_at >= '2026-10-12 00:00-04' AND detail LIKE '{%' ORDER BY created_at;

\echo === R3 grade corpus today full-ish
SELECT ticker, captured_at AT TIME ZONE 'America/New_York' AS cap_et, company_name, raw_grade, sec_title, left(perplexity_text,60) AS pplx60 FROM mi_ep_grade_corpus WHERE alert_date='2026-10-12' ORDER BY captured_at;

\echo === R4 job_runs for ALL tv_news_shadow since 10-09, and any job rows from 10:00-10:30 today
SELECT job_id, started_at AT TIME ZONE 'America/New_York' AS started_et, status FROM mi_job_runs WHERE started_at >= '2026-10-12 09:55-04' ORDER BY started_at;
