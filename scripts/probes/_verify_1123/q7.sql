SET default_transaction_read_only = on;
\echo == 728 stop events today
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') t, event_type, left(summary,180), left(detail,200) FROM mi_audit_log WHERE created_at >= '2026-11-23 15:30-05' AND (event_type IN ('stop_updated','stop_update_retry_triggered','stop_update_failed','stop_breach_market_sale','stop_breach_sale_deferred_extended_hours','stop_price_replace_unconfirmed','naked_position_detected') OR event_type LIKE 'stop_%') ORDER BY created_at;
\echo == 728 mechanism count today all day
SELECT event_type, detail LIKE '%price_only_replace%' por, count(*) FROM mi_audit_log WHERE created_at >= '2026-11-23 00:00-05' AND event_type IN ('stop_updated','stop_update_retry_triggered','stop_update_failed','stop_breach_market_sale') GROUP BY 1,2 ORDER BY 1;
\echo == 727 calendar
SELECT event_date, event_type, to_char(release_et AT TIME ZONE 'America/New_York','MM-DD HH24:MI') rel, source, to_char(refreshed_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') refr FROM mi_cot_calendar WHERE event_type IN ('AU_CPI','PCE','USDA_EXPORTS','OPEC') ORDER BY event_date LIMIT 20;
\echo == 695 KOD 404 arms
SELECT arm, outcome, sessions_walked, mark_r, realized_r FROM mi_live_fill_counterfactuals WHERE trade_id=404 ORDER BY arm;
SELECT count(*) total, count(mark_r) with_mark FROM mi_live_fill_counterfactuals;
\echo == 717 breakout partial / stop-to-fill since 11-18
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') t, event_type, left(summary,180), left(detail,250) FROM mi_audit_log WHERE created_at >= '2026-11-18 23:00-05' AND event_type IN ('breakout_pp_stop_to_fill_after_third','profit_trigger_resting','profit_trigger_failed') ORDER BY created_at;
