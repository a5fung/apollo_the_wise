\echo === U1 fmp news emptiness in mi_ep_catalyst_metrics last 30d
SELECT count(*) AS n, count(*) FILTER (WHERE raw_fmp_news_json IS NULL) AS fmp_null, count(*) FILTER (WHERE raw_fmp_news_json = '[]'::jsonb) AS fmp_empty, count(*) FILTER (WHERE jsonb_array_length(coalesce(raw_fmp_news_json,'[]'::jsonb))>0) AS fmp_nonempty
FROM mi_ep_catalyst_metrics WHERE alert_date >= '2026-09-12';
