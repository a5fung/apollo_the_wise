SET default_transaction_read_only = on;
\echo == trade 429 after the 10-29 16:45 pass
SELECT id, ticker, status, remaining_shares, stop_price, hard_stop, breakeven_active, depth_sell_pending_on, exit_rule,
       jsonb_array_length(running_closes) AS n_closes, running_closes
FROM mi_live_trades WHERE id IN (429, 422);
\echo == the 16:45 job run
SELECT job_id, status, started_at AT TIME ZONE 'America/New_York' AS et FROM mi_job_runs WHERE started_at > '2026-10-29 16:40-04' ORDER BY started_at LIMIT 10;
\echo == audit rows naming CLS or IRON since 16:40
SELECT (created_at AT TIME ZONE 'America/New_York')::time(0) AS et, event_type, left(coalesce(summary, detail::text,''), 220)
FROM mi_audit_log WHERE created_at > '2026-10-29 16:40-04' AND (coalesce(summary,'') ~ '\m(CLS|IRON)\M' OR coalesce(detail::text,'') ~ '"(CLS|IRON)"') ORDER BY created_at LIMIT 20;
