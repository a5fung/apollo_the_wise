-- #210 read 2026-10-10 — SELECT only. Captured ONCE to q1_read.out; never re-run to re-read.
\echo '### Q1 all shadow rows, full'
SELECT ticker, alert_date, checked_at AT TIME ZONE 'America/New_York' AS checked_et, catalyst_quality, our_has_direct_source AS our_direct, our_source_class_count AS our_src_n, our_corpus_available AS corpus, our_polygon_count AS poly, our_alpaca_count AS alp, our_fmp_count AS fmp, our_perplexity_present AS pplx, tv_status, tv_skip_reason, exchange_mic, tv_symbol, tv_item_count AS tv_n, tv_providers, tv_oldest_item_published AT TIME ZONE 'America/New_York' AS oldest_et, tv_coverage_reaches_alert_date AS reaches, tv_items_on_alert_date AS tv_sameday, tv_providers_on_alert_date, jsonb_array_length(tv_items_we_missed) AS missed_n FROM mi_tv_news_shadow ORDER BY alert_date;

\echo '### Q2 why unreadable: shadow rows joined to metrics rows'
SELECT s.ticker, s.alert_date, s.our_corpus_available AS corpus, (m.ticker IS NOT NULL) AS metrics_row, m.extraction_quality, m.extracted_at AT TIME ZONE 'America/New_York' AS extracted_et, (m.raw_polygon_news_json IS NULL) AS poly_null, (m.raw_alpaca_news_json IS NULL) AS alp_null, (m.raw_fmp_news_json IS NULL) AS fmp_null, (m.raw_perplexity_text IS NULL) AS pplx_null FROM mi_tv_news_shadow s LEFT JOIN mi_ep_catalyst_metrics m ON m.ticker=s.ticker AND m.alert_date=s.alert_date ORDER BY s.alert_date;

\echo '### Q3 our corpus raw for ACN 10-01 and PENG 10-07'
SELECT ticker, alert_date, extracted_at AT TIME ZONE 'America/New_York' AS extracted_et, extraction_quality, raw_polygon_news_json::text AS polygon, raw_alpaca_news_json::text AS alpaca, raw_fmp_news_json::text AS fmp, raw_perplexity_text AS pplx FROM mi_ep_catalyst_metrics WHERE (ticker, alert_date) IN (('ACN','2026-10-01'),('PENG','2026-10-07'));

\echo '### Q4 tv_items_we_missed raw for the same two'
SELECT ticker, alert_date, tv_items_we_missed::text AS missed FROM mi_tv_news_shadow WHERE (ticker, alert_date) IN (('ACN','2026-10-01'),('PENG','2026-10-07'));

\echo '### Q5 job runs'
SELECT started_at AT TIME ZONE 'America/New_York' AS started_et, status, rows_written FROM mi_job_runs WHERE job_id ILIKE '%tv_news%' ORDER BY started_at;

\echo '### Q6 run summaries + endpoint errors'
SELECT created_at AT TIME ZONE 'America/New_York' AS at_et, event_type, summary FROM mi_audit_log WHERE event_type IN ('tv_news_shadow_run','tv_news_endpoint_error','tv_news_shadow_error') ORDER BY created_at;

\echo '### Q7 mi_ep_alerts columns'
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_ep_alerts' ORDER BY ordinal_position;

\echo '### Q8 alerts per week since 09-01: ticker-days, with metrics row, with news corpus'
SELECT date_trunc('week', a.alert_date)::date AS wk, count(*) AS alert_rows, count(DISTINCT (a.ticker, a.alert_date)) AS ticker_days, count(DISTINCT (a.ticker, a.alert_date)) FILTER (WHERE m.ticker IS NOT NULL) AS with_metrics_row, count(DISTINCT (a.ticker, a.alert_date)) FILTER (WHERE m.raw_alpaca_news_json IS NOT NULL OR m.raw_polygon_news_json IS NOT NULL) AS with_news_corpus FROM mi_ep_alerts a LEFT JOIN mi_ep_catalyst_metrics m ON m.ticker=a.ticker AND m.alert_date=a.alert_date WHERE a.alert_date >= '2026-09-01' GROUP BY 1 ORDER BY 1;

\echo '### Q9 provenance ticker-days per week since 09-01 matching the shadow population predicate (regex on detail; never cast)'
SELECT date_trunc('week', (substring(detail from '"alert_date": *"([0-9-]+)"'))::date)::date AS wk, count(DISTINCT (substring(detail from '"ticker": *"([A-Z.\-]+)"'), substring(detail from '"alert_date": *"([0-9-]+)"'))) AS ticker_days, count(DISTINCT (substring(detail from '"ticker": *"([A-Z.\-]+)"'), substring(detail from '"alert_date": *"([0-9-]+)"'))) FILTER (WHERE detail ~ '"catalyst_quality": *"routine"' OR detail ~ '"has_direct_source": *false') AS pop_pred FROM mi_audit_log WHERE event_type='ep_catalyst_provenance' AND created_at >= '2026-09-01' AND detail ~ '"alert_date": *"[0-9]{4}-[0-9]{2}-[0-9]{2}"' GROUP BY 1 ORDER BY 1;

\echo '### Q10 one provenance detail sample (shape)'
SELECT created_at AT TIME ZONE 'America/New_York' AS at_et, left(detail, 700) FROM mi_audit_log WHERE event_type='ep_catalyst_provenance' ORDER BY created_at DESC LIMIT 2;

\echo '### Q11 provenance rows for ACN 10-01 and PENG 10-07 (all ticks)'
SELECT created_at AT TIME ZONE 'America/New_York' AS at_et, left(detail, 400) FROM mi_audit_log WHERE event_type='ep_catalyst_provenance' AND ((detail LIKE '%"ticker": "ACN"%' AND detail LIKE '%2026-10-01%') OR (detail LIKE '%"ticker": "PENG"%' AND detail LIKE '%2026-10-07%')) ORDER BY created_at;

\echo '### Q12 mi_ep_alerts rows for the 10 shadow ticker-days (row count per key)'
SELECT a.ticker, a.alert_date, count(*) AS alert_rows FROM mi_ep_alerts a JOIN mi_tv_news_shadow s ON s.ticker=a.ticker AND s.alert_date=a.alert_date GROUP BY 1,2 ORDER BY 2;
