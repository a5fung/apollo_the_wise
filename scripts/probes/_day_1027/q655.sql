SET default_transaction_read_only = on;
SELECT theme_date, name, stage, source FROM mi_themes WHERE 'RH' = ANY(tickers) AND theme_date >= '2026-10-22' ORDER BY theme_date, name;
SELECT * FROM mi_validation_cooldowns WHERE ticker='RH' AND created_at >= '2026-10-20' ORDER BY created_at;
SELECT created_at AT TIME ZONE 'America/New_York' et, event_type, left(summary,240) FROM mi_audit_log WHERE created_at >= '2026-10-23' AND (summary ILIKE '%RH %' OR summary ILIKE '%RH:%' OR detail ILIKE '%"RH"%') AND event_type ILIKE ANY (ARRAY['%valid%','%remov%','%rescore%','%moved%','%rehome%','%join%']) ORDER BY 1;
SELECT created_at AT TIME ZONE 'America/New_York' et, event_type, left(summary,200) FROM mi_audit_log WHERE created_at >= '2026-10-26 16:00-04' AND event_type ILIKE '%rescore%' ORDER BY 1 LIMIT 5;
