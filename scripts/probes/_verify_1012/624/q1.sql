\echo === strategy row
SELECT strategy_id, phase, enabled, max_concurrent_positions, sizing_multiplier FROM mi_strategies WHERE strategy_id IN ('magna53_smallcap','magna53_ep');
\echo === toggles (lane + paper exit)
SELECT safeguard, account_mode, state, to_char(updated_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') AS upd FROM mi_safeguard_state WHERE safeguard IN ('lowcap_paper_lane','breakeven_at_broker','entry_ask_aware','profit_take_oco','profit_take_resting_limit') ORDER BY 1,2;
\echo === lane alerts all rows
SELECT id, ticker, alert_date, strategy_id, to_char(first_graded_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS first_graded, score_tier, ep_score, reject_stage, reject_reason, catalyst_quality, round(gap_pct::numeric,1) gap, round(rel_volume::numeric,1) rv, round(market_cap/1e6) mcap_m, judge_tier, lane_rule_version FROM mi_lowcap_paper_lane_alerts ORDER BY id;
\echo === lane replays count
SELECT count(*) FROM mi_lowcap_paper_lane_replays;
\echo === audit events lowcap since 10-09
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS t, event_type, left(summary,200) FROM mi_audit_log WHERE (event_type ILIKE '%lowcap%' OR summary ILIKE '%lowcap_paper%' OR summary ILIKE '%magna53_smallcap%') AND created_at > now() - interval '4 days' ORDER BY created_at;
\echo === lane-related trades
SELECT id, ticker, signal_type, account_mode, status, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') AS created FROM mi_live_trades WHERE signal_type='magna53_smallcap' ORDER BY id DESC LIMIT 20;
\echo === overlap lane tickers today in mi_ep_alerts
SELECT a.ticker, a.alert_date, a.score_tier AS live_tier FROM mi_ep_alerts a JOIN mi_lowcap_paper_lane_alerts l ON l.ticker=a.ticker AND l.alert_date=a.alert_date;
\echo === live ep alerts today
SELECT ticker, score_tier, ep_score, to_char(detected_at AT TIME ZONE 'America/New_York','HH24:MI:SS') t FROM mi_ep_alerts WHERE alert_date = (now() AT TIME ZONE 'America/New_York')::date ORDER BY detected_at;
