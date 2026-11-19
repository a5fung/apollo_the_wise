SET default_transaction_read_only = on;
-- B6 fork-B backtest (prereg: docs/analysis/b6_forkB_backtest_prereg_2026-11-19.md). READ-ONLY.
-- Run: psql -A -f pull_1_population.sql > pull_1_population.out   (psql -A, default '|' separator)
-- Returns: schema check for every column the other pulls name; last settled daily bar; the
-- population (every scored earnings candidate since 2026-05-19, plus any composite-downgrade
-- event with no scored row); every downgrade event as scalar fields (no free text); the
-- rubric-passed events; the daily regime rows.
\echo === SCHEMA ===
SELECT table_name, column_name, data_type FROM information_schema.columns
WHERE table_name IN ('mi_ep_scan_log','mi_ep_alerts','mi_live_trades','mi_ep_catalyst_metrics',
                     'mi_intraday_bars','mi_daily_closes','mi_market_regime','mi_stock_scores',
                     'mi_audit_log','mi_ep_score_shadow','mi_catalyst_tier_shadow')
ORDER BY table_name, ordinal_position;
\echo === LASTBAR ===
SELECT max(trade_date) AS last_daily_bar,
       (SELECT to_char(max(bar_time) AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') FROM mi_intraday_bars) AS last_minute_bar_et
FROM mi_daily_closes;
\echo === POP ===
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
       CASE WHEN p.alert_date >= '2026-08-22' THEN 'post' ELSE 'pre' END AS era,
       m.q_revenue_yoy_pct, m.extraction_quality,
       (m.ticker IS NOT NULL) AS has_metrics_row,
       (m.yoy_recovered_json IS NOT NULL) AS has_yoy_recovery,
       EXISTS (SELECT 1 FROM mi_ep_alerts e WHERE e.ticker = p.ticker AND e.alert_date = p.alert_date
               AND COALESCE(e.source,'live') = 'live') AS has_alert,
       (SELECT count(*) FROM ev WHERE ev.j->>'ticker' = p.ticker
               AND ev.j->>'alert_date' = p.alert_date::text) AS n_downgrade_events
FROM pop p LEFT JOIN mi_ep_catalyst_metrics m ON m.ticker = p.ticker AND m.alert_date = p.alert_date
ORDER BY p.alert_date, p.ticker;
\echo === DOWNGRADES ===
WITH ev AS MATERIALIZED (
  SELECT a.id AS event_id, a.created_at, a.detail::jsonb AS j
  FROM mi_audit_log a
  WHERE a.event_type = 'catalyst_earnings_revenue_weak_downgrade'
    AND a.created_at >= '2026-05-19' AND a.detail LIKE '{%'
)
SELECT event_id,
       to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS created_et,
       j->>'ticker' AS ticker, j->>'alert_date' AS alert_date,
       j->>'from_quality' AS from_quality, j->>'to_quality' AS to_quality,
       j->>'reason' AS reason,
       j->>'q_revenue_yoy_pct' AS q_revenue_yoy_pct,
       j->>'guidance_midpoint_yoy_pct' AS guidance_midpoint_yoy_pct,
       j->>'extraction_quality' AS extraction_quality,
       j->'rubric'->>'composite_scaled' AS composite_scaled,
       j->'rubric'->>'label' AS rubric_label,
       translate(COALESCE((j->'rubric'->'caps_applied')::text,''), E'|\n\r', '/  ') AS caps_applied,
       translate(COALESCE((j->'rubric'->'axes_scored')::text,''), E'|\n\r', '/  ') AS axes_scored,
       j->>'earnings_source' AS earnings_source,
       j->>'gap_pct' AS gap_pct
FROM ev ORDER BY created_at;
\echo === RUBRIC_PASSED ===
SELECT a.id AS event_id,
       to_char(a.created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS created_et,
       a.detail::jsonb->>'ticker' AS ticker, a.detail::jsonb->>'alert_date' AS alert_date,
       a.detail::jsonb->'rubric'->>'composite_scaled' AS composite_scaled,
       a.detail::jsonb->'rubric'->>'label' AS rubric_label,
       a.detail::jsonb->>'gap_pct' AS gap_pct
FROM mi_audit_log a
WHERE a.event_type = 'catalyst_rubric_passed' AND a.detail LIKE '{%'
ORDER BY a.created_at;
\echo === REGIME ===
SELECT regime_date, regime, ep_threshold FROM mi_market_regime
WHERE regime_date >= '2026-05-01' ORDER BY regime_date;
