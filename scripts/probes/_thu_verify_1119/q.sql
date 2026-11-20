SET default_transaction_read_only = on;
\echo JOB
SELECT job_name, status, started_at AT TIME ZONE 'America/New_York', finished_at AT TIME ZONE 'America/New_York', left(coalesce(error,''),200) FROM mi_job_runs WHERE started_at::date = current_date AND job_name ILIKE '%mgmt%' OR (started_at > now()-interval '4 hours' AND job_name ILIKE '%judge%');
\echo CLOSED_TODAY
SELECT ticker, signal_type, account_mode, closed_at AT TIME ZONE 'America/New_York' FROM mi_live_trades WHERE status='closed' AND (closed_at AT TIME ZONE 'America/New_York')::date = (now() AT TIME ZONE 'America/New_York')::date;
\echo AUDIT
SELECT event_type, created_at AT TIME ZONE 'America/New_York', left(detail::text,300) FROM mi_audit_log WHERE created_at > now() - interval '9 hours' AND (event_type ILIKE '%sell_discipline%' OR event_type ILIKE '%mgmt_judge%' OR event_type ILIKE '%telegram%' OR event_type ILIKE 'breakout_pp%' OR event_type ILIKE 'stop_update%' OR event_type ILIKE 'naked%' OR event_type ILIKE 'profit_trigger%' OR event_type ILIKE 'partial_exit%') ORDER BY created_at;
