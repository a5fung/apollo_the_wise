SET default_transaction_read_only = on;
SELECT job_id, status, started_at AT TIME ZONE 'America/New_York', duration_s::int, left(coalesce(error_message,''),200) FROM mi_job_runs WHERE started_at > now() - interval '40 minutes' AND job_id NOT IN ('stop_ack_timeout_watchdog','stuck_fill_watchdog','breakout_v1_entry') ORDER BY started_at;
SELECT event_type, created_at AT TIME ZONE 'America/New_York', left(detail::text,200) FROM mi_audit_log WHERE created_at > now() - interval '40 minutes' AND event_type NOT ILIKE 'exposure%' ORDER BY created_at;
