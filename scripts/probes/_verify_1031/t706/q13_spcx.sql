SET default_transaction_read_only = on;
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary,160) AS s FROM mi_audit_log
WHERE created_at >= '2026-10-21 13:29:00+00' AND created_at < '2026-10-21 13:34:00+00' AND event_type LIKE 'orb%' ORDER BY created_at;
SELECT id, ticker, status, skip_reason, created_at AT TIME ZONE 'America/New_York' AS et FROM mi_live_trades WHERE alert_date='2026-10-21' ORDER BY id;
SELECT column_name FROM information_schema.columns WHERE table_name='mi_job_log' ORDER BY ordinal_position;
