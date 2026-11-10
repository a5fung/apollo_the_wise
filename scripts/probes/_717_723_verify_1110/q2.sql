SET default_transaction_read_only = on;
SELECT left(coalesce(skip_reason,'-'),80) r, count(*) FROM mi_live_trades WHERE signal_type='breakout_v1' AND alert_date=DATE '2026-11-10' AND status='skipped' GROUP BY 1 ORDER BY 2 DESC;
SELECT t.ticker, t.status, l.order_score, rank() OVER (ORDER BY l.order_score DESC) rk FROM mi_live_trades t JOIN mi_breakout_v1_list l ON l.ticker=t.ticker AND l.scan_date=DATE '2026-11-09' WHERE t.signal_type='breakout_v1' AND t.alert_date=DATE '2026-11-10' AND t.status NOT IN ('skipped') ORDER BY l.order_score DESC;
SELECT ticker, signal_type, status FROM mi_live_trades WHERE account_mode='paper' AND status IN ('filled','confirmed','order_placed','partially_filled');
