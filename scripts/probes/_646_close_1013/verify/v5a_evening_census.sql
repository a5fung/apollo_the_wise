\pset pager off
\pset null '-'
-- V5a re-issue (v5's version errored on a non-JSON detail row): census of ALL audit rows 16:00-21:15 ET on weeknights 09-14..10-12
-- whose type or summary touches stops/coverage/positions; account mode read from detail when it parses, else from the summary tag.
SELECT a.event_type,
       CASE WHEN a.summary ~* '\[paper\]' OR a.detail ~ '"account_mode": "paper"' THEN 'paper'
            WHEN a.summary ~* '\[live\]' OR a.detail ~ '"account_mode": "live"' THEN 'live' ELSE '?' END AS am,
       count(*) AS n, count(DISTINCT (a.created_at AT TIME ZONE 'America/New_York')::date) AS nights,
       string_agg(DISTINCT to_char(a.created_at AT TIME ZONE 'America/New_York','HH24:MI'),',') AS hhmm
FROM mi_audit_log a
WHERE a.created_at >= '2026-09-14 04:00+00' AND a.created_at < '2026-10-13 12:00+00'
  AND (a.created_at AT TIME ZONE 'America/New_York')::time BETWEEN '16:00' AND '21:15'
  AND extract(isodow FROM a.created_at AT TIME ZONE 'America/New_York') < 6
  AND (a.event_type ~* '(stop|cover|unprot|naked|orphan|remed|restor|repair|exit|sync|backstop|pending|position|fail|reject|alert|breach|flat)'
       OR a.summary ~* '(unprotected|naked|no stop|without a stop|NOT RESTORED|FAILED)')
  AND a.event_type NOT IN ('theme_orphan_sub','path_coverage_gap','coverage_probe_ran','ep_rt_universe_coverage','backup_restore_check_ok')
GROUP BY 1,2 ORDER BY 1,2;

-- every row in that census on a LIVE trade or with '?' mode that is not one of the routine 16:45 cycle / slot / refresh types
SELECT to_char(a.created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS et, a.event_type, left(a.summary,220) AS summary
FROM mi_audit_log a
WHERE a.created_at >= '2026-09-14 04:00+00' AND a.created_at < '2026-10-13 12:00+00'
  AND (a.created_at AT TIME ZONE 'America/New_York')::time BETWEEN '16:00' AND '21:15'
  AND extract(isodow FROM a.created_at AT TIME ZONE 'America/New_York') < 6
  AND (a.event_type ~* '(stop|cover|unprot|naked|orphan|remed|restor|repair|exit|sync|backstop|pending|position|fail|reject|alert|breach|flat)'
       OR a.summary ~* '(unprotected|naked|no stop|without a stop|NOT RESTORED|FAILED)')
  AND a.event_type NOT IN ('theme_orphan_sub','path_coverage_gap','coverage_probe_ran','ep_rt_universe_coverage','backup_restore_check_ok',
       'coverage_checked_post_close','coverage_checked_late','coverage_verified_evening','stop_update_started','stop_update_retry_triggered',
       'stop_update_retry_succeeded','stop_replacement_confirmed_silent','stop_updated','dead_stop_price_preserved','stop_refresh_ran','stop_order_id_changed')
  AND NOT (a.summary ~* '\[paper\]' OR a.detail ~ '"account_mode": "paper"')
ORDER BY a.created_at;
