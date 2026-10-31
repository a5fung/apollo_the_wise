SET default_transaction_read_only = on;
SELECT alert_date, ticker, status, skip_reason, account_mode, created_at AT TIME ZONE 'America/New_York' AS created_et, id
FROM mi_live_trades WHERE alert_date >= '2026-10-22' ORDER BY alert_date, created_at;
SELECT alert_date, ticker, score_tier, ep_score, source, detected_at AT TIME ZONE 'America/New_York' det_et FROM mi_ep_alerts WHERE alert_date >= '2026-10-22' AND score_tier='HIGH' ORDER BY alert_date, detected_at;
SELECT date_trunc('day', created_at AT TIME ZONE 'America/New_York') d, count(*) FROM mi_audit_log WHERE created_at > now() - interval '12 days' AND (event_type ILIKE '%orb%' OR event_type ILIKE '%skip%') GROUP BY 1,event_type ORDER BY 1;
