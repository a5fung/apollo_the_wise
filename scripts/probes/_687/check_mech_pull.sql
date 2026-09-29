-- ADVERSARIAL CHECK of #687 part 3 — ONE read-only prod capture (READ ONLY transaction, rolled back). $0.
BEGIN TRANSACTION READ ONLY;
\echo === FULL_EXIT_ORDERS_REAL_COLUMNS ===
SELECT o.trade_id, o.ticker, t.account_mode, o.status, o.qty, o.filled_qty, o.filled_avg_price,
       o.submitted_at AT TIME ZONE 'America/New_York' AS submitted_et,
       o.filled_at AT TIME ZONE 'America/New_York' AS filled_et,
       o.cancelled_at AT TIME ZONE 'America/New_York' AS cancelled_et,
       jsonb_typeof(o.raw_response) AS raw_type,
       CASE WHEN jsonb_typeof(o.raw_response) = 'string' THEN left(o.raw_response #>> '{}', 700)
            ELSE left(o.raw_response::text, 700) END AS raw
FROM mi_live_orders o JOIN mi_live_trades t ON t.id = o.trade_id
WHERE o.purpose = 'full_exit' ORDER BY o.trade_id;
\echo === TRADES_119_167_382_400_404 ===
SELECT id, ticker, account_mode, signal_type, alert_date, status, entry_price, hard_stop, stop_price, stop_order_id,
       remaining_shares, partial_taken, breakeven_active, closed_at AT TIME ZONE 'America/New_York' AS closed_et,
       left(exits::text, 900) AS exits
FROM mi_live_trades WHERE id IN (119, 167, 382, 400, 404) ORDER BY id;
\echo === ORDERS_382_400_404 ===
SELECT trade_id, ticker, purpose, order_type, status, qty, stop_price, limit_price, filled_qty, filled_avg_price,
       submitted_at AT TIME ZONE 'America/New_York' AS submitted_et, filled_at AT TIME ZONE 'America/New_York' AS filled_et,
       left(alpaca_order_id, 8) AS oid
FROM mi_live_orders WHERE trade_id IN (382, 400, 404) ORDER BY trade_id, submitted_at;
\echo === AUDIT_BW_OVERNIGHT_0526_0527 ===
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary, 260) AS summary
FROM mi_audit_log
WHERE created_at >= TIMESTAMPTZ '2026-05-26 15:30-04' AND created_at < TIMESTAMPTZ '2026-05-27 10:30-04'
  AND (summary ILIKE '%BW%' OR detail ILIKE '%"BW"%' OR detail ILIKE '%trade_id": 119%' OR detail ILIKE '%trade_id=119%')
ORDER BY created_at;
\echo === AUDIT_IBM_OVERNIGHT_0609_0610 ===
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary, 260) AS summary
FROM mi_audit_log
WHERE created_at >= TIMESTAMPTZ '2026-06-09 15:30-04' AND created_at < TIMESTAMPTZ '2026-06-10 10:30-04'
  AND (summary ILIKE '%IBM%' OR detail ILIKE '%"IBM"%' OR detail ILIKE '%trade_id": 167%')
ORDER BY created_at;
\echo === AUDIT_OKTA_0911_1644_TO_0914_1000 ===
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary, 300) AS summary
FROM mi_audit_log
WHERE created_at >= TIMESTAMPTZ '2026-09-11 15:55-04' AND created_at < TIMESTAMPTZ '2026-09-14 10:00-04'
  AND (summary ILIKE '%OKTA%' OR detail ILIKE '%OKTA%')
  AND event_type NOT IN ('theme_discovery_shown_declined', 'api_failure_fmp', 'book_concentration_snapshot', 'exposure_family_checked')
ORDER BY created_at;
\echo === COVERAGE_WATCH_RECENT ===
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary, 200) AS summary
FROM mi_audit_log
WHERE event_type IN ('coverage_checked_post_close', 'coverage_checked_late', 'coverage_verified_evening',
                     'coverage_checked_post_close_repair_attempted', 'coverage_checked_late_repair_attempted',
                     'position_unprotected', 'stop_ack_broker_covered', 'stop_remediation_skipped_pending_exit')
  AND created_at >= NOW() - INTERVAL '6 days'
ORDER BY created_at DESC LIMIT 30;
\echo === MAGNA53_STRATEGY_AND_TOGGLES ===
SELECT strategy_id, phase, profit_trigger_r, breakeven_arm_r FROM mi_strategies WHERE strategy_id = 'magna53';
SELECT safeguard, account_mode, state, updated_at AT TIME ZONE 'America/New_York' AS updated_et
FROM mi_safeguard_state WHERE safeguard IN ('profit_take_oco', 'profit_take_resting_limit', 'partial_exit_leg_safe')
ORDER BY safeguard;
\echo === LIVE_EXIT_REASONS_ALL_TIME ===
SELECT t.account_mode, e ->> 'reason' AS reason, count(*) AS n
FROM mi_live_trades t, jsonb_array_elements(CASE WHEN jsonb_typeof(t.exits) = 'array' THEN t.exits ELSE '[]'::jsonb END) e
WHERE t.signal_type = 'magna53' GROUP BY 1, 2 ORDER BY 1, 3 DESC;
ROLLBACK;
