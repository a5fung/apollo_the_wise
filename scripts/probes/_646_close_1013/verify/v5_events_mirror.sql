\pset pager off
\pset null '-'
-- V5a: every audit row 16:00-21:15 ET on weeknights 09-14..10-12, by event_type, split by the account_mode in detail (if any)
SELECT a.event_type, coalesce(a.detail::jsonb->>'account_mode','?') AS am, count(*) AS n,
       string_agg(DISTINCT to_char(a.created_at AT TIME ZONE 'America/New_York','HH24:MI'),',') AS hhmm
FROM mi_audit_log a
WHERE a.created_at >= '2026-09-14 04:00+00' AND a.created_at < '2026-10-13 12:00+00'
  AND (a.created_at AT TIME ZONE 'America/New_York')::time BETWEEN '16:00' AND '21:15'
  AND extract(isodow FROM a.created_at AT TIME ZONE 'America/New_York') < 6
  AND a.detail ~ '^\s*\{'
  AND a.event_type ~* '(stop|cover|unprot|naked|orphan|remed|restor|repair|exit|sync|backstop|pending|position|job_fail|failure|alert)'
GROUP BY 1,2 ORDER BY 1,2;

-- V5b: any job-failure / recovery row naming one of the named jobs, in window
SELECT a.event_type, to_char(a.created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS et, left(a.summary,200) AS summary
FROM mi_audit_log a
WHERE a.created_at >= '2026-09-14 04:00+00' AND a.created_at < '2026-10-13 12:00+00'
  AND (a.summary ~* '(coverage_watch|evening_position_backstop|eod_cleanup|live_position_update|post_close_stop_refresh|naked_position_post)'
       OR a.detail ~* '(coverage_watch|evening_position_backstop|post_close_stop_refresh|naked_position_post_refresh)')
  AND a.event_type NOT IN ('coverage_checked_post_close','coverage_checked_late','coverage_verified_evening')
ORDER BY a.created_at;

-- V5c: full_exit_rejected + restore + watchdog + coverage-repair rows (any account), with mode
SELECT to_char(a.created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS.MS') AS et, a.event_type,
       a.detail::jsonb->>'account_mode' AS am, a.detail::jsonb->>'ticker' AS tkr, a.detail::jsonb->>'trade_id' AS tid,
       left(a.summary,160) AS summary
FROM mi_audit_log a
WHERE a.created_at >= '2026-09-14 04:00+00' AND a.created_at < '2026-10-13 12:00+00'
  AND (a.event_type IN ('full_exit_rejected','stop_ack_timeout_remediated','stop_coverage_repaired','stop_coverage_repair_failed',
                        'stop_ack_broker_covered','stop_remediation_skipped_pending_exit','full_exit_committed')
       OR (a.event_type='stop_order_id_changed' AND a.detail::jsonb->>'reason' IN ('restored_after_failed_full_exit','partial_naked','sync_coverage_repair','stop_ack_timeout','watchdog_synced_from_broker')))
ORDER BY a.created_at;

-- V5d: order-mirror cross-check, 150 live position-slots: is a live stop_loss sell order alive at the slot instant?
WITH days AS (SELECT d::date AS d FROM generate_series('2026-09-14'::date,'2026-10-12'::date,'1 day') g(d) WHERE extract(isodow FROM d)<6),
slots AS (SELECT d, nm, ((d + t) AT TIME ZONE 'America/New_York') AS ts FROM days,
          (VALUES ('1700', time '17:00'),('1900', time '19:00'),('2110', time '21:10')) s(nm,t)),
ps AS (SELECT s.d, s.nm, s.ts, t.id AS trade_id, t.ticker FROM slots s JOIN mi_live_trades t
       ON t.account_mode='live' AND t.filled_at < s.ts AND (t.closed_at IS NULL OR t.closed_at > s.ts))
SELECT count(*) AS position_slots,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM mi_live_orders o WHERE o.trade_id=ps.trade_id AND o.purpose='stop_loss' AND o.side ILIKE '%sell%'
        AND o.submitted_at < ps.ts AND (o.cancelled_at IS NULL OR o.cancelled_at > ps.ts) AND (o.filled_at IS NULL OR o.filled_at > ps.ts))) AS mirror_alive_any,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM mi_live_orders o WHERE o.trade_id=ps.trade_id AND o.purpose='stop_loss' AND o.side ILIKE '%sell%'
        AND o.status NOT IN ('replaced')
        AND o.submitted_at < ps.ts AND (o.cancelled_at IS NULL OR o.cancelled_at > ps.ts) AND (o.filled_at IS NULL OR o.filled_at > ps.ts))) AS mirror_alive_excl_replaced,
  string_agg(ps.ticker||'@'||ps.d||' '||ps.nm, ', ') FILTER (WHERE NOT EXISTS (SELECT 1 FROM mi_live_orders o WHERE o.trade_id=ps.trade_id AND o.purpose='stop_loss' AND o.side ILIKE '%sell%'
        AND o.status NOT IN ('replaced')
        AND o.submitted_at < ps.ts AND (o.cancelled_at IS NULL OR o.cancelled_at > ps.ts) AND (o.filled_at IS NULL OR o.filled_at > ps.ts))) AS not_alive_excl_replaced
FROM ps;

-- V5e: qty check — at each live position-slot, sum of alive stop qty (excl replaced) vs remaining shares now-or-then (entry_shares minus exits before ts)
WITH days AS (SELECT d::date AS d FROM generate_series('2026-09-14'::date,'2026-10-12'::date,'1 day') g(d) WHERE extract(isodow FROM d)<6),
slots AS (SELECT d, nm, ((d + t) AT TIME ZONE 'America/New_York') AS ts FROM days,
          (VALUES ('1700', time '17:00'),('1900', time '19:00'),('2110', time '21:10')) s(nm,t)),
ps AS (SELECT s.d, s.nm, s.ts, t.id AS trade_id, t.ticker, t.entry_shares,
              coalesce((SELECT sum((e->>'shares')::numeric) FROM jsonb_array_elements(coalesce(t.exits,'[]'::jsonb)) e
                        WHERE (e->>'time')::timestamptz < s.ts),0) AS sold_before
       FROM slots s JOIN mi_live_trades t ON t.account_mode='live' AND t.filled_at < s.ts AND (t.closed_at IS NULL OR t.closed_at > s.ts)),
q AS (SELECT ps.*, (SELECT coalesce(sum(o.qty),0) FROM mi_live_orders o WHERE o.trade_id=ps.trade_id AND o.purpose='stop_loss' AND o.side ILIKE '%sell%'
        AND o.status NOT IN ('replaced') AND o.submitted_at < ps.ts AND (o.cancelled_at IS NULL OR o.cancelled_at > ps.ts) AND (o.filled_at IS NULL OR o.filled_at > ps.ts)) AS stop_qty
      FROM ps)
SELECT ticker, count(*) AS slots, min(entry_shares - sold_before) AS held_min, max(entry_shares - sold_before) AS held_max,
       min(stop_qty) AS stopq_min, max(stop_qty) AS stopq_max,
       count(*) FILTER (WHERE stop_qty < entry_shares - sold_before - 0.5) AS under_covered_slots
FROM q GROUP BY 1 ORDER BY 1;

-- V5f: PnL + exits of the three overnight stop fills
SELECT id, ticker, total_pnl, exits FROM mi_live_trades WHERE id IN (392,382,400);
