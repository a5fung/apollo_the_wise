SET default_transaction_read_only = on;
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') t, event_type, left(summary,140) FROM mi_audit_log WHERE created_at>='2026-11-16' AND event_type IN ('breakout_pp_stop_to_fill_after_third','profit_trigger_resting','profit_trigger_failed','breakout_pp_exit','breakout_pp_profit_trigger','naked_position_detected') ORDER BY created_at;
SELECT strategy_id, phase, enabled FROM mi_strategies WHERE strategy_id ILIKE 'breakout%';
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) FROM mi_audit_log WHERE event_type ILIKE 'breakout_pp%' AND created_at>='2026-11-16' GROUP BY 1,2 ORDER BY 1;
