SET default_transaction_read_only = on;
SELECT id, created_at AT TIME ZONE 'America/New_York' et, event_type, left(summary,300), left(detail,900) FROM mi_audit_log
 WHERE (summary ILIKE '%SYNA%' OR detail ILIKE '%"SYNA"%') AND event_type ILIKE '%mna%' AND created_at BETWEEN '2026-10-01' AND '2026-10-10' ORDER BY id LIMIT 6;
SELECT trade_date, close FROM mi_daily_closes WHERE ticker='SYNA' AND trade_date >= '2026-09-25' ORDER BY trade_date;
