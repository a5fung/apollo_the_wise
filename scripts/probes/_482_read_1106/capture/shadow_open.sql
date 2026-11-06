SET default_transaction_read_only = on;
SET TIME ZONE 'UTC';
\copy (SELECT s.id, s.ticker, s.alert_date, s.bar_size_minutes, s.signal_type, s.entry_price, s.hard_stop, s.status, s.quarantined, s.replayed_at, s.created_at FROM mi_orb_shadow_trades s WHERE s.bar_size_minutes = 5 AND s.status = 'open' AND NOT s.quarantined AND s.signal_type = 'magna53' AND s.alert_date >= DATE '2026-08-17' ORDER BY s.alert_date, s.ticker) TO STDOUT WITH CSV HEADER
