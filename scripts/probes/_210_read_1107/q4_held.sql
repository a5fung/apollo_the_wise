SET default_transaction_read_only = on;
-- the rest of the strict rows: did our grade-time corpus hold the story TradingView carried?
SELECT c.ticker, c.alert_date, c.raw_grade, k.kw,
  (c.alpaca_json::text ILIKE '%'||k.kw||'%') AS alpaca_hit,
  (c.fmp_json::text ILIKE '%'||k.kw||'%') AS fmp_hit,
  (c.perplexity_text ILIKE '%'||k.kw||'%') AS pplx_hit,
  (m.raw_polygon_news_json::text ILIKE '%'||k.kw||'%') AS polygon_hit
FROM mi_ep_grade_corpus c
JOIN (VALUES ('RRC',DATE '2026-10-26','EQT'),('REGN',DATE '2026-10-30','guidance'),
             ('REGN',DATE '2026-10-30','quarter'),('BSP',DATE '2026-10-14','stake'),
             ('BSP',DATE '2026-10-14','330'),('LSCC',DATE '2026-11-03','price target'),
             ('ALAB',DATE '2026-11-06','relief'),('NBIS',DATE '2026-11-06','Leverage Shares')) k(t,d,kw)
  ON c.ticker=k.t AND c.alert_date=k.d
LEFT JOIN mi_ep_catalyst_metrics m ON m.ticker=c.ticker AND m.alert_date=c.alert_date
ORDER BY 1,2;
-- BSP: what did our grade-time corpus actually say?
SELECT left(perplexity_text, 600) AS pplx, jsonb_array_length(alpaca_json) AS n_alpaca,
       jsonb_array_length(fmp_json) AS n_fmp, captured_at
FROM mi_ep_grade_corpus WHERE ticker='BSP' AND alert_date='2026-10-14';
