-- #312 Tue 10-13: the 09:28 allocator row and today's EP alerts (read-only)
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(detail::text, 600) AS detail
  FROM mi_audit_log
 WHERE created_at >= '2026-10-13 12:00+00' AND event_type ILIKE 'unified_allocat%'
 ORDER BY id;
SELECT count(*) AS live_open_filled FROM mi_live_trades WHERE account_mode='live' AND status='filled' AND remaining_shares > 0;
SELECT ticker, account_mode, status, remaining_shares FROM mi_live_trades WHERE status='filled' AND remaining_shares > 0 ORDER BY account_mode, ticker;
