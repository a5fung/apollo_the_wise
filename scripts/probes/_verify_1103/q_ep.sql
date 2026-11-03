SET default_transaction_read_only = on;
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(detail::text, 520) FROM mi_audit_log
 WHERE created_at > '2026-11-03 13:00+00' AND (event_type ILIKE 'magna53_open%' OR event_type ILIKE 'orb_%' OR event_type = 'ep_rt_floor_flip_up')
 ORDER BY created_at;
\echo == trades today
SELECT id, ticker, account_mode, signal_type, status, entry_price, stop_price, created_at AT TIME ZONE 'America/New_York' AS et FROM mi_live_trades WHERE created_at > '2026-11-03 12:00+00' AND signal_type <> 'breakout_v1' ORDER BY id;
\echo == scan log prev_close for the would-skip names
SELECT DISTINCT ON (ticker) ticker, scan_date, prev_close FROM mi_ep_scan_log WHERE scan_date = '2026-11-03' AND ticker IN ('FN','AEHR','AEIS') ORDER BY ticker, scan_time_et DESC;
