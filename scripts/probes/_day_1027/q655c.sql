SET default_transaction_read_only = on;
WITH rem AS (SELECT ticker, theme_name, removed_at FROM mi_validation_cooldowns WHERE removed_at >= '2026-10-26 16:30-04' AND removed_at < '2026-10-26 20:00-04'),
mv AS (SELECT created_at, event_type, detail::jsonb->>'ticker' tk, coalesce(detail::jsonb->>'to', detail::jsonb->>'target', detail::jsonb->>'theme') tgt
       FROM mi_audit_log WHERE created_at >= '2026-10-12' AND event_type IN ('theme_member_rehomed','theme_sector_cap_absorbed','theme_fail_only_fold','theme_member_moved'))
SELECT r.ticker, r.theme_name, r.removed_at AT TIME ZONE 'America/New_York', m.event_type, m.created_at AT TIME ZONE 'America/New_York', m.tgt
FROM rem r LEFT JOIN mv m ON m.tk = r.ticker ORDER BY r.ticker;
SELECT ticker, theme_name, removed_at FROM mi_validation_cooldowns WHERE ticker='RH' AND removed_at >= '2026-10-20';
SELECT event_type, count(*) FROM mi_audit_log WHERE created_at >= '2026-10-12' AND event_type IN ('theme_member_rehomed','theme_sector_cap_absorbed','theme_fail_only_fold','theme_member_moved') GROUP BY 1;
