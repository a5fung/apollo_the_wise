-- positive traces that the screen RAN on flag-board names (not just 'no fired row'): non-fired mna_* rows
-- naming a ticker that was TIGHTENING/COILED/TRIGGERED on the board since 10-05
SELECT a.created_at AT TIME ZONE 'America/New_York' AS et, a.event_type, LEFT(a.summary,200) AS summary
FROM mi_audit_log a
WHERE a.created_at >= '2026-10-05' AND a.event_type LIKE 'mna%' AND a.event_type <> 'mna_filter_fired'
  AND EXISTS (SELECT 1 FROM mi_flag_candidates f
              WHERE f.stage IN ('TIGHTENING','COILED','TRIGGERED','unqualified') AND f.scan_date >= '2026-10-05'
                AND f.ticker IN (SELECT ticker FROM mi_flag_candidates WHERE stage IN ('TIGHTENING','COILED','TRIGGERED') AND scan_date >= '2026-10-05')
                AND a.summary LIKE f.ticker || ': %')
ORDER BY a.created_at;
SELECT '--- mna_headline_cap_hit since 10-05 (shared pool exhausted before the flag scan?) ---' AS x;
SELECT created_at AT TIME ZONE 'America/New_York' AS et, LEFT(summary,200) summary
FROM mi_audit_log WHERE event_type='mna_headline_cap_hit' AND created_at >= '2026-10-05' ORDER BY created_at;
