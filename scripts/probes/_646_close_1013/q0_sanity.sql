\pset pager off
\timing off
SELECT now() AS db_now_utc, (now() AT TIME ZONE 'America/New_York') AS now_et;
-- table sizes / date span of the audit log
SELECT min(created_at) AS first_row, max(created_at) AS last_row, count(*) FROM mi_audit_log WHERE created_at >= '2026-09-12';
-- job_runs status vocabulary in window
SELECT status, count(*) FROM mi_job_runs WHERE started_at >= '2026-09-12' GROUP BY 1 ORDER BY 2 DESC;
-- trade status vocabulary by account_mode, and whether closed rows lack closed_at
SELECT account_mode, status, count(*) AS n, count(*) FILTER (WHERE closed_at IS NULL) AS closed_at_null, count(*) FILTER (WHERE filled_at IS NULL) AS filled_at_null, count(*) FILTER (WHERE remaining_shares>0) AS rem_pos
FROM mi_live_trades WHERE created_at >= '2026-08-15' GROUP BY 1,2 ORDER BY 1,2;
-- event census (broad regex) in window
SELECT event_type, count(*) AS n, min(created_at AT TIME ZONE 'America/New_York') AS first_et, max(created_at AT TIME ZONE 'America/New_York') AS last_et
FROM mi_audit_log
WHERE created_at >= '2026-09-12' AND created_at < '2026-10-13 12:00+00'
  AND event_type ~* '(stop|unprot|naked|cover|orphan|remed|restor|reprot|full_exit|backstop|ack|pointer|repair|breach|exit_rej|cancel_or_reject|sync_)'
GROUP BY 1 ORDER BY 1;
