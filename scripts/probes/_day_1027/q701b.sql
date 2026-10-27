SET default_transaction_read_only = on;
SELECT column_name FROM information_schema.columns WHERE table_name='mi_ep_alerts' AND column_name IN ('ticker','alert_date','score_tier','tier','ep_score','catalyst_quality','llm_catalyst_quality','acting_catalyst_quality','grade','alerted_at','created_at') ORDER BY 1;
