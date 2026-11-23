SET default_transaction_read_only = on;
SELECT detail FROM mi_audit_log WHERE created_at >= '2026-11-23 00:00-05' AND event_type='stop_ack_timeout_remediated';
SELECT id, ticker, status, account_mode, exit_reason, exit_price, shares, stop_price FROM mi_trades WHERE id=1427;
SELECT ticker, to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI') t, (float_shares/1e6)::int float_m, score_breakdown->>'float' fpts, ep_score, filter_reason FROM mi_ep_scan_log WHERE scan_date='2026-11-23' AND score_breakdown IS NOT NULL AND float_shares < 50e6 ORDER BY ep_score DESC NULLS LAST LIMIT 8;
