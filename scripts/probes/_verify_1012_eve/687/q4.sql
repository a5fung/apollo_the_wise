\echo === Q10 ep alerts alert_date 2026-10-12
SELECT id, ticker, alert_date, gap_pct, ep_score, score_tier, source, fire_status, judge_tier, setup_class, created_at AT TIME ZONE 'America/New_York' AS created_et, detected_at AT TIME ZONE 'America/New_York' AS det_et
FROM mi_ep_alerts WHERE alert_date = '2026-10-12' OR created_at >= (timestamp '2026-10-12 09:00' AT TIME ZONE 'America/New_York') ORDER BY id;

\echo === Q11 live_trades skipped/cancelled last 10 days for context
SELECT id, ticker, signal_type, account_mode, status, alert_date, skip_reason, created_at AT TIME ZONE 'America/New_York' AS created_et, exit_rule
FROM mi_live_trades WHERE created_at >= now() - interval '10 days' ORDER BY id DESC;

\echo === Q12 all-mode trade rows today incl paper (account_mode paper)
SELECT account_mode, signal_type, count(*), count(exit_rule) FROM mi_live_trades WHERE created_at >= (timestamp '2026-10-12 00:00' AT TIME ZONE 'America/New_York') GROUP BY 1,2;

\echo === Q13 depth_open_auction_sale job runs recent (any day)
SELECT job_id, started_at AT TIME ZONE 'America/New_York' AS started_et, status, rows_written, left(coalesce(error_message,''),200) AS err FROM mi_job_runs WHERE job_id ILIKE '%depth%' ORDER BY started_at DESC LIMIT 8;

\echo === Q14 audit rows containing 'depth' ever last 8 days (event_type)
SELECT event_type, count(*), max(created_at AT TIME ZONE 'America/New_York') AS last_et FROM mi_audit_log WHERE created_at >= now() - interval '8 days' AND (event_type ILIKE '%depth%' OR summary ILIKE '%depth%') GROUP BY 1 ORDER BY 3 DESC;

\echo === Q15 jobs scheduled 17:00-18:30 today run status (all jobs, non-success only)
SELECT job_id, started_at AT TIME ZONE 'America/New_York' AS started_et, status, left(coalesce(error_message,''),200) AS err FROM mi_job_runs WHERE started_at >= (timestamp '2026-10-12 16:30' AT TIME ZONE 'America/New_York') AND status <> 'success' ORDER BY started_at;
