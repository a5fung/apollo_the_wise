SET default_transaction_read_only = on;
SELECT column_name FROM information_schema.columns WHERE table_name='mi_breakout_v1_list' ORDER BY ordinal_position;
SELECT * FROM mi_breakout_v1_list WHERE scan_date=DATE '2026-11-09' AND ticker IN ('ABCL','OUST','MRNA','SPCE','NVAX');
SELECT created_at AT TIME ZONE 'America/New_York' et, left(summary,250) FROM mi_audit_log WHERE event_type='breakout_v1_entry_order' AND created_at > TIMESTAMPTZ '2026-11-10 13:00+00' ORDER BY id;
