-- READ-ONLY. VERIFIER. flag_stage_flip_held audit rows per ET day since 10-09 vs holds written that scan_date (v2_hold.sql V2e had a GROUP BY error).
SET default_transaction_read_only = on;
SET statement_timeout = '60s';
WITH a AS (
  SELECT (created_at AT TIME ZONE 'America/New_York')::date AS et_day, id, summary FROM mi_audit_log
  WHERE event_type='flag_stage_flip_held' AND created_at >= TIMESTAMPTZ '2026-10-09 00:00-04'
), d AS (SELECT DISTINCT scan_date FROM mi_flag_candidates WHERE scan_date >= DATE '2026-10-09')
SELECT d.scan_date, (SELECT count(*) FROM a WHERE a.et_day = d.scan_date) audit_rows,
       (SELECT string_agg(id::text||' '||summary, '; ' ORDER BY id) FROM a WHERE a.et_day = d.scan_date) rows,
       (SELECT count(*) FROM mi_flag_candidates c WHERE c.scan_date = d.scan_date AND c.held_from_stage IS NOT NULL) holds_that_date
FROM d ORDER BY 1;
