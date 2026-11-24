SET default_transaction_read_only = on;
SELECT row_kind, status, count(*), min(event_date), max(event_date) FROM mi_parabolic_short_shadow GROUP BY 1,2 ORDER BY 1,2;
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, left(detail::text,140) FROM mi_audit_log WHERE event_type='parabolic_short_shadow_run' AND created_at>='2026-11-19' ORDER BY created_at;
SELECT strategy_id, phase, enabled FROM mi_strategies WHERE strategy_id ILIKE '%parab%' OR strategy_id ILIKE '%wick%';
