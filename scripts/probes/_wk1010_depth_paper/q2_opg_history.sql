-- READ-ONLY. Has ANY opening-auction (opg) sale ever been sent from the app, and what did the
-- depth rule's audit events show? (review of branch wk1010/depth-paper-lane, 2026-10-10)
SELECT event_type, count(*) AS n,
       count(*) FILTER (WHERE detail LIKE '%"account_mode": "paper"%') AS paper_n,
       min(created_at) AS first_at, max(created_at) AS last_at
FROM mi_audit_log
WHERE event_type IN ('depth_open_sale_placed','depth_open_sale_error','depth_close_below_line',
                     'depth_sale_mark_stale','time_stop')
GROUP BY 1 ORDER BY 1;
SELECT '---';
SELECT count(*) AS orders_mentioning_opg
FROM mi_live_orders WHERE raw_response::text ILIKE '%opg%';
SELECT '---';
SELECT count(*) AS stamped_trades FROM mi_live_trades WHERE exit_rule IS NOT NULL;
