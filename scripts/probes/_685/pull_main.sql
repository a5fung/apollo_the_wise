-- #685 — the ONE read-only prod pull (small sections). Captured once; every later step reads the file.
-- Cohort = every ticker that ever carried a live EP alert or a MAGNA53 trade (the ep_replay _pull2 cohort,
-- naturally extended to September). Minute bars are in pull_min.sql (gzipped separately).
\echo === LASTDAY ===
SELECT max(trade_date) AS last_full_day FROM (SELECT trade_date FROM mi_daily_closes GROUP BY trade_date HAVING count(*) >= 500) s;
\echo === STRAT ===
SELECT strategy_id, phase, enabled, live_real_enabled, profit_trigger_r, breakeven_arm_r, position_size_multiplier, max_concurrent_positions
FROM mi_strategies WHERE strategy_id LIKE 'magna53%' ORDER BY strategy_id;
\echo === TRADES ===
SELECT id, ticker, alert_date, account_mode, signal_type, status, entry_attempt,
       orb_high, orb_low, atr_14, entry_price, entry_shares, stop_price, hard_stop,
       risk_dollars, risk_dollars_actual, total_pnl, remaining_shares,
       partial_taken, breakeven_active, pnl_attribution, hold_days, skip_reason,
       highest_price_seen, lowest_price_seen,
       filled_at AT TIME ZONE 'America/New_York' AS filled_at_et,
       closed_at AT TIME ZONE 'America/New_York' AS closed_at_et,
       exits::text AS exits_json, running_closes::text AS running_closes_json
FROM mi_live_trades
WHERE signal_type LIKE 'magna53%' AND alert_date >= '2026-08-01'
ORDER BY alert_date, ticker;
\echo === ALERTS ===
SELECT id, ticker, alert_date, gap_pct, rel_volume, ep_score, score_tier,
       catalyst_quality, vol_percentile, in_active_theme, pm_rvol,
       judge_tier, grade_engine_authority, confidence_multiplier,
       detected_at AT TIME ZONE 'America/New_York' AS detected_at_et
FROM mi_ep_alerts WHERE COALESCE(source,'live')='live' AND alert_date >= '2026-09-01'
ORDER BY alert_date, ticker;
\echo === REGIME ===
SELECT regime_date, regime, ep_threshold FROM mi_market_regime WHERE regime_date >= '2026-08-01' ORDER BY regime_date;
\echo === ADV ===
WITH cohort AS (
  SELECT DISTINCT ticker FROM mi_ep_alerts WHERE COALESCE(source,'live')='live'
  UNION SELECT DISTINCT ticker FROM mi_live_trades WHERE signal_type LIKE 'magna53%'
)
SELECT s.ticker, s.score_date, s.adv_20 FROM mi_stock_scores s JOIN cohort c USING (ticker)
WHERE s.adv_20 IS NOT NULL AND s.score_date >= '2026-08-01' ORDER BY s.ticker, s.score_date;
\echo === DAILY ===
WITH cohort AS (
  SELECT DISTINCT ticker FROM mi_ep_alerts WHERE COALESCE(source,'live')='live'
  UNION SELECT DISTINCT ticker FROM mi_live_trades WHERE signal_type LIKE 'magna53%'
)
SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close, d.volume
FROM mi_daily_closes d JOIN cohort c USING (ticker)
WHERE d.trade_date >= '2026-01-01'
ORDER BY d.ticker, d.trade_date;
\echo === MINCOV ===
WITH cohort AS (
  SELECT DISTINCT ticker FROM mi_ep_alerts WHERE COALESCE(source,'live')='live'
  UNION SELECT DISTINCT ticker FROM mi_live_trades WHERE signal_type LIKE 'magna53%'
)
SELECT b.ticker, (b.bar_time AT TIME ZONE 'America/New_York')::date AS d, COUNT(*) AS n,
       to_char(min(b.bar_time) AT TIME ZONE 'America/New_York','HH24:MI') AS first_et,
       to_char(max(b.bar_time) AT TIME ZONE 'America/New_York','HH24:MI') AS last_et
FROM mi_intraday_bars b JOIN cohort c USING (ticker)
GROUP BY 1,2 ORDER BY 1,2;
\echo === OKTA_ORDERS ===
SELECT o.trade_id, o.alpaca_order_id, o.purpose, o.exit_reason, o.status, o.side, o.order_type, o.qty, o.limit_price, o.stop_price,
       o.filled_qty, o.filled_avg_price,
       o.submitted_at AT TIME ZONE 'America/New_York' AS submitted_et,
       o.filled_at AT TIME ZONE 'America/New_York' AS filled_et,
       o.cancelled_at AT TIME ZONE 'America/New_York' AS cancelled_et
FROM mi_live_orders o WHERE o.trade_id = 382 ORDER BY o.submitted_at;
\echo === OKTA_AUDIT ===
SELECT id, created_at AT TIME ZONE 'America/New_York' AS created_et, event_type, left(summary, 300) AS summary, left(detail, 600) AS detail
FROM mi_audit_log WHERE created_at >= '2026-09-15' AND (summary ILIKE '%OKTA%' OR detail ILIKE '%OKTA%')
  AND (event_type ILIKE '%stop%' OR event_type ILIKE '%exit%' OR event_type ILIKE '%breakeven%' OR event_type ILIKE '%trail%')
ORDER BY created_at;
