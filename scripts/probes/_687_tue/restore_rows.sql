-- #687 Tue 10-13 expiry test: what production wrote for trade 421 (read-only)
SELECT * FROM mi_live_trades WHERE id = 421 \gx
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, event_type,
       left(detail::text, 260) AS detail
  FROM mi_audit_log
 WHERE created_at >= '2026-10-13 12:00+00' AND (detail::text LIKE '%"trade_id": 421%' OR detail::text LIKE '%f18ed7c0%' OR detail::text LIKE '%1822f417%')
 ORDER BY id;
