SET default_transaction_read_only = on;
\x on
SELECT * FROM mi_live_trades WHERE id = 422;
\x off
\echo == audit for trade 422 since yesterday 16:00 ET
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(detail::text, 500) FROM mi_audit_log WHERE created_at > '2026-11-02 21:00+00' AND detail::text LIKE '%422%' AND detail::text ILIKE '%IRON%' ORDER BY created_at;
