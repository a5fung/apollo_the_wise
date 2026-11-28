SET default_transaction_read_only = on;
\echo === per-day history 2026-08-01..2026-11-27 ===
WITH b AS (
  SELECT d.trade_date, d.ticker, d.open_price,
         lag(d.close)  OVER (PARTITION BY d.ticker ORDER BY d.trade_date) AS prev_close,
         lag(d.volume) OVER (PARTITION BY d.ticker ORDER BY d.trade_date) AS prev_volume
  FROM mi_daily_closes d WHERE d.trade_date >= DATE '2026-07-20' AND d.trade_date <= DATE '2026-11-27'
), g AS (
  SELECT b.trade_date, b.ticker,
         (b.open_price - b.prev_close)/NULLIF(b.prev_close,0)*100.0 AS gap,
         b.open_price, b.prev_close, b.prev_volume, s.security_type
  FROM b LEFT JOIN mi_security_types s ON s.ticker=b.ticker
  WHERE b.trade_date >= DATE '2026-08-01'
)
SELECT trade_date,
  count(*) FILTER (WHERE open_price IS NOT NULL) AS rows_with_open,
  count(*) FILTER (WHERE open_price IS NOT NULL AND prev_close>=5 AND prev_volume>=50000 AND gap>=10) AS supply_all,
  count(*) FILTER (WHERE open_price IS NOT NULL AND prev_close>=5 AND prev_volume>=50000 AND gap>=10 AND security_type IN ('CS','ADRC')) AS supply_stock,
  count(*) FILTER (WHERE open_price IS NOT NULL AND prev_close>=5 AND prev_volume>=50000 AND gap>=10 AND security_type IS NULL) AS supply_untyped,
  round(max(gap) FILTER (WHERE ticker='SPY')::numeric,2) AS spy_gap,
  round(max(gap) FILTER (WHERE ticker='QQQ')::numeric,2) AS qqq_gap
FROM g GROUP BY trade_date ORDER BY trade_date;
\echo === live alerts per day ===
SELECT alert_date, count(*) n, count(*) FILTER (WHERE score_tier='HIGH') high_n
FROM mi_ep_alerts WHERE alert_date >= DATE '2026-08-01' AND COALESCE(source,'live')='live' GROUP BY alert_date ORDER BY alert_date;
\echo === past lattice trigger-b pages ===
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary,160)
FROM mi_audit_log WHERE event_type ILIKE '%lattice%' AND created_at >= '2026-08-01' ORDER BY created_at;
