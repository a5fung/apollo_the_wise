\pset pager off
\pset null '-'
\pset format unaligned
\pset fieldsep ' | '
-- 2026-10-06 PEP #411 (paper rehearsal): everything the audit log says 09:35:00-09:37:00 ET naming PEP / trade 411
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary,260) AS summary
FROM mi_audit_log
WHERE created_at >= '2026-10-06 13:35:00+00' AND created_at < '2026-10-06 13:37:30+00'
  AND (summary ILIKE '%PEP%' OR detail ILIKE '%"trade_id": 411%' OR detail ILIKE '%PEP%')
ORDER BY created_at;
