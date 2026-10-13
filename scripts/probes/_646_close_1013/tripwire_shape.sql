-- shape of the evening coverage rows, for the #646/#649 first-fire tripwire predicate (read-only)
SELECT event_type, created_at AT TIME ZONE 'America/New_York' AS et, left(detail, 400) AS detail
  FROM mi_audit_log
 WHERE event_type IN ('coverage_checked_post_close','coverage_checked_late','coverage_verified_evening')
 ORDER BY id DESC LIMIT 3;
SELECT count(*) AS would_count_now FROM mi_audit_log
 WHERE created_at >= DATE '2026-09-15'
   AND (event_type LIKE 'coverage_%repair_attempted'
        OR (event_type IN ('coverage_checked_post_close','coverage_checked_late','coverage_verified_evening')
            AND (coalesce(jsonb_array_length(detail::jsonb->'gaps'),0) > 0
                 OR coalesce(jsonb_array_length(detail::jsonb->'check_failed'),0) > 0)));
