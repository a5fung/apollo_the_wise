SET default_transaction_read_only = on;
SELECT now() AT TIME ZONE 'America/New_York' now_et, (SELECT state FROM mi_safeguard_state WHERE safeguard='breakout_v1_paper') sw;
SELECT id, ticker, status, left(coalesce(skip_reason,''),60) FROM mi_live_trades WHERE signal_type='breakout_v1' AND alert_date=DATE '2026-11-10' AND status NOT IN ('skipped') ORDER BY id;
SELECT created_at AT TIME ZONE 'America/New_York' et, event_type, left(summary,140) FROM mi_audit_log WHERE event_type ILIKE 'breakout_v1%' AND created_at > TIMESTAMPTZ '2026-11-10 15:19+00' AND event_type NOT IN ('breakout_v1_entry_hold','breakout_v1_entry_abstain') ORDER BY id LIMIT 15;
