SET default_transaction_read_only = on;
SELECT id, created_at AT TIME ZONE 'America/New_York' et, left(summary,250), left(detail,300) FROM mi_audit_log WHERE created_at >= '2026-10-26 12:50-04' AND event_type='dead_column_suspect' ORDER BY id;
SELECT count(*), min(created_at AT TIME ZONE 'America/New_York')::date FROM mi_audit_log WHERE event_type='dead_column_suspect' AND created_at >= '2026-10-19';
SELECT id, filled_at AT TIME ZONE 'America/New_York' FROM mi_live_trades WHERE id IN (374, 382, 372, 383);
