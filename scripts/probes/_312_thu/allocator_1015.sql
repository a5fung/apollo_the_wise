-- #312 Thu 10-15: today's 09:28 allocator row and any EP alerts (read-only)
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, left(detail::text, 600) AS detail
  FROM mi_audit_log WHERE created_at >= '2026-10-15 12:00+00' AND event_type ILIKE 'unified_allocat%' ORDER BY id;
SELECT count(*) AS ep_alerts_today FROM mi_ep_alerts WHERE alert_date = DATE '2026-10-15';
