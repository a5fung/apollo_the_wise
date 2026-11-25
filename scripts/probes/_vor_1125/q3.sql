SET default_transaction_read_only = on;
SELECT scan_date, count(*) n, count(*) FILTER (WHERE (gates->'range'->>'pass')::bool IS NOT TRUE) no_base
FROM mi_breakout_v1_list WHERE scan_date >= '2026-11-16' GROUP BY 1 ORDER BY 1;
SELECT t.ticker, t.alert_date, round(t.total_pnl::numeric) pnl, (l.gates->'range'->>'pass') base_found
FROM mi_live_trades t LEFT JOIN mi_breakout_v1_list l ON l.ticker=t.ticker AND l.scan_date=(SELECT max(scan_date) FROM mi_breakout_v1_list x WHERE x.ticker=t.ticker AND x.scan_date<t.alert_date)
WHERE t.signal_type='breakout_v1' AND t.account_mode='paper' AND t.status='closed' ORDER BY t.alert_date;
