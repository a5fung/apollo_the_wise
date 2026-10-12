\echo === the exact bound query the allocator runs (pre-entry live book, now) vs rebuilt 09:28 ===
SELECT COUNT(*) AS allocator_query_now FROM mi_live_trades
WHERE status = ANY(ARRAY['filled','order_placed','confirmed']) AND ('live'::text IS NULL OR account_mode = 'live') AND (DATE '2026-10-12' IS NULL OR alert_date < DATE '2026-10-12');
