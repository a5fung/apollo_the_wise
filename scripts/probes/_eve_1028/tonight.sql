-- Wed 2026-10-28 evening reads, READ-ONLY. #491 night 3; a first look at the #482 hour lane's first run (the verify is Thu).
SET default_transaction_read_only = on;
\echo '== B. #491 night 3: bounces since the U2 deploy (expect 0), skip rows, failures, rehomes'
SELECT m.detail::jsonb->>'ticker' tk, m.detail::jsonb->>'from' frm, t.theme_date FROM mi_audit_log m JOIN mi_themes t ON t.source='shadow_promoted'
 AND t.name = m.detail::jsonb->>'from' AND (m.detail::jsonb->>'ticker') = ANY(t.tickers)
 AND t.theme_date > (m.created_at AT TIME ZONE 'America/New_York')::date AND t.theme_date <= (m.created_at AT TIME ZONE 'America/New_York')::date + 14
WHERE m.event_type='theme_member_rehomed' AND m.created_at >= '2026-10-24';
SELECT created_at AT TIME ZONE 'America/New_York' et, left(detail,260) FROM mi_audit_log WHERE event_type='promote_member_skipped' AND created_at >= '2026-10-28 12:00-04' ORDER BY id;
SELECT event_type, count(*) FROM mi_audit_log WHERE event_type IN ('shadow_themes_promoted','shadow_promotion_failed','theme_member_rehomed','theme_rehome_pass_ran') AND created_at >= '2026-10-28 12:00-04' GROUP BY 1;
\echo '== H. #482 hour lane: rows by bar size and status written today'
SELECT bar_size_minutes, status, count(*) FROM mi_orb_shadow_trades WHERE created_at >= '2026-10-28 12:00-04' GROUP BY 1,2 ORDER BY 1,2;
SELECT bar_size_minutes, count(*) FROM mi_orb_shadow_trades GROUP BY 1 ORDER BY 1;
SELECT created_at AT TIME ZONE 'America/New_York' et, event_type, left(coalesce(summary,''),200) FROM mi_audit_log
 WHERE created_at >= '2026-10-28 16:40-04' AND (event_type ILIKE '%shadow_orb%' OR event_type ILIKE '%hour_lane%' OR event_type ILIKE '%shadow_hour%') ORDER BY id LIMIT 20;
