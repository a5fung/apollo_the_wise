\pset pager off
\echo === V2-1 market-agent boot rows (intelligence role) 10-11 00:00 ET .. now, to date each image that scanned
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t_et, event_type, left(summary,90) s FROM mi_audit_log WHERE created_at >= '2026-10-11 04:00+00' AND event_type='account_mode_active' ORDER BY id;
