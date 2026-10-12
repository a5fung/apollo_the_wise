\echo == QRVO board rows
SELECT ticker, anchor_date, state, coil_days, mna_screened_on, to_char(updated_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') AS upd FROM mi_anticipation_consolidation WHERE ticker='QRVO' ORDER BY anchor_date DESC LIMIT 5;
\echo == QRVO and SWKS latest daily closes
SELECT ticker, max(trade_date) AS last_bar, count(*) FROM mi_daily_closes WHERE ticker IN ('QRVO','SWKS','SYNA') AND trade_date >= '2026-09-01' GROUP BY 1;
\echo == QRVO detail of 10-09 price_unread row
SELECT left(detail,900) FROM mi_audit_log WHERE id=55116;
