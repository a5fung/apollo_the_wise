SET default_transaction_read_only = on;
-- the two WOULD-FAIL-IF hits, split by era
SELECT (our_captured_at IS NOT NULL) AS post_fix, ticker, alert_date, tv_coverage_reaches_period_start,
       jsonb_array_length(tv_items_we_missed) AS n_missed
FROM mi_tv_news_shadow
WHERE tv_items_we_missed IS NOT NULL AND jsonb_array_length(tv_items_we_missed)=0
  AND tv_coverage_reaches_period_start IS NOT TRUE;
SELECT (s.our_captured_at IS NOT NULL) AS post_fix, count(*) AS untagged_items
FROM mi_tv_news_shadow s, jsonb_array_elements(s.tv_items_we_missed) i
WHERE s.tv_items_we_missed IS NOT NULL AND (i->>'match' IS NULL OR i->>'bucket' IS NULL) GROUP BY 1;
-- did our grade-time corpus hold the story? keyword hits per source
SELECT c.ticker, c.alert_date, c.raw_grade, c.sec_title,
  (c.alpaca_json::text ILIKE '%'||k.kw||'%') AS alpaca_hit,
  (c.fmp_json::text ILIKE '%'||k.kw||'%') AS fmp_hit,
  (c.perplexity_text ILIKE '%'||k.kw||'%') AS pplx_hit,
  k.kw
FROM mi_ep_grade_corpus c
JOIN (VALUES ('BSP',DATE '2026-10-14','Berkshire'),('LRCX',DATE '2026-11-06','buyback'),
             ('LRCX',DATE '2026-11-06','repurchase'),('GMAB',DATE '2026-10-28','Phase 3'),
             ('GMAB',DATE '2026-10-28','overall surviv'),('IRON',DATE '2026-10-19','trial'),
             ('INIO',DATE '2026-10-27','backlog'),('REGN',DATE '2026-10-30','R&D'),
             ('CHYM',DATE '2026-11-05','Rev'),('AMAT',DATE '2026-11-06','flash')) k(t,d,kw)
  ON c.ticker=k.t AND c.alert_date=k.d
ORDER BY 1,2;
