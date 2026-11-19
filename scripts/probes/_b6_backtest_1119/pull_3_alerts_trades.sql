SET default_transaction_read_only = on;
-- Returns: every live EP alert since 2026-05-19 (floor tier, judge tier, final tier, detection
-- time) - the PASS arm's actual alerts, the ALL-HIGH comparator, the judge keep-rate denominator and each morning's
-- competing HIGH board; every trade row of EVERY strategy since 05-01 (the position cap counts all open positions on an account) (entries, skips and their reasons -
-- the slot-cap / breaker column and the PASS arm's real fills); prior-day RS and ADV for the
-- population AND every post-rescale alert (slot rank + ADV cross-check); other audit events that touch the counterfactual.
-- Run: psql -A -f pull_3_alerts_trades.sql > pull_3_alerts_trades.out
\echo === ALERTS ===
SELECT e.id, e.ticker, e.alert_date, e.gap_pct, e.rel_volume, e.ep_score, e.score_tier,
       e.baseline_floor_tier, e.judge_tier, e.judge_direction, e.grade_engine_authority,
       e.catalyst_quality, e.confidence_multiplier, e.vol_percentile, e.in_active_theme, e.pm_rvol,
       to_char(e.detected_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS detected_at_et
FROM mi_ep_alerts e
WHERE e.alert_date >= '2026-05-19' AND COALESCE(e.source,'live') = 'live'
ORDER BY e.alert_date, e.ticker, e.id;
\echo === TRADES ===
SELECT t.id, t.ticker, t.alert_date, t.account_mode, t.signal_type, t.status, t.entry_attempt,
       translate(COALESCE(t.skip_reason,''), E'|\n\r', '/  ') AS skip_reason,
       t.orb_high, t.orb_low, t.atr_14, t.entry_price, t.entry_shares, t.stop_price, t.hard_stop,
       t.risk_dollars, t.total_pnl,
       to_char(t.filled_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS filled_at_et,
       to_char(t.closed_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS closed_at_et
FROM mi_live_trades t
WHERE t.alert_date >= '2026-05-01'
ORDER BY t.alert_date, t.ticker, t.id;
\echo === RSADV ===
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
SELECT p.ticker, p.alert_date, s.score_date, s.rs_composite, s.rs_rank, s.adv_20
FROM wide p JOIN LATERAL (
  SELECT score_date, rs_composite, rs_rank, adv_20 FROM mi_stock_scores
  WHERE ticker = p.ticker AND score_date < p.alert_date AND score_date >= p.alert_date - 10
  ORDER BY score_date DESC LIMIT 1) s ON TRUE
ORDER BY p.alert_date, p.ticker;
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
FROM evx x JOIN pop p ON p.ticker = x.j->>'ticker' AND p.alert_date = x.et_date
ORDER BY x.created_at;
