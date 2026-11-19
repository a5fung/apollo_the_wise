SET default_transaction_read_only = on;
-- FOLLOW-UP PULL (not yet run). Closes the gap found in phase 2: pull_2 SCANLOG and pull_3 EVENTS
-- were joined to the earnings population only, so the 35 real post-rescale HIGH alerts OUTSIDE it
-- (the ALL-HIGH comparator) have no scan ticks and no flip events — the replay's board and
-- open-below-floor gates were silently off for them. Returns ONLY the rows the first pulls lack
-- (same columns, same section names). Expect roughly 1-2k rows.
-- Run: psql -A -f pull_6_wide_ticks_events.sql > pull_6_wide_ticks_events.out
\echo === SCANLOG ===
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
SELECT s.id, s.ticker, s.scan_date,
       to_char(s.scan_time_et AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS scan_et,
       s.minutes_since_open, s.reject_stage,
       translate(COALESCE(s.filter_reason,''), E'|\n\r', '/  ') AS filter_reason,
       s.ep_score, s.score_tier, s.ep_bar, s.score_side,
       s.catalyst_quality, s.llm_catalyst_quality,
       s.score_breakdown::text AS score_breakdown,
       s.gap_pct, s.gap_pct_rt, s.gap_pct_delayed, s.price_source,
       s.prev_close, s.current_price, s.rel_volume, s.projected_vol_multiple,
       s.pm_rvol, s.today_volume, s.adv, s.vol_percentile, s.float_shares,
       s.in_active_theme, s.prior_3m_change, s.extension_pct, s.days_since_prior_alert,
       s.market_cap, s.atr_pct, s.rank_by_gap, s.rank_by_prescore
FROM mi_ep_scan_log s JOIN wide p ON p.ticker = s.ticker AND p.alert_date = s.scan_date
WHERE NOT EXISTS (SELECT 1 FROM pop q WHERE q.ticker = s.ticker AND q.alert_date = s.scan_date)
ORDER BY s.scan_date, s.ticker, s.scan_time_et, s.id;
\echo === EVENTS ===
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
), evx AS MATERIALIZED (
  SELECT a.id AS event_id, a.event_type, a.created_at, a.detail::jsonb AS j,
         (a.created_at AT TIME ZONE 'America/New_York')::date AS et_date
  FROM mi_audit_log a
  WHERE a.created_at >= '2026-05-19' AND a.detail LIKE '{%'
    AND a.event_type IN ('ep_rt_floor_flip_up','earnings_override_applied',
                         'earnings_override_skipped_post_downgrade',
                         'catalyst_prose_mismatch_downgrade','catalyst_earnings_boost',
                         'ep_rt_floor_flip_down')
)
SELECT x.event_id, x.event_type,
       to_char(x.created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS created_et,
       x.j->>'ticker' AS ticker, x.et_date,
       x.j->>'tick_et' AS tick_et,
       x.j->>'authoritative' AS authoritative,
       x.j->>'acted' AS acted,
       x.j->>'ep_score' AS ep_score,
       x.j->>'from_quality' AS from_quality,
       x.j->>'matched_marker' AS matched_marker
FROM evx x JOIN wide p ON p.ticker = x.j->>'ticker' AND p.alert_date = x.et_date
WHERE NOT EXISTS (SELECT 1 FROM pop q WHERE q.ticker = x.j->>'ticker' AND q.alert_date = x.et_date)
ORDER BY x.created_at;
