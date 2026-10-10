-- #559 era-D re-cut (2026-10-10) — capture 1 of 2: state, events, alerts, trades, scan log,
-- minute-bar COVERAGE. READ-ONLY (SELECT only), $0. Run ONCE via the stdin psql form; the
-- analysis reads c1_scope.out and never re-runs this. Window = alert days 2026-09-08..2026-10-09
-- (era D first acting session .. last settled session before the 10-12 depth-exit go-live).
\set ON_ERROR_STOP off
\pset footer on

\echo === STATE ===
SELECT safeguard, account_mode, state,
       to_char(last_transition_at AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI') AS since_et,
       to_char(updated_at AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI') AS updated_et
FROM mi_safeguard_state
WHERE safeguard LIKE 'ep_rt%' OR safeguard LIKE '%depth%' OR safeguard LIKE 'profit_take%'
ORDER BY safeguard, account_mode;

\echo === STRATEGIES ===
SELECT strategy_id, name, phase, profit_trigger_r, breakeven_arm_r FROM mi_strategies ORDER BY strategy_id;

\echo === EVCOUNT ===
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, event_type, count(*) AS n
FROM mi_audit_log
WHERE event_type LIKE 'ep_rt_%' AND event_type <> 'ep_rt_universe_coverage'
  AND (created_at AT TIME ZONE 'America/New_York')::date BETWEEN '2026-09-08' AND '2026-10-09'
GROUP BY 1,2 ORDER BY 1,2;

\echo === EVENTS ===
SELECT id,
       (created_at AT TIME ZONE 'America/New_York')::date AS d,
       to_char(created_at AT TIME ZONE 'America/New_York', 'HH24:MI:SS') AS t_et,
       event_type,
       detail::json->>'ticker' AS ticker,
       detail::json->>'tick_et' AS tick_et,
       detail::json->>'rt_gap' AS rt_gap,
       detail::json->>'delayed_gap' AS delayed_gap,
       detail::json->>'authoritative' AS authoritative,
       detail::json->>'declined_reason' AS declined_reason,
       detail::json->>'reason' AS reason,
       detail::json->>'acted' AS acted,
       replace(replace(summary, E'\t', ' '), E'\n', ' ') AS summary
FROM mi_audit_log
WHERE event_type LIKE 'ep_rt_%' AND event_type <> 'ep_rt_universe_coverage'
  AND (created_at AT TIME ZONE 'America/New_York')::date BETWEEN '2026-09-08' AND '2026-10-09'
ORDER BY created_at;

\echo === ALERTS ===
SELECT id, ticker, alert_date, gap_pct, ep_score, score_tier, catalyst_quality, judge_tier, judge_grade,
       grade_engine_authority, in_active_theme, COALESCE(source,'live') AS source,
       to_char(detected_at AT TIME ZONE 'America/New_York', 'HH24:MI:SS') AS detected_et,
       to_char(created_at AT TIME ZONE 'America/New_York', 'HH24:MI:SS') AS created_et
FROM mi_ep_alerts
WHERE alert_date BETWEEN '2026-09-08' AND '2026-10-09'
ORDER BY alert_date, ticker;

\echo === TRADES ===
SELECT id, ticker, alert_date, signal_type, account_mode, status, entry_attempt, skip_reason,
       orb_high, orb_low, atr_14, entry_price, entry_shares, stop_price, hard_stop,
       risk_dollars, risk_dollars_actual, total_pnl, remaining_shares, partial_taken, breakeven_active,
       highest_price_seen, lowest_price_seen, pnl_attribution,
       to_char(filled_at AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI:SS') AS filled_et,
       to_char(closed_at AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI:SS') AS closed_et,
       replace(replace(exits::text, E'\t', ' '), E'\n', ' ') AS exits_json
FROM mi_live_trades
WHERE alert_date BETWEEN '2026-09-08' AND '2026-10-09'
ORDER BY alert_date, ticker, id;

\echo === ORBEVENTS ===
SELECT id, (created_at AT TIME ZONE 'America/New_York')::date AS d,
       to_char(created_at AT TIME ZONE 'America/New_York', 'HH24:MI:SS') AS t_et,
       event_type, replace(replace(summary, E'\t', ' '), E'\n', ' ') AS summary
FROM mi_audit_log
WHERE (event_type LIKE 'orb_%' OR event_type LIKE 'window%' OR event_type LIKE 'partial_exit%'
       OR event_type LIKE 'breakeven%' OR event_type LIKE 'profit_take%')
  AND (created_at AT TIME ZONE 'America/New_York')::date BETWEEN '2026-09-08' AND '2026-10-09'
ORDER BY created_at;

\echo === SCANSRC ===
SELECT scan_date, price_source, count(DISTINCT ticker) AS tickers, count(*) AS rows_n
FROM mi_ep_scan_log
WHERE scan_date BETWEEN '2026-09-08' AND '2026-10-09'
GROUP BY 1,2 ORDER BY 1,2;

\echo === SCANLOG ===
WITH ev AS (
  SELECT DISTINCT detail::json->>'ticker' AS ticker,
         (created_at AT TIME ZONE 'America/New_York')::date AS d
  FROM mi_audit_log
  WHERE event_type IN ('ep_rt_universe_catch','ep_rt_floor_flip_up','ep_rt_admit','ep_rt_live_miss',
                       'ep_rt_sustain_reject','ep_rt_declined_not_missed')
    AND (created_at AT TIME ZONE 'America/New_York')::date BETWEEN '2026-09-08' AND '2026-10-09'
), al AS (
  SELECT ticker, alert_date AS d FROM mi_ep_alerts WHERE alert_date BETWEEN '2026-09-08' AND '2026-10-09'
), pairs AS (SELECT * FROM ev UNION SELECT * FROM al)
SELECT s.scan_date, s.ticker,
       to_char(s.scan_time_et AT TIME ZONE 'America/New_York', 'HH24:MI:SS') AS scan_et,
       s.gap_pct, s.gap_pct_rt, s.gap_pct_delayed, s.prev_close, s.price_source, s.filter_reason,
       s.reject_stage, s.ep_score, s.score_tier, s.catalyst_quality, s.minutes_since_open,
       s.extension_pct, s.quality_adv_dollar, s.atr_pct, s.market_cap, s.days_since_prior_alert
FROM mi_ep_scan_log s JOIN pairs p ON p.ticker = s.ticker AND p.d = s.scan_date
ORDER BY s.scan_date, s.ticker, s.scan_time_et;

\echo === COVERAGE ===
WITH ev AS (
  SELECT DISTINCT detail::json->>'ticker' AS ticker,
         (created_at AT TIME ZONE 'America/New_York')::date AS d
  FROM mi_audit_log
  WHERE event_type IN ('ep_rt_universe_catch','ep_rt_floor_flip_up','ep_rt_admit','ep_rt_live_miss')
    AND (created_at AT TIME ZONE 'America/New_York')::date BETWEEN '2026-09-08' AND '2026-10-09'
), al AS (
  SELECT ticker, alert_date AS d FROM mi_ep_alerts WHERE alert_date BETWEEN '2026-09-08' AND '2026-10-09'
), tr AS (
  SELECT ticker, alert_date AS d FROM mi_live_trades WHERE alert_date BETWEEN '2026-09-08' AND '2026-10-09'
), pairs AS (SELECT * FROM ev UNION SELECT * FROM al UNION SELECT * FROM tr)
SELECT p.ticker, p.d,
       count(b.bar_time) FILTER (WHERE (b.bar_time AT TIME ZONE 'America/New_York')::time >= '09:30'
                                   AND (b.bar_time AT TIME ZONE 'America/New_York')::time < '09:45') AS orb_bars,
       count(b.bar_time) FILTER (WHERE (b.bar_time AT TIME ZONE 'America/New_York')::time >= '09:30'
                                   AND (b.bar_time AT TIME ZONE 'America/New_York')::time < '16:00') AS rth_bars,
       bool_or((b.bar_time AT TIME ZONE 'America/New_York')::time = '09:30') AS has_930
FROM pairs p
LEFT JOIN mi_intraday_bars b ON b.ticker = p.ticker
  AND (b.bar_time AT TIME ZONE 'America/New_York')::date = p.d
GROUP BY p.ticker, p.d ORDER BY p.d, p.ticker;

\echo === REGIME ===
SELECT regime_date, regime, ep_threshold FROM mi_market_regime
WHERE regime_date BETWEEN '2026-09-01' AND '2026-10-09' ORDER BY regime_date;

\echo === DAILYRANGE ===
SELECT min(trade_date) AS first_d, max(trade_date) AS last_d, count(DISTINCT trade_date) AS n_days
FROM mi_daily_closes WHERE trade_date BETWEEN '2026-09-01' AND '2026-10-10';

\echo === BASELINE_EVCOUNT ===
SELECT event_type, count(*) AS n
FROM mi_audit_log
WHERE event_type IN ('ep_rt_universe_catch','ep_rt_floor_flip_up','ep_rt_admit','ep_rt_live_miss')
  AND (created_at AT TIME ZONE 'America/New_York')::date BETWEEN '2026-07-21' AND '2026-08-10'
GROUP BY 1 ORDER BY 1;
