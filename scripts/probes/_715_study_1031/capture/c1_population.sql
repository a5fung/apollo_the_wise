-- #715 (2026-10-31) — capture 1 of 2: the POPULATION, its stored fates, and every per-row input the
-- stage-2 replay needs except the bars (those are c2_bars.sql). READ-ONLY (SELECT only), $0.
-- Run ONCE from the laptop, read the .out many times, never re-run to re-read:
--
--   ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|'" \
--     < scripts/probes/_715_study_1031/capture/c1_population.sql \
--     > scripts/probes/_715_study_1031/capture/c1_population.out
--
-- POPULATION — every section's POP CTE is VERBATIM scripts/probes/_regn_1030/q3_flipups.sql:
--   the distinct (ET date, ticker) of `ep_rt_floor_flip_up` audit rows since 2026-08-02 (ticker =
--   the summary's leading token), joined to a HIGH mi_ep_alerts row on the same date.
--   q3_flipups.out (2026-10-30) read 871 flip-ups / 51 became HIGH / 3 chase-cap skips / 10 filled.
--   POPCOUNT below re-runs q3's own count statement unchanged; stage 2 asserts 51 and names any delta.
-- Text columns are sanitised for the pipe format: newline/tab -> space, '|' -> '¦'.
-- Every timestamp is rendered in ET (AT TIME ZONE 'America/New_York'); dates are ET dates.
SET default_transaction_read_only = on;
\set ON_ERROR_STOP off
\pset footer off

\echo === RUN ===
SELECT to_char(now() AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI:SS') AS run_et,
       current_setting('TimeZone') AS session_tz,
       current_setting('client_encoding') AS client_encoding,   -- the '≥' floor parse in POP needs UTF8
       current_setting('server_encoding') AS server_encoding,
       current_setting('default_transaction_read_only') AS read_only,
       version() AS pg;

\echo === TOGGLES ===
SELECT safeguard, account_mode, state,
       to_char(last_transition_at AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI:SS') AS since_et,
       to_char(updated_at AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI:SS') AS updated_et
FROM mi_safeguard_state
WHERE safeguard LIKE 'ep_rt%'
   OR safeguard IN ('magna53_depth_exit', 'entry_ask_aware', 'profit_take_resting_limit',
                    'breakeven_at_broker', 'ep_score_separation', 'regime_sizing',
                    'mna_headline_unanswered_blocks')
ORDER BY safeguard, account_mode;

\echo === STRATEGIES ===
SELECT strategy_id, name, family, phase, enabled, live_real_enabled, signal_type,
       position_size_multiplier, max_concurrent_positions, profit_trigger_r, breakeven_arm_r,
       to_char(updated_at AT TIME ZONE 'America/New_York', 'YYYY-MM-DD') AS updated_et
FROM mi_strategies ORDER BY strategy_id;

\echo === POPCOUNT ===
-- q3_flipups.sql's count statement, VERBATIM (expected 51 became_high / 3 / 10 as of 10-30).
WITH f AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d, substring(summary from '^([A-Z.]{1,6}) ') AS t
  FROM mi_audit_log WHERE event_type = 'ep_rt_floor_flip_up' AND created_at >= '2026-08-02'
)
SELECT count(*) AS flip_ups,
       count(a.ticker) AS became_high,
       count(lt.id) FILTER (WHERE lt.skip_reason ILIKE 'setup:chase_cap%') AS chase_cap_skips,
       count(lt.id) FILTER (WHERE lt.status IN ('filled','closed','partial')) AS filled
FROM f
LEFT JOIN (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts WHERE score_tier='HIGH') a ON a.ticker = f.t AND a.alert_date = f.d
LEFT JOIN mi_live_trades lt ON lt.ticker = f.t AND lt.alert_date = f.d AND lt.signal_type='magna53';

\echo === POP ===
-- One row per ticker-day of the population: the FIRST flip-up row's fields (the floor is parsed from
-- the summary — '≥9' since 08-19, '≥10' before — never hard-coded), the detector's prev close
-- (get_prev_close's exact rule: latest mi_daily_closes row strictly before the day, close > 0), the
-- official daily row ON the day (open_price = the opening print), and the stored 09:30 ET minute bar
-- (= the live ORB bar; orb_bar_fetched in EVENTS cross-checks it).
WITH f AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d, substring(summary from '^([A-Z.]{1,6}) ') AS t
  FROM mi_audit_log WHERE event_type = 'ep_rt_floor_flip_up' AND created_at >= '2026-08-02'
), pop AS (
  SELECT f.d, f.t FROM f
  JOIN (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts WHERE score_tier='HIGH') a ON a.ticker = f.t AND a.alert_date = f.d
), first_flip AS (
  SELECT DISTINCT ON (p.d, p.t) p.d, p.t, l.id AS flip_audit_id, l.created_at, l.summary, l.detail
  FROM pop p
  JOIN mi_audit_log l ON l.event_type = 'ep_rt_floor_flip_up' AND l.created_at >= '2026-08-02'
   AND (l.created_at AT TIME ZONE 'America/New_York')::date = p.d
   AND substring(l.summary from '^([A-Z.]{1,6}) ') = p.t
  ORDER BY p.d, p.t, l.created_at, l.id
)
SELECT ff.d, ff.t,
       ff.flip_audit_id,
       to_char(ff.created_at AT TIME ZONE 'America/New_York', 'HH24:MI:SS.MS') AS flip_et,
       (CASE WHEN left(ff.detail, 1) = '{' THEN ff.detail::json->>'tick_et'       END) AS tick_et,
       (CASE WHEN left(ff.detail, 1) = '{' THEN ff.detail::json->>'rt_gap'        END) AS rt_gap,
       (CASE WHEN left(ff.detail, 1) = '{' THEN ff.detail::json->>'delayed_gap'   END) AS delayed_gap,
       (CASE WHEN left(ff.detail, 1) = '{' THEN ff.detail::json->>'authoritative' END) AS authoritative,
       substring(ff.summary from '≥([0-9]+(?:\.[0-9]+)?)') AS floor_pct_from_summary,
       replace(replace(replace(ff.summary, E'\n', ' '), E'\t', ' '), '|', '¦') AS flip_summary,
       pc.trade_date AS prev_close_date, pc.close AS prev_close,
       d0.open_price AS day0_open, d0.high_price AS day0_high, d0.low_price AS day0_low,
       d0.close AS day0_close, d0.volume AS day0_volume,
       b930.open AS orb_open, b930.high AS orb_high, b930.low AS orb_low, b930.close AS orb_close,
       b930.volume AS orb_volume
FROM first_flip ff
LEFT JOIN LATERAL (
  SELECT trade_date, close FROM mi_daily_closes
  WHERE ticker = ff.t AND trade_date < ff.d AND close > 0
  ORDER BY trade_date DESC LIMIT 1
) pc ON true
LEFT JOIN mi_daily_closes d0 ON d0.ticker = ff.t AND d0.trade_date = ff.d
LEFT JOIN mi_intraday_bars b930 ON b930.ticker = ff.t
  AND b930.bar_time = ((ff.d::text || ' 09:30')::timestamp AT TIME ZONE 'America/New_York')
ORDER BY ff.d, ff.t;

\echo === EVENTS ===
-- Every real-time admission event and every ORB / entry event for the population's ticker-days.
-- ep_rt_* rows are matched on detail->>'ticker' (c1_scope.sql's form); the ORB/entry rows carry the
-- ticker in free text, matched as a whole token on the same ET date. ⚠ Free-text matching can
-- over-include (a theme summary naming the ticker) — stage 2 keys on event_type, never on presence.
WITH f AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d, substring(summary from '^([A-Z.]{1,6}) ') AS t
  FROM mi_audit_log WHERE event_type = 'ep_rt_floor_flip_up' AND created_at >= '2026-08-02'
), pop AS (
  SELECT f.d, f.t FROM f
  JOIN (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts WHERE score_tier='HIGH') a ON a.ticker = f.t AND a.alert_date = f.d
)
SELECT p.d, p.t, l.id,
       to_char(l.created_at AT TIME ZONE 'America/New_York', 'HH24:MI:SS.MS') AS t_et,
       l.event_type,
       replace(replace(replace(l.summary, E'\n', ' '), E'\t', ' '), '|', '¦') AS summary,
       replace(replace(replace(left(coalesce(l.detail, ''), 600), E'\n', ' '), E'\t', ' '), '|', '¦') AS detail
FROM pop p
JOIN mi_audit_log l
  ON l.created_at >= ((p.d::text || ' 04:00')::timestamp AT TIME ZONE 'America/New_York')
 AND l.created_at <  ((p.d::text || ' 20:00')::timestamp AT TIME ZONE 'America/New_York')
 AND (
       (l.event_type LIKE 'ep_rt_%' AND l.event_type <> 'ep_rt_universe_coverage'
        AND ((CASE WHEN left(l.detail, 1) = '{' THEN l.detail::json->>'ticker' END) = p.t
             OR substring(l.summary from '^([A-Z.]{1,6}) ') = p.t))
    OR ((   l.event_type LIKE 'orb_%'      OR l.event_type LIKE 'entry_%'   OR l.event_type LIKE 'window%'
         OR l.event_type LIKE 'order_%'    OR l.event_type LIKE 'fill%'     OR l.event_type LIKE 'stop_%'
         OR l.event_type LIKE 'trade_%'    OR l.event_type LIKE 'position_%' OR l.event_type LIKE 'partial_%'
         OR l.event_type LIKE 'breakeven%' OR l.event_type LIKE 'profit_take%' OR l.event_type LIKE 'depth_%'
         OR l.event_type LIKE 'bar_stream%'
         OR l.event_type IN ('ep_alert', 'ep_grade_decision', 'conviction_floor_eligible',
                             'exposure_family_checked'))
        -- prefixes, not a hand-typed list: several ORB skips are written through `_skip(audit_event=...)`
        -- and a literal grep under-counts them; the day range + the ticker token bound the rows.
        AND l.summary ~ ('(^|[^A-Z.])' || replace(p.t, '.', '\.') || '([^A-Z.]|$)'))
     )
ORDER BY p.d, p.t, l.created_at, l.id;

\echo === ALERTS ===
WITH f AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d, substring(summary from '^([A-Z.]{1,6}) ') AS t
  FROM mi_audit_log WHERE event_type = 'ep_rt_floor_flip_up' AND created_at >= '2026-08-02'
), pop AS (
  SELECT f.d, f.t FROM f
  JOIN (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts WHERE score_tier='HIGH') a ON a.ticker = f.t AND a.alert_date = f.d
)
SELECT a.id, a.ticker, a.alert_date, a.gap_pct, a.rel_volume, a.ep_score, a.score_tier,
       a.catalyst_quality, a.judge_tier, a.judge_grade, a.grade_engine_authority, a.rubric_version,
       a.setup_class, a.baseline_floor_tier, coalesce(a.source, 'live') AS source, a.in_active_theme,
       a.pm_rvol, a.vol_percentile, a.confidence_multiplier,
       to_char(a.detected_at AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI:SS') AS detected_et,
       to_char(a.created_at  AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI:SS') AS created_et,
       replace(replace(replace(left(coalesce(a.catalyst, ''), 200), E'\n', ' '), E'\t', ' '), '|', '¦') AS catalyst_200
FROM pop p JOIN mi_ep_alerts a ON a.ticker = p.t AND a.alert_date = p.d
ORDER BY a.alert_date, a.ticker, a.id;

\echo === SCANLOG ===
-- every scan tick stored for the ticker-day: the gap pair the floor decided on, the prev close the
-- scan used (cross-check against POP.prev_close), the price it read, the stage it was cut at.
WITH f AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d, substring(summary from '^([A-Z.]{1,6}) ') AS t
  FROM mi_audit_log WHERE event_type = 'ep_rt_floor_flip_up' AND created_at >= '2026-08-02'
), pop AS (
  SELECT f.d, f.t FROM f
  JOIN (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts WHERE score_tier='HIGH') a ON a.ticker = f.t AND a.alert_date = f.d
)
SELECT s.scan_date, s.ticker,
       to_char(s.scan_time_et AT TIME ZONE 'America/New_York', 'HH24:MI:SS') AS scan_et,
       s.gap_pct, s.gap_pct_rt, s.gap_pct_delayed, s.prev_close, s.prev_close_alpaca,
       s.current_price, s.price_source, s.rt_price_age_s, s.minutes_since_open,
       replace(replace(coalesce(s.filter_reason, ''), E'\n', ' '), '|', '¦') AS filter_reason,
       s.reject_stage, s.ep_score, s.score_tier, s.catalyst_quality,
       s.extension_pct, s.quality_adv_dollar, s.atr_pct, s.market_cap, s.ep_bar, s.rank_by_gap
FROM pop p JOIN mi_ep_scan_log s ON s.ticker = p.t AND s.scan_date = p.d
ORDER BY s.scan_date, s.ticker, s.scan_time_et, s.id;

\echo === TRADES ===
-- every mi_live_trades row for the ticker-days — all modes, all statuses, all signal types
-- (stage 2 filters signal_type = 'magna53' and entry_attempt = 1 for the calibration; the rest is
-- context). hard_stop = the PLACED stop; stop_price = the live, possibly trailed stop.
WITH f AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d, substring(summary from '^([A-Z.]{1,6}) ') AS t
  FROM mi_audit_log WHERE event_type = 'ep_rt_floor_flip_up' AND created_at >= '2026-08-02'
), pop AS (
  SELECT f.d, f.t FROM f
  JOIN (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts WHERE score_tier='HIGH') a ON a.ticker = f.t AND a.alert_date = f.d
)
SELECT lt.id, lt.ticker, lt.alert_date, lt.signal_type, lt.account_mode, lt.status, lt.entry_attempt,
       replace(replace(coalesce(lt.skip_reason, ''), E'\n', ' '), '|', '¦') AS skip_reason,
       lt.orb_high, lt.orb_low, lt.atr_14, lt.entry_price, lt.entry_shares, lt.stop_price, lt.hard_stop,
       lt.risk_dollars, lt.risk_dollars_actual, lt.exit_rule, lt.depth_sell_pending_on,
       lt.remaining_shares, lt.partial_taken, lt.breakeven_active, lt.total_pnl, lt.pnl_attribution,
       lt.highest_price_seen, lt.lowest_price_seen, lt.regime, lt.gap_pct, lt.ep_score,
       to_char(lt.proposed_at  AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI:SS') AS proposed_et,
       to_char(lt.confirmed_at AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI:SS') AS confirmed_et,
       to_char(lt.filled_at    AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI:SS') AS filled_et,
       to_char(lt.closed_at    AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI:SS') AS closed_et,
       replace(replace(replace(coalesce(lt.exits::text, ''), E'\n', ' '), E'\t', ' '), '|', '¦') AS exits_json,
       replace(coalesce(lt.running_closes::text, ''), '|', '¦') AS running_closes_json
FROM pop p JOIN mi_live_trades lt ON lt.ticker = p.t AND lt.alert_date = p.d
ORDER BY lt.alert_date, lt.ticker, lt.account_mode, lt.id;

\echo === ORDERS ===
-- the broker orders behind those trade rows: a #500 limit-fallback entry carries limit_price =
-- latest × 1.002 at submit — the ONLY stored read of the live "latest trade" the proxy is
-- calibrated against (see PLAN.md §2.2).
WITH f AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d, substring(summary from '^([A-Z.]{1,6}) ') AS t
  FROM mi_audit_log WHERE event_type = 'ep_rt_floor_flip_up' AND created_at >= '2026-08-02'
), pop AS (
  SELECT f.d, f.t FROM f
  JOIN (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts WHERE score_tier='HIGH') a ON a.ticker = f.t AND a.alert_date = f.d
)
SELECT o.id, o.trade_id, o.ticker, lt.alert_date, lt.account_mode, o.side, o.order_type, o.qty,
       o.stop_price, o.limit_price, o.status, o.filled_qty, o.filled_avg_price, o.purpose, o.exit_reason,
       to_char(o.submitted_at AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI:SS.MS') AS submitted_et,
       to_char(o.filled_at    AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI:SS.MS') AS filled_et,
       to_char(o.cancelled_at AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI:SS.MS') AS cancelled_et
FROM pop p
JOIN mi_live_trades lt ON lt.ticker = p.t AND lt.alert_date = p.d
JOIN mi_live_orders o ON o.trade_id = lt.id
ORDER BY lt.alert_date, lt.ticker, o.submitted_at, o.id;

\echo === SHADOW ===
-- the 5-minute shadow lane's row for the same alert (context; a different bar size, never pooled)
WITH f AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d, substring(summary from '^([A-Z.]{1,6}) ') AS t
  FROM mi_audit_log WHERE event_type = 'ep_rt_floor_flip_up' AND created_at >= '2026-08-02'
), pop AS (
  SELECT f.d, f.t FROM f
  JOIN (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts WHERE score_tier='HIGH') a ON a.ticker = f.t AND a.alert_date = f.d
)
SELECT s.id, s.ticker, s.alert_date, s.bar_size_minutes, s.signal_type, s.score_tier, s.shape_tag,
       s.orb_high, s.orb_low, s.atr_14, s.trigger_minute_et, s.entry_price, s.stop_price, s.hard_stop,
       s.status, replace(coalesce(s.skip_reason, ''), '|', '¦') AS skip_reason, s.total_pnl,
       s.quarantined, s.quarantine_reason,
       replace(coalesce(s.exits::text, ''), '|', '¦') AS exits_json
FROM pop p JOIN mi_orb_shadow_trades s ON s.ticker = p.t AND s.alert_date = p.d
ORDER BY s.alert_date, s.ticker, s.bar_size_minutes;

\echo === CF ===
-- the #482 recorder's rows for the population's fills: the live_replay arm on a depth-stamped fill
-- is THE bridge — stage 2's offline depth walk of the same fill must reproduce realized_r /
-- final_reason / exit_session before any option is read (PLAN.md §4 check 2).
WITH f AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d, substring(summary from '^([A-Z.]{1,6}) ') AS t
  FROM mi_audit_log WHERE event_type = 'ep_rt_floor_flip_up' AND created_at >= '2026-08-02'
), pop AS (
  SELECT f.d, f.t FROM f
  JOIN (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts WHERE score_tier='HIGH') a ON a.ticker = f.t AND a.alert_date = f.d
)
SELECT c.id, c.trade_id, c.ticker, c.account_mode, c.signal_type, c.entry_attempt, c.alert_date, c.fill_day,
       c.arm, c.arm_kind, c.stop_rule, c.harvest_rule, c.trail_rule, c.entry_rule,
       c.entry_price, c.orb_high, c.orb_low, c.live_stop, c.target_price, c.target_r, c.breakeven_arm_r,
       c.adr20_pct, c.adr20_n, c.adr_dollar, c.stop_price, c.risk_per_share,
       c.outcome, c.final_reason, c.realized_r, c.realized_pct, c.mark_r, c.partial_fired, c.gap_through,
       c.exit_session, c.sessions_walked, c.day0_bar_count,
       c.exit_era, replace(coalesce(c.exit_rules::text, ''), '|', '¦') AS exit_rules_json, c.admission_era,
       c.settle_version, c.settled_session,
       to_char(c.recorded_at AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI') AS recorded_et,
       replace(coalesce(c.exits::text, ''), '|', '¦') AS exits_json
FROM pop p JOIN mi_live_fill_counterfactuals c ON c.ticker = p.t AND c.alert_date = p.d
ORDER BY c.alert_date, c.ticker, c.trade_id, c.arm;

\echo === REGIME ===
WITH f AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d, substring(summary from '^([A-Z.]{1,6}) ') AS t
  FROM mi_audit_log WHERE event_type = 'ep_rt_floor_flip_up' AND created_at >= '2026-08-02'
), pop AS (
  SELECT f.d, f.t FROM f
  JOIN (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts WHERE score_tier='HIGH') a ON a.ticker = f.t AND a.alert_date = f.d
)
SELECT DISTINCT r.regime_date, r.regime, r.vix, r.qqq_ema_bullish, r.spy_vs_50ma
FROM pop p JOIN mi_market_regime r ON r.regime_date = p.d
ORDER BY r.regime_date;

\echo === SESSIONS ===
-- the trading calendar as the store knows it (a date with >= 500 daily rows is a session): the
-- forward-horizon counter and the "last settled session" come from here, never from a hand-typed date.
SELECT trade_date, count(*) AS n_rows
FROM mi_daily_closes
WHERE trade_date BETWEEN '2026-06-01' AND current_date
GROUP BY trade_date HAVING count(*) >= 500
ORDER BY trade_date;

\echo === COVERAGE ===
-- stored-minute coverage per ticker-day BEFORE any bar is read for an outcome: a ticker-day without
-- its 09:30 bar has no ORB; a gap inside 09:30-10:00 can hide the crossing bar or the fill.
WITH f AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d, substring(summary from '^([A-Z.]{1,6}) ') AS t
  FROM mi_audit_log WHERE event_type = 'ep_rt_floor_flip_up' AND created_at >= '2026-08-02'
), pop AS (
  SELECT f.d, f.t FROM f
  JOIN (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts WHERE score_tier='HIGH') a ON a.ticker = f.t AND a.alert_date = f.d
)
SELECT p.d, p.t,
       count(b.bar_time) AS rth_bars,
       count(b.bar_time) FILTER (WHERE b.bar_time < ((p.d::text || ' 09:45')::timestamp AT TIME ZONE 'America/New_York')) AS bars_0930_0945,
       count(b.bar_time) FILTER (WHERE b.bar_time < ((p.d::text || ' 10:00')::timestamp AT TIME ZONE 'America/New_York')) AS bars_0930_1000,
       bool_or(b.bar_time = ((p.d::text || ' 09:30')::timestamp AT TIME ZONE 'America/New_York')) AS has_0930,
       to_char(min(b.bar_time) AT TIME ZONE 'America/New_York', 'HH24:MI') AS first_bar_et,
       to_char(max(b.bar_time) AT TIME ZONE 'America/New_York', 'HH24:MI') AS last_bar_et
FROM pop p
LEFT JOIN mi_intraday_bars b ON b.ticker = p.t
  AND b.bar_time >= ((p.d::text || ' 09:30')::timestamp AT TIME ZONE 'America/New_York')
  AND b.bar_time <  ((p.d::text || ' 16:00')::timestamp AT TIME ZONE 'America/New_York')
GROUP BY p.d, p.t ORDER BY p.d, p.t;

\echo === CHECKS ===
-- the counts stage 2 asserts before reading anything else (51 / 10 / 3 are the 10-30 readings)
WITH f AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d, substring(summary from '^([A-Z.]{1,6}) ') AS t
  FROM mi_audit_log WHERE event_type = 'ep_rt_floor_flip_up' AND created_at >= '2026-08-02'
), pop AS (
  SELECT f.d, f.t FROM f
  JOIN (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts WHERE score_tier='HIGH') a ON a.ticker = f.t AND a.alert_date = f.d
)
SELECT (SELECT count(*) FROM pop) AS pop_rows,
       (SELECT count(DISTINCT t) FROM pop) AS pop_tickers,
       (SELECT min(d) FROM pop) AS first_day,
       (SELECT max(d) FROM pop) AS last_day,
       (SELECT count(*) FROM pop p WHERE EXISTS (SELECT 1 FROM mi_live_trades lt WHERE lt.ticker = p.t AND lt.alert_date = p.d AND lt.signal_type = 'magna53')) AS with_magna53_trade_row,
       (SELECT count(*) FROM pop p WHERE EXISTS (SELECT 1 FROM mi_live_trades lt WHERE lt.ticker = p.t AND lt.alert_date = p.d AND lt.signal_type = 'magna53' AND lt.status IN ('filled','closed','partial'))) AS filled,
       (SELECT count(*) FROM pop p WHERE EXISTS (SELECT 1 FROM mi_live_trades lt WHERE lt.ticker = p.t AND lt.alert_date = p.d AND lt.signal_type = 'magna53' AND lt.skip_reason ILIKE 'setup:chase_cap%')) AS chase_cap_skips,
       (SELECT count(*) FROM pop p WHERE EXISTS (SELECT 1 FROM mi_intraday_bars b WHERE b.ticker = p.t AND b.bar_time = ((p.d::text || ' 09:30')::timestamp AT TIME ZONE 'America/New_York'))) AS with_0930_bar,
       (SELECT count(*) FROM pop p WHERE EXISTS (SELECT 1 FROM mi_live_fill_counterfactuals c WHERE c.ticker = p.t AND c.alert_date = p.d)) AS with_cf_rows;
