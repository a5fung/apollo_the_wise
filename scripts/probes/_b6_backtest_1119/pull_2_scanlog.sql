SET default_transaction_read_only = on;
-- Returns: EVERY mi_ep_scan_log row (one per scan tick) for each population (ticker, day):
-- the per-tick gate verdict, the stored score, and the #605 score inputs (score_breakdown,
-- vol_percentile, float_shares, ep_bar, score_side). This is what the re-score reads.
-- Also a coverage table: how many ticks carry a stored breakdown, by era and reject stage.
-- Expect roughly 10-20k rows.  Run: psql -A -f pull_2_scanlog.sql | gzip > pull_2_scanlog.out.gz
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
FROM mi_ep_scan_log s JOIN pop p ON p.ticker = s.ticker AND p.alert_date = s.scan_date
ORDER BY s.scan_date, s.ticker, s.scan_time_et, s.id;
\echo === SCANCOV ===
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
SELECT CASE WHEN s.scan_date >= '2026-08-29' THEN 'post_605'
            WHEN s.scan_date >= '2026-08-22' THEN 'post_pre605' ELSE 'pre' END AS era,
       COALESCE(s.reject_stage,'(none)') AS reject_stage,
       count(*) AS ticks,
       count(*) FILTER (WHERE s.ep_score IS NOT NULL) AS with_score,
       count(*) FILTER (WHERE s.score_breakdown IS NOT NULL) AS with_breakdown,
       count(*) FILTER (WHERE s.vol_percentile IS NOT NULL) AS with_vol_pct,
       count(*) FILTER (WHERE s.float_shares IS NOT NULL) AS with_float,
       count(DISTINCT (s.ticker, s.scan_date)) AS ticker_days
FROM mi_ep_scan_log s JOIN pop p ON p.ticker = s.ticker AND p.alert_date = s.scan_date
GROUP BY 1,2 ORDER BY 1,2;
\echo === SCORESHADOW ===
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
SELECT h.ticker, h.scan_date,
       to_char(h.first_seen_et AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') AS first_et,
       to_char(h.last_seen_et AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') AS last_et,
       h.sep_score_first, h.sep_score_last, h.sep_tier_first, h.sep_tier_last,
       h.sep_bar, h.live_side, h.gap_pct_first, h.gap_pct_last, h.catalyst_quality_last
FROM mi_ep_score_shadow h JOIN pop p ON p.ticker = h.ticker AND p.alert_date = h.scan_date
ORDER BY h.scan_date, h.ticker;
\echo === TIERSHADOW ===
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
SELECT t.ticker, t.scan_date, t.live_quality_first, t.live_quality_last,
       t.shadow_tier_first, t.shadow_tier_last, t.rule_first, t.rule_last, t.live_side,
       t.expct_sched, t.expct_combined, t.expct_beat, t.demotion_marker, t.concrete_event,
       t.sector_confirm, t.live_ep_score, t.live_tier
FROM mi_catalyst_tier_shadow t JOIN pop p ON p.ticker = t.ticker AND p.alert_date = t.scan_date
ORDER BY t.scan_date, t.ticker;
