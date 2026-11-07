SET default_transaction_read_only = on;
-- the 9 post-frame rows whose window did not reach the prior close: what did TradingView carry that we did not match?
SELECT s.ticker, s.alert_date, s.our_acting_grade, s.catalyst_quality, s.tv_coverage_reaches_period_start AS reaches,
       s.tv_unseen_minutes_at_period_start AS unseen_min, s.tv_items_before_grade AS before_n,
       (SELECT string_agg(i->>'bucket'||':'||(i->>'match')||':'||left(i->>'title',110), ' || ')
          FROM jsonb_array_elements(s.tv_items_unmatched_seen) i) AS unmatched
FROM mi_tv_news_shadow s
WHERE s.our_captured_at IS NOT NULL AND s.tv_items_we_missed IS NULL
ORDER BY s.alert_date, s.ticker;
-- denominator: distinct alert ticker-days in the window vs shadow rows
SELECT count(DISTINCT (a.ticker, a.alert_date)) AS alert_days,
       count(DISTINCT (a.ticker, a.alert_date)) FILTER (WHERE s.ticker IS NOT NULL) AS with_shadow_row
FROM mi_ep_alerts a LEFT JOIN mi_tv_news_shadow s ON s.ticker=a.ticker AND s.alert_date=a.alert_date
WHERE a.alert_date BETWEEN '2026-10-12' AND '2026-11-06';
SELECT a.ticker, a.alert_date FROM mi_ep_alerts a
LEFT JOIN mi_tv_news_shadow s ON s.ticker=a.ticker AND s.alert_date=a.alert_date
WHERE a.alert_date BETWEEN '2026-10-12' AND '2026-11-06' AND s.ticker IS NULL
GROUP BY 1,2 ORDER BY 2,1;
-- the two weak "held" calls, with the actual figures
SELECT c.ticker, k.kw, (c.alpaca_json::text ILIKE '%'||k.kw||'%') AS alpaca_hit,
       (c.fmp_json::text ILIKE '%'||k.kw||'%') AS fmp_hit, (c.perplexity_text ILIKE '%'||k.kw||'%') AS pplx_hit,
       (m.raw_polygon_news_json::text ILIKE '%'||k.kw||'%') AS polygon_hit
FROM mi_ep_grade_corpus c
JOIN (VALUES ('CHYM',DATE '2026-11-05','2.79'),('CHYM',DATE '2026-11-05','2.8 b'),('CHYM',DATE '2026-11-05','2.8b'),
             ('CHYM',DATE '2026-11-05','guid'),('CHYM',DATE '2026-11-05','outlook'),
             ('INIO',DATE '2026-10-27','8B'),('INIO',DATE '2026-10-27','8 billion'),('INIO',DATE '2026-10-27','backlog')) k(t,d,kw)
  ON c.ticker=k.t AND c.alert_date=k.d
LEFT JOIN mi_ep_catalyst_metrics m ON m.ticker=c.ticker AND m.alert_date=c.alert_date
ORDER BY 1,2;
SELECT ticker, left(perplexity_text, 700) FROM mi_ep_grade_corpus WHERE (ticker,alert_date) IN (('CHYM','2026-11-05'),('INIO','2026-10-27'));
