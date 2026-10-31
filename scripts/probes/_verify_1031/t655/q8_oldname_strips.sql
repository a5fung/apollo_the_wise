SET default_transaction_read_only = on;
\echo == removal/strip rows on a renaming night that name the winner's OLD name, inside the 17:00-17:20 ET engine window
SELECT r.old_name, a.event_type, a.created_at AT TIME ZONE 'America/New_York' AS et
FROM mi_theme_renames r JOIN mi_audit_log a
  ON (a.created_at AT TIME ZONE 'America/New_York')::date = r.theme_date
 AND (a.created_at AT TIME ZONE 'America/New_York')::time BETWEEN '17:00' AND '17:20'
 AND (a.event_type ILIKE '%strip%' OR a.event_type ILIKE '%remov%' OR a.event_type ILIKE '%validat%')
 AND position(r.old_name in a.detail) > 0
WHERE r.mechanism = 'arm_b_merge_rename' ORDER BY a.created_at;
\echo == same, naming the NEW (merged) name — the expected side
SELECT count(*) FROM mi_theme_renames r JOIN mi_audit_log a
  ON (a.created_at AT TIME ZONE 'America/New_York')::date = r.theme_date
 AND (a.created_at AT TIME ZONE 'America/New_York')::time BETWEEN '17:00' AND '17:20'
 AND (a.event_type ILIKE '%strip%' OR a.event_type ILIKE '%remov%' OR a.event_type ILIKE '%validat%')
 AND position(r.new_name in a.detail) > 0
WHERE r.mechanism = 'arm_b_merge_rename';
