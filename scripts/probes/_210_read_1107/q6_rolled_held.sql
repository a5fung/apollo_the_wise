SET default_transaction_read_only = on;
-- the rolled rows' before-grade 'none' items: did our grade-time corpus hold the story?
SELECT c.ticker, c.raw_grade, k.kw, (c.alpaca_json::text ILIKE '%'||k.kw||'%') AS alpaca_hit,
       (c.fmp_json::text ILIKE '%'||k.kw||'%') AS fmp_hit, (c.perplexity_text ILIKE '%'||k.kw||'%') AS pplx_hit,
       (m.raw_polygon_news_json::text ILIKE '%'||k.kw||'%') AS polygon_hit, c.sec_title
FROM mi_ep_grade_corpus c
JOIN (VALUES ('SPCX',DATE '2026-10-21','Tesla'),('SPCX',DATE '2026-10-21','merger'),
             ('SOFI',DATE '2026-10-27','5.04'),('SOFI',DATE '2026-10-27','6.4'),('SOFI',DATE '2026-10-27','guid'),
             ('MRNA',DATE '2026-11-06','8.1'),('MRNA',DATE '2026-11-06','cash'),
             ('FN',DATE '2026-11-03','repurchase'),('VRT',DATE '2026-10-28','margin'),
             ('CLS',DATE '2026-10-27','earnings')) k(t,d,kw)
  ON c.ticker=k.t AND c.alert_date=k.d
LEFT JOIN mi_ep_catalyst_metrics m ON m.ticker=c.ticker AND m.alert_date=c.alert_date
ORDER BY 1,3;
SELECT ticker, left(perplexity_text, 450) FROM mi_ep_grade_corpus WHERE (ticker,alert_date) IN (('SPCX','2026-10-21'),('MRNA','2026-11-06'));
