SET default_transaction_read_only = on;
-- Returns: daily bars (open/high/low/close/volume) since 2026-01-01 for every population ticker
-- and every post-rescale alerted ticker (the ALL-HIGH comparator):
-- the forward exit-ladder walk, ADR20 / ATR14, the moving-average trail, the prior close.
-- Expect roughly 90k rows.  Run: psql -A -f pull_4_daily.sql | gzip > pull_4_daily.out.gz
\echo === DAILY ===
WITH ev AS MATERIALIZED (
  SELECT a.id AS event_id, a.created_at,
         a.detail::jsonb AS j
  FROM mi_audit_log a
  WHERE a.event_type = 'catalyst_earnings_revenue_weak_downgrade'
    AND a.created_at >= '2026-05-19' AND a.detail LIKE '{%'
), pop AS (
  SELECT m.ticker, m.alert_date FROM mi_ep_catalyst_metrics m
  WHERE m.alert_date >= '2026-05-19' AND m.alert_date < (now() AT TIME ZONE 'America/New_York')::date
    AND m.q_revenue_yoy_pct IS NOT NULL
  UNION
  SELECT ev.j->>'ticker', (ev.j->>'alert_date')::date FROM ev
  WHERE ev.j->>'reason' LIKE 'rubric_composite_%' AND ev.j->>'alert_date' >= '2026-05-19'
    AND (ev.j->>'alert_date')::date < (now() AT TIME ZONE 'America/New_York')::date
), wide AS (
  -- population + every real post-rescale live alert (the ALL-HIGH comparator and each
  -- morning's competing board)
  SELECT ticker, alert_date FROM pop
  UNION
  SELECT e.ticker, e.alert_date FROM mi_ep_alerts e
  WHERE e.alert_date >= '2026-08-22' AND e.alert_date < (now() AT TIME ZONE 'America/New_York')::date
    AND COALESCE(e.source,'live') = 'live'
)
SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close, d.volume
FROM mi_daily_closes d
WHERE d.trade_date >= '2026-01-01'
  AND d.ticker IN (SELECT DISTINCT ticker FROM wide)
ORDER BY d.ticker, d.trade_date;
