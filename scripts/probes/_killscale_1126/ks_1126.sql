SET default_transaction_read_only = on;
SELECT id, signal_type, alert_date, ticker, round(total_pnl::numeric,0) pnl, round(risk_dollars_actual::numeric,1) risk,
 round((total_pnl/NULLIF(risk_dollars_actual,0))::numeric,2) r
FROM mi_live_trades WHERE status='closed' AND account_mode='live' AND pnl_attribution IS NULL ORDER BY alert_date, id;
SELECT to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') t, event_type, left(summary,200) FROM mi_audit_log
 WHERE event_type ILIKE '%drawdown%' AND created_at > now() - interval '60 days' ORDER BY created_at DESC LIMIT 12;
