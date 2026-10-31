SET default_transaction_read_only = on;
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary,200) AS summary
FROM mi_audit_log
WHERE created_at >= '2026-10-23 16:00:00+00'
  AND (created_at AT TIME ZONE 'America/New_York')::time BETWEEN '09:25' AND '10:10'
  AND extract(dow from created_at AT TIME ZONE 'America/New_York') BETWEEN 1 AND 5
  AND event_type IN ('orb_triggered','orb_filtered','orb_duplicate','orb_skipped','orb_skip','orb_pipeline_crash','orb_entry','orb_window_out','entry_skipped','live_entry_skipped')
ORDER BY created_at;
SELECT event_type, count(*) FROM mi_audit_log WHERE created_at >= '2026-10-23 16:00:00+00' AND event_type ILIKE 'orb%' OR (created_at >= '2026-10-23 16:00:00+00' AND event_type ILIKE '%skip%') GROUP BY 1 ORDER BY 1;
