SET default_transaction_read_only = on;
SELECT (created_at AT TIME ZONE 'America/New_York')::time(3) AS et, event_type, left(coalesce(summary, detail::text, ''), 240) AS s
FROM mi_audit_log WHERE created_at >= '2026-10-30 09:00-04' AND (coalesce(summary,'') ILIKE '%REGN%' OR coalesce(detail::text,'') ILIKE '%"REGN"%')
ORDER BY created_at LIMIT 40;
SELECT id, ticker, status, skip_reason, orb_high, orb_low, entry_price, stop_price, entry_shares, (proposed_at AT TIME ZONE 'America/New_York')::time(0) proposed FROM mi_live_trades WHERE id = 434;
SELECT (bar_time AT TIME ZONE 'America/New_York')::time(0) et, open, high, low, close, volume FROM mi_intraday_bars WHERE ticker='REGN' AND bar_time >= '2026-10-30 09:30-04' AND bar_time < '2026-10-30 09:40-04' ORDER BY bar_time;
