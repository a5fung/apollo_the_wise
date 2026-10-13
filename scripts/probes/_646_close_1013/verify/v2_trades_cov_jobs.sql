\pset pager off
\pset null '-'
-- V2a: every trade row touched since 09-01 (fixed column list; v1's statement errored on a non-existent column)
SELECT id, ticker, account_mode, status, signal_type, alert_date,
       filled_at AT TIME ZONE 'America/New_York' AS filled_et, closed_at AT TIME ZONE 'America/New_York' AS closed_et,
       entry_shares, remaining_shares, stop_price, hard_stop, orb_low, exit_rule, depth_sell_pending_on,
       (SELECT string_agg(coalesce(e->>'reason',e->>'exit_reason','?')||'@'||coalesce(e->>'time',e->>'timestamp',e->>'date','?'),';') FROM jsonb_array_elements(coalesce(exits,'[]'::jsonb)) e) AS exits
FROM mi_live_trades
WHERE created_at >= '2026-09-01' OR closed_at >= '2026-09-01' OR (closed_at IS NULL AND filled_at IS NOT NULL)
ORDER BY id;
SELECT last_value FROM mi_live_trades_id_seq;

-- V2b: coverage slot rows, my own ET bucketing; examined/covered + array lengths, plus any row outside 17:00/19:00/21:10
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d_et,
       to_char(created_at AT TIME ZONE 'America/New_York','Dy') AS dow,
       event_type, to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') AS t_et,
       detail::jsonb->>'examined' AS ex, detail::jsonb->>'covered' AS cov,
       jsonb_array_length(detail::jsonb->'gaps') AS gaps, jsonb_array_length(detail::jsonb->'check_failed') AS failed,
       jsonb_array_length(detail::jsonb->'deferred') AS deferred
FROM mi_audit_log
WHERE event_type IN ('coverage_checked_post_close','coverage_checked_late','coverage_verified_evening')
  AND created_at >= '2026-09-10'
ORDER BY created_at;

-- V2c: every event type ever written whose name contains coverage/repair_attempted/unprotected (all time), counts + last
SELECT event_type, count(*) AS n, max(created_at AT TIME ZONE 'America/New_York') AS last_et
FROM mi_audit_log WHERE event_type ~* '(repair_attempted|unprotected|naked|remediation_failed|stop_update_failed|full_exit_failed|coverage_checked|coverage_verified|evening_verify)'
GROUP BY 1 ORDER BY 1;

-- V2d: job runs for the named jobs, per ET date, Mon-Fri 09-14..10-12
SELECT job_id, count(DISTINCT (started_at AT TIME ZONE 'America/New_York')::date) AS days_run,
       count(*) AS runs, count(*) FILTER (WHERE status='success') AS ok,
       string_agg(DISTINCT status, ',') AS statuses,
       min(to_char(started_at AT TIME ZONE 'America/New_York','HH24:MI:SS')) AS earliest_t,
       max(to_char(started_at AT TIME ZONE 'America/New_York','HH24:MI:SS')) AS latest_t
FROM mi_job_runs
WHERE job_id IN ('coverage_watch_post_close','coverage_watch_late','coverage_watch_evening','evening_position_backstop',
                 'eod_cleanup','live_position_update','post_close_stop_refresh','naked_position_post_refresh_check',
                 'naked_position_pre_close_check','depth_open_auction_sale')
  AND (started_at AT TIME ZONE 'America/New_York')::date BETWEEN '2026-09-14' AND '2026-10-12'
GROUP BY 1 ORDER BY 1;

-- V2e: weekday dates in window MISSING a success run for each named job
WITH days AS (SELECT d::date AS d FROM generate_series('2026-09-14'::date,'2026-10-12'::date,'1 day') g(d) WHERE extract(isodow FROM d)<6),
jobs AS (SELECT unnest(ARRAY['coverage_watch_post_close','coverage_watch_late','coverage_watch_evening','evening_position_backstop',
                 'eod_cleanup','live_position_update','post_close_stop_refresh','naked_position_post_refresh_check']) AS job_id)
SELECT j.job_id, d.d FROM jobs j CROSS JOIN days d
WHERE NOT EXISTS (SELECT 1 FROM mi_job_runs r WHERE r.job_id=j.job_id AND r.status='success'
                  AND (r.started_at AT TIME ZONE 'America/New_York')::date = d.d)
ORDER BY 1,2;
