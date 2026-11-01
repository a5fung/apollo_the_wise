SET default_transaction_read_only = on;
\echo == 314 nightly runs since 10-24
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, COUNT(*), MAX(LEFT(summary,160)) FROM mi_audit_log WHERE event_type = 'parabolic_short_shadow_run' AND created_at >= '2026-10-24' GROUP BY 1 ORDER BY 1;
\echo == 314 errors / disabled since 10-24
SELECT event_type, COUNT(*) FROM mi_audit_log WHERE event_type ILIKE 'parabolic_short%' AND event_type <> 'parabolic_short_shadow_run' AND created_at >= '2026-10-24' GROUP BY 1;
\echo == 314 candidates since 10-24 by stage
SELECT scan_date, stage, COUNT(*) FROM mi_parabolic_candidates WHERE scan_date >= '2026-10-24' GROUP BY 1,2 ORDER BY 1,2;
\echo == 314 any climax ever since 10-17, and arm rows
SELECT COUNT(*) FILTER (WHERE stage ILIKE '%climax%') AS climax FROM mi_parabolic_candidates WHERE scan_date >= '2026-10-17';
SELECT COUNT(*) AS arm_rows FROM mi_parabolic_short_shadow;
\echo == 482 counterfactual population
SELECT COUNT(*) AS rows, COUNT(DISTINCT trade_id) AS trades, COUNT(DISTINCT arm) AS arms, MIN(fill_date), MAX(fill_date) FROM mi_live_fill_counterfactuals;
