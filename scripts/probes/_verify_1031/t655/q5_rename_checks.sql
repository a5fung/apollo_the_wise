SET default_transaction_read_only = on;
\echo == merged rows since 10-17: description_stored value and lineage flag, by ET date
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS et_date,
       substring(detail from 'description_stored=(True|False)') AS desc_stored,
       substring(detail from 'lineage_staged=([A-Za-z0-9_]+)') AS lineage,
       (detail LIKE '%description quality check:%') AS has_quality_note
FROM mi_audit_log WHERE event_type = 'theme_thesis_merged' AND created_at >= '2026-10-17' ORDER BY created_at;
\echo == WOULD-FAIL-IF part 2: renamed theme whose stored description equals the old name's last description (description_stored=True but unchanged)
SELECT r.new_name, r.theme_date,
       (SELECT description FROM mi_themes t WHERE t.name = r.old_name AND t.theme_date < r.theme_date ORDER BY theme_date DESC LIMIT 1) = 
       (SELECT description FROM mi_themes t WHERE t.name = r.new_name AND t.theme_date >= r.theme_date ORDER BY theme_date LIMIT 1) AS same_desc
FROM mi_theme_renames r WHERE r.mechanism = 'arm_b_merge_rename' ORDER BY r.renamed_at;
