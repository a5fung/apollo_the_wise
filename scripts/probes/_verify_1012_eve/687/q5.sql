\echo === Q16 ep_rt_* and ep_filter + tinycap details 09:30-10:05
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, event_type, summary, left(detail,500) AS detail
FROM mi_audit_log WHERE created_at >= (timestamp '2026-10-12 09:30' AT TIME ZONE 'America/New_York') AND created_at < (timestamp '2026-10-12 10:10' AT TIME ZONE 'America/New_York')
 AND event_type IN ('ep_rt_admit','ep_rt_sustain_reject','ep_rt_declined_not_missed','ep_filter_session_rvol','ep_tinycap_observed','ep_rt_halt_suspect','ep_catalyst_provenance','lowcap_paper_lane_tick') ORDER BY id;

\echo === Q17 depth_open_sale_placed 10-08 detail
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, summary, left(detail,600) FROM mi_audit_log WHERE event_type='depth_open_sale_placed' ORDER BY id DESC LIMIT 3;

\echo === Q18 per-open-row last closes vs trailing lines? running_closes + hold_days for the 3 open rows
SELECT id, ticker, hold_days, partial_taken, breakeven_active, remaining_shares, stop_price, hard_stop, exit_rule, depth_sell_pending_on, left(running_closes::text,300) AS running_closes, lowest_price_seen, highest_price_seen, left(exits::text,300) AS exits FROM mi_live_trades WHERE id IN (404,414,419);

\echo === Q19 live orders for the 3 open rows (open/accepted stops)
SELECT trade_id, ticker, side, order_type, qty, stop_price, limit_price, status, purpose, submitted_at AT TIME ZONE 'America/New_York' AS sub_et FROM mi_live_orders WHERE trade_id IN (404,414,419) AND status IN ('accepted','new','held','partially_filled','pending_new','open') ORDER BY trade_id, id;
