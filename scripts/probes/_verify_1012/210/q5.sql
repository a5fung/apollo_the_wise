\echo === T1 fmp/alpaca json null vs empty on todays grade-corpus rows
SELECT ticker, (fmp_json IS NULL) AS fmp_null, (fmp_json = '[]'::jsonb) AS fmp_empty, (alpaca_json IS NULL) AS alp_null, (alpaca_json = '[]'::jsonb) AS alp_empty, (perplexity_text IS NULL) AS pplx_null
FROM mi_ep_grade_corpus WHERE alert_date='2026-10-12' ORDER BY ticker;
\echo === T2 mi_ep_alerts 10-12
SELECT count(*) FROM mi_ep_alerts WHERE alert_date='2026-10-12';
