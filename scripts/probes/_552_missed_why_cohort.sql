-- #552-adjacent probe (read-only): rebuild the tier-A real-stock gap-day cohort
-- 2026-03-01..07-15 and join every funnel surface we have, to attribute WHY the
-- 72 missed tail winners never became alerts. Mirrors the SQL shape in
-- docs/roadmap/ep_profitability_program.md 2026-08-16 "ETF CONTAMINATION FIXED".
WITH stocks AS (
  SELECT ticker FROM mi_stock_scores GROUP BY 1
  HAVING count(*) FILTER (WHERE sector IS NOT NULL) > 0),
d AS (
  SELECT ticker, trade_date, open_price o, high_price h, close c, volume v,
    lag(close) OVER w pc,
    avg((high_price-low_price)/nullif(close,0)) OVER (PARTITION BY ticker ORDER BY trade_date
        ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) adr,
    max(high_price) OVER (PARTITION BY ticker ORDER BY trade_date
        ROWS BETWEEN 1 FOLLOWING AND 20 FOLLOWING) fwd_hi
  FROM mi_daily_closes WHERE trade_date >= '2026-03-01'
  WINDOW w AS (PARTITION BY ticker ORDER BY trade_date)),
g AS (
  SELECT ticker, trade_date, o, h, pc, c, v, adr, fwd_hi,
    (o-pc)/pc AS gap, (fwd_hi-c)/c/adr AS tailx
  FROM d
  WHERE pc>0 AND adr>0 AND c>=10 AND c*v>=50e6 AND (o-pc)/pc>=0.08
    AND trade_date<='2026-07-15'
    AND ticker IN (SELECT ticker FROM stocks))
SELECT g.ticker, g.trade_date,
  round((g.gap*100)::numeric,2)       AS gap_pct,
  round(g.o::numeric,2)               AS o,
  round(g.h::numeric,2)               AS hi,
  round(g.pc::numeric,2)              AS pc,
  round(g.c::numeric,2)               AS c,
  round((g.adr*100)::numeric,2)       AS adr_pct,
  round((g.c*g.v/1e6)::numeric,1)     AS dvol_m,
  round(g.tailx::numeric,2)           AS tailx,
  CASE WHEN g.tailx>=8 THEN 1 ELSE 0 END AS winner,
  COALESCE(a.n,0)                     AS alert_n,
  COALESCE(a.tiers,'')                AS alert_tiers,
  COALESCE(s.n,0)                     AS scan_n,
  COALESCE(s.reasons,'')              AS scan_reasons,
  COALESCE(s.max_score::text,'')      AS scan_max_score,
  COALESCE(m.srcs,'')                 AS mo_sources,
  COALESCE(m.cats,'')                 AS mo_cats,
  COALESCE(m.reasons,'')              AS mo_reasons
FROM g
LEFT JOIN LATERAL (
  SELECT count(*) n, string_agg(DISTINCT score_tier,',') tiers
  FROM mi_ep_alerts a
  WHERE a.ticker=g.ticker AND a.alert_date=g.trade_date
    AND COALESCE(a.source,'live')='live') a ON true
LEFT JOIN LATERAL (
  SELECT count(*) n,
         string_agg(DISTINCT COALESCE(filter_reason,'<none>'),' ;; ') reasons,
         max(ep_score) max_score
  FROM mi_ep_scan_log s
  WHERE s.ticker=g.ticker AND s.scan_date=g.trade_date) s ON true
LEFT JOIN LATERAL (
  SELECT string_agg(DISTINCT source,',') srcs,
         string_agg(DISTINCT skip_category,',') cats,
         string_agg(DISTINCT COALESCE(skip_reason,'<null>'),' ;; ') reasons
  FROM mi_ep_missed_outcomes m
  WHERE m.ticker=g.ticker AND m.alert_date=g.trade_date) m ON true
ORDER BY g.trade_date, g.ticker;
