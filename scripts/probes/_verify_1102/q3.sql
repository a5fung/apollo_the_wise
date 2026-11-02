SET default_transaction_read_only = on;
SELECT l.ticker, l.list_rank, (SELECT MAX((a.created_at AT TIME ZONE 'America/New_York')::date) FROM mi_audit_log a WHERE a.event_type IN ('mna_filter_fired','mna_pin_confirmed') AND split_part(a.summary,' ',1) = l.ticker AND a.created_at >= NOW() - INTERVAL '120 days') AS last_mna_block
FROM mi_breakout_v1_list l WHERE l.scan_date = (SELECT MAX(scan_date) FROM mi_breakout_v1_list) ORDER BY l.list_rank;
