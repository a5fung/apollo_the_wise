-- READ-ONLY (advisor review 10-16). (1) prod constraints on mi_analyst_estimates; (4) FEIM 09-18: why no confirm row?
SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='mi_analyst_estimates'::regclass ORDER BY 1;
SELECT period_type, source, count(*) FROM mi_analyst_estimates GROUP BY 1,2 ORDER BY 1,2;
SELECT id, ticker, anchor_date, entry_date, entry_mode FROM mi_consolidation_entry_shadow WHERE ticker='FEIM' ORDER BY entry_date;
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary,200) FROM mi_audit_log
 WHERE created_at BETWEEN '2026-09-17' AND '2026-09-20' AND (summary ILIKE '%FEIM%' OR detail ILIKE '%FEIM%') ORDER BY created_at;
SELECT ticker, anchor_date, state, last_eval FROM mi_anticipation_consolidation WHERE ticker='FEIM' ORDER BY anchor_date;
