-- Thu 2026-10-29 evening reads, READ-ONLY. #491 night 4; #482 hour-lane check 6 (Thu 16:50 steps a Wed 60 row).
SET default_transaction_read_only = on;
\echo '== B. #491 night 4: bounces since the U2 deploy (expect 0), skip rows, failures, rehomes'
SELECT m.detail::jsonb->>'ticker' tk, m.detail::jsonb->>'from' frm, t.theme_date FROM mi_audit_log m JOIN mi_themes t ON t.source='shadow_promoted'
 AND t.name = m.detail::jsonb->>'from' AND (m.detail::jsonb->>'ticker') = ANY(t.tickers)
 AND t.theme_date > (m.created_at AT TIME ZONE 'America/New_York')::date AND t.theme_date <= (m.created_at AT TIME ZONE 'America/New_York')::date + 14
WHERE m.event_type='theme_member_rehomed' AND m.created_at >= '2026-10-24';
SELECT created_at AT TIME ZONE 'America/New_York' et, left(detail,260) FROM mi_audit_log WHERE event_type='promote_member_skipped' AND created_at >= '2026-10-29 12:00-04' ORDER BY id;
SELECT event_type, count(*) FROM mi_audit_log WHERE event_type IN ('shadow_themes_promoted','shadow_promotion_failed','theme_member_rehomed','theme_rehome_pass_ran') AND created_at >= '2026-10-29 12:00-04' GROUP BY 1;
\echo '== H. #482 check 6: the 60 rows after Thu 16:50 (each open row gains one close; VRT 10-28 should now hold 1)'
SELECT id, ticker, alert_date, status, CASE WHEN jsonb_typeof(running_closes)='array' THEN jsonb_array_length(running_closes) ELSE -1 END n_closes, hold_days, total_pnl
FROM mi_orb_shadow_trades WHERE bar_size_minutes = 60 AND status IN ('open','closed') ORDER BY alert_date, ticker;
SELECT created_at AT TIME ZONE 'America/New_York' et, event_type, left(coalesce(summary,''),220) FROM mi_audit_log
 WHERE created_at >= '2026-10-29 16:40-04' AND (event_type ILIKE '%shadow_orb%' OR event_type ILIKE '%hour%') ORDER BY id LIMIT 20;
SELECT job_id, status, started_at AT TIME ZONE 'America/New_York' et FROM mi_job_runs WHERE job_id ILIKE '%shadow_orb%' AND started_at > '2026-10-29 09:00-04' ORDER BY started_at;
