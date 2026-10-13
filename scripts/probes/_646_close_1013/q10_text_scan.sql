\pset pager off
\pset null '-'
-- Catch-all: any audit row in the window whose TEXT (not just event_type) says unprotected/naked/bare/no stop/flagged/uncovered
SELECT event_type, count(*) AS n, min(created_at AT TIME ZONE 'America/New_York') AS first_et, max(created_at AT TIME ZONE 'America/New_York') AS last_et
FROM mi_audit_log
WHERE created_at >= '2026-09-14' AND created_at < '2026-10-13 12:00+00'
  AND (summary ~* '(unprotect|naked|no live stop|no stop|bare|uncovered|still unprotected|gap\)|COVERAGE_FLAGGED|manual intervention)' OR detail ~* '(unprotect|naked|no_stop_and_no_stop_price|COVERAGE_FLAGGED)')
  AND event_type NOT IN ('coverage_checked_post_close','coverage_checked_late','coverage_verified_evening','path_coverage_gap')
GROUP BY 1 ORDER BY 1;
-- and the live-only slice of the same: rows naming a live trade id (tickers of live positions in window)
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary,220) AS summary
FROM mi_audit_log
WHERE created_at >= '2026-09-14' AND created_at < '2026-10-13 12:00+00'
  AND (summary ~* '(unprotect|naked|no live stop|uncovered|COVERAGE_FLAGGED|manual intervention)' OR detail ~* '(unprotect|naked|no_stop_and_no_stop_price|COVERAGE_FLAGGED)')
  AND event_type NOT IN ('coverage_checked_post_close','coverage_checked_late','coverage_verified_evening','path_coverage_gap')
  AND (summary ~ '(OKTA|HOOD|SEI|DFTX|VICR|KOD|CEG|PENG|HUM)' OR detail ~ '"account_mode": "live"')
ORDER BY created_at LIMIT 30;
-- rows where a coverage-slot detail JSON carries a non-empty gaps/check_failed/deferred array (should be 0 per q1 totals)
SELECT count(*) AS slot_rows_with_any_nonempty_array FROM mi_audit_log
WHERE event_type IN ('coverage_checked_post_close','coverage_checked_late','coverage_verified_evening') AND created_at >= '2026-09-12'
  AND (jsonb_array_length(detail::jsonb->'gaps')>0 OR jsonb_array_length(detail::jsonb->'check_failed')>0 OR jsonb_array_length(detail::jsonb->'deferred')>0);
