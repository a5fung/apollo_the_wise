SET default_transaction_read_only = on;
SELECT 'alpaca' AS src, i->>'headline' AS title, i->>'created_at' AS published
FROM mi_ep_grade_corpus c, jsonb_array_elements(c.alpaca_json) i WHERE c.ticker='MRNA' AND c.alert_date='2026-11-06'
UNION ALL
SELECT 'polygon', i->>'title', i->>'published_utc'
FROM mi_ep_catalyst_metrics m, jsonb_array_elements(m.raw_polygon_news_json) i WHERE m.ticker='MRNA' AND m.alert_date='2026-11-06'
UNION ALL
SELECT 'fmp', i->>'title', i->>'publishedDate'
FROM mi_ep_grade_corpus c, jsonb_array_elements(c.fmp_json) i WHERE c.ticker='MRNA' AND c.alert_date='2026-11-06';
SELECT captured_at FROM mi_ep_grade_corpus WHERE ticker='MRNA' AND alert_date='2026-11-06';
