SET default_transaction_read_only = on;
-- review predicate (threshold 128) + settled count by population
SELECT 'predicate_count' AS k, count(*)::text AS v FROM mi_consolidation_entry_shadow
 WHERE origin = 'family_a' AND outcome IS NOT NULL AND realized_r IS NOT NULL
   AND entry_date >= DATE '2026-06-29';
SELECT 'by_mode_stop' AS k, entry_mode||'/'||stop_kind||' n='||count(*)||' last_entry='||max(entry_date) AS v
  FROM mi_consolidation_entry_shadow
 WHERE origin = 'family_a' AND outcome IS NOT NULL AND realized_r IS NOT NULL
   AND entry_date >= DATE '2026-06-29'
 GROUP BY entry_mode, stop_kind ORDER BY 2;
