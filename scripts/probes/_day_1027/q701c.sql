SET default_transaction_read_only = on;
SELECT ticker, alert_date, score_tier, ep_score, catalyst_quality, created_at AT TIME ZONE 'America/New_York' FROM mi_ep_alerts WHERE ticker='MFIC' AND alert_date >= '2026-10-20' ORDER BY created_at;
