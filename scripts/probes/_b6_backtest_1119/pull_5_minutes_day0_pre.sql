SET default_transaction_read_only = on;
-- Returns: alert-day regular-session 1-minute bars (09:30-15:59 ET) for every population
-- (ticker, day) - PRE-RESCALE (separate column only, never pooled). Expect roughly 80k rows.
-- Same column order as scripts/ep_replay_data/_pull4_min.sql so ep_replay's loader shape holds.
-- Forward sessions are walked on DAILY bars (the harness's own contract) - no forward minutes.
-- Run: psql -A -f pull_5_minutes_day0_pre.sql | gzip > pull_5_minutes_day0_pre.out.gz
\echo === MINCOV ===
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
)
SELECT p.ticker, p.alert_date,
       count(b.bar_time) AS rth_bars,
       count(b.bar_time) FILTER (WHERE (b.bar_time AT TIME ZONE 'America/New_York')::time = '09:30') AS has_930,
       count(b.bar_time) FILTER (WHERE (b.bar_time AT TIME ZONE 'America/New_York')::time >= '09:31'
                            AND (b.bar_time AT TIME ZONE 'America/New_York')::time <  '10:00') AS bars_0931_0959
FROM pop p LEFT JOIN mi_intraday_bars b
  ON b.ticker = p.ticker
 AND b.bar_time >= ((p.alert_date + time '09:30') AT TIME ZONE 'America/New_York')
 AND b.bar_time <  ((p.alert_date + time '16:00') AT TIME ZONE 'America/New_York')
WHERE p.alert_date < '2026-08-22'
GROUP BY 1,2 ORDER BY 2,1;
\echo === MIN ===
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
)
SELECT b.ticker,
       to_char(b.bar_time AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI') AS et_min,
       b.open, b.high, b.low, b.close, b.volume
FROM pop p JOIN mi_intraday_bars b
  ON b.ticker = p.ticker
 AND b.bar_time >= ((p.alert_date + time '09:30') AT TIME ZONE 'America/New_York')
 AND b.bar_time <  ((p.alert_date + time '16:00') AT TIME ZONE 'America/New_York')
WHERE p.alert_date < '2026-08-22'
ORDER BY b.ticker, b.bar_time;
