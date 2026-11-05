SET default_transaction_read_only = on;
SELECT event_type, created_at AT TIME ZONE 'America/New_York' et, left(summary,120) FROM mi_audit_log
WHERE created_at > TIMESTAMPTZ '2026-11-05 10:00+00' AND event_type IN ('ep_rt_floor_flip_up','magna53_open_floor_checked')
  AND (summary ILIKE 'APPN%' OR summary ILIKE 'CHYM%' OR summary ILIKE 'U %' OR summary ILIKE '%ORB APPN%' OR summary ILIKE '%ORB U %') ORDER BY id;
SELECT count(*) AS checked_rows_today, count(DISTINCT left(summary, 12)) FROM mi_audit_log WHERE created_at > TIMESTAMPTZ '2026-11-05 10:00+00' AND event_type='magna53_open_floor_checked';
