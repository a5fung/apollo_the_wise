SET default_transaction_read_only = on;
SELECT summary, (detail::jsonb->>'as_of') AS d, (detail::jsonb->>'value')::float AS v FROM mi_audit_log WHERE event_type = 'metric_sample' AND summary IN ('cooldowns_per_day','theme_count_active','market_hours_boot_count','9m_alerts_per_day') AND created_at >= NOW() - INTERVAL '130 days' ORDER BY 1, 2;
