SET default_transaction_read_only = on;
\echo == A. today's alerts
SELECT alert_date, ticker, score_tier, LEFT(COALESCE(signal_type,''),20) AS sig, created_at AT TIME ZONE 'America/New_York' AS at_et FROM mi_ep_alerts WHERE alert_date = CURRENT_DATE ORDER BY created_at;
\echo == B. audit events 09:00-09:50 ET today (counts by type)
SELECT event_type, COUNT(*) FROM mi_audit_log WHERE created_at >= (CURRENT_DATE::timestamp AT TIME ZONE 'America/New_York') + INTERVAL '9 hours' AND created_at < (CURRENT_DATE::timestamp AT TIME ZONE 'America/New_York') + INTERVAL '9 hours 50 minutes' GROUP BY 1 ORDER BY 2 DESC;
\echo == C. the ORB / floor / skip rows (09:25-09:50 ET), in order
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') AS t, event_type, LEFT(summary, 170) AS summary FROM mi_audit_log WHERE created_at >= (CURRENT_DATE::timestamp AT TIME ZONE 'America/New_York') + INTERVAL '9 hours 25 minutes' AND created_at < (CURRENT_DATE::timestamp AT TIME ZONE 'America/New_York') + INTERVAL '9 hours 50 minutes' AND (event_type ILIKE 'orb%' OR event_type ILIKE 'magna53_open%' OR event_type ILIKE 'ep_rt%' OR event_type ILIKE '%skip%' OR event_type ILIKE 'entry%' OR event_type ILIKE 'unified_alloc%' OR event_type ILIKE 'breakout_v1%') ORDER BY created_at;
\echo == D. job runs 09:20-09:50 ET
SELECT job_id, status, to_char(started_at AT TIME ZONE 'America/New_York','HH24:MI:SS') AS st FROM mi_job_runs WHERE started_at >= (CURRENT_DATE::timestamp AT TIME ZONE 'America/New_York') + INTERVAL '9 hours 20 minutes' AND started_at < (CURRENT_DATE::timestamp AT TIME ZONE 'America/New_York') + INTERVAL '9 hours 50 minutes' AND job_id ~ '(unified|orb|breakout|ep_scan|alloc)' ORDER BY started_at LIMIT 40;
\echo == E. trades created today
SELECT id, ticker, signal_type, account_mode, status, to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') AS t, entry_price, stop_price FROM mi_live_trades WHERE created_at >= CURRENT_DATE::timestamp AT TIME ZONE 'America/New_York' ORDER BY created_at;
