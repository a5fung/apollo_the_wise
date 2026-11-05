SET default_transaction_read_only = on;
SELECT id, ticker, score_tier, created_at AT TIME ZONE 'America/New_York' AS et FROM mi_ep_alerts WHERE alert_date = DATE '2026-11-05' ORDER BY id;
SELECT id, event_type, created_at AT TIME ZONE 'America/New_York' AS et, left(coalesce(summary,''),170) FROM mi_audit_log
WHERE created_at > TIMESTAMPTZ '2026-11-05 14:20+00' AND (event_type ILIKE 'magna53_open%' OR event_type ILIKE 'orb_gap%' OR event_type ILIKE 'ep_rt_floor%' OR event_type IN ('unified_allocation_decided','orb_entry_submitted','orb_order_submitted')) ORDER BY id LIMIT 30;
