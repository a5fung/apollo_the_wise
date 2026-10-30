SET default_transaction_read_only = on;
SELECT (created_at AT TIME ZONE 'America/New_York')::time(3) et, event_type, detail FROM mi_audit_log
WHERE created_at >= '2026-10-30 09:36-04' AND created_at < '2026-10-30 09:37-04' AND event_type IN ('entry_chase_cap_skipped','orb_order_failed','orb_bar_fetched');
SELECT ticker, bar_size_minutes, status, orb_high, orb_low, entry_price, trigger_minute_et, skip_reason FROM mi_orb_shadow_trades WHERE ticker='REGN' AND alert_date='2026-10-30';
SELECT close, open_price, high_price, low_price, trade_date FROM mi_daily_closes WHERE ticker='REGN' AND trade_date >= '2026-10-28' ORDER BY trade_date;
