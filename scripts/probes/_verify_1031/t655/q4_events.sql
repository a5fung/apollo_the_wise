SET default_transaction_read_only = on;
\echo == (1) renaming Arm B merges since the 10-17 deploy: lineage rows
SELECT id, old_name, new_name, mechanism, theme_date, renamed_at FROM mi_theme_renames WHERE mechanism = 'arm_b_merge_rename' ORDER BY renamed_at;
\echo == (1) theme_thesis_merged audit rows since 10-17 (detail head)
SELECT created_at AT TIME ZONE 'America/New_York' AS et, left(detail, 220) FROM mi_audit_log WHERE event_type = 'theme_thesis_merged' AND created_at >= '2026-10-17' ORDER BY created_at;
\echo == (2c) Pass 1.5 operator-exempt rows and errors since 10-17
SELECT event_type, count(*), min(created_at AT TIME ZONE 'America/New_York')::date, max(created_at AT TIME ZONE 'America/New_York')::date FROM mi_audit_log WHERE event_type LIKE 'theme_pass1_5_operator_exempt%' AND created_at >= '2026-10-17' GROUP BY 1;
\echo == (7) lane2_widen_reconsider predicate (threshold 20)
WITH runs AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d
  FROM mi_audit_log WHERE event_type = 'narrative_theme_discovery_ran'
    AND (created_at AT TIME ZONE 'America/New_York')::date >= DATE '2026-08-09'),
alerts AS (SELECT alert_date, count(DISTINCT ticker) AS n FROM mi_ep_alerts GROUP BY 1) SELECT count(*) FROM runs r LEFT JOIN alerts a ON a.alert_date = r.d WHERE a.n >= 2 AND NOT EXISTS (
  SELECT 1 FROM mi_theme_candidates_shadow c
  WHERE c.source = 'narrative_cogap' AND c.run_date = r.d);
