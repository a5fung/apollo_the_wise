-- #312 Step A fix round (review findings 2 + 3). READ-ONLY. Captured once 2026-10-10.
\echo === A. status vocabulary of mi_live_trades by account_mode (which statuses can a closed row carry?) ===
SELECT account_mode, status, COUNT(*) AS n, COUNT(closed_at) AS with_closed_at, COUNT(confirmed_at) AS with_confirmed_at
FROM mi_live_trades GROUP BY account_mode, status ORDER BY account_mode, status;

\echo === B. 2026-10-09: the allocator audit row the 09:35 run wrote (finding 3 baseline) ===
SELECT (created_at AT TIME ZONE 'America/New_York') AS et, summary, detail
FROM mi_audit_log
WHERE event_type = 'unified_allocation_decided'
  AND (created_at AT TIME ZONE 'America/New_York')::date = DATE '2026-10-09';

\echo === C. 2026-10-09: the #687 paper rehearsal events (rows deleted 09:41) ===
SELECT (created_at AT TIME ZONE 'America/New_York') AS et, event_type, summary
FROM mi_audit_log
WHERE (created_at AT TIME ZONE 'America/New_York')::date = DATE '2026-10-09'
  AND (summary ILIKE '%rehearsal%' OR event_type ILIKE '%rehearsal%')
ORDER BY created_at;

\echo === D. live rows that were open at 2026-10-09 09:35 ET (alert_date, mode, status, confirmed/closed ET) ===
SELECT id, ticker, account_mode, status, alert_date,
       (confirmed_at AT TIME ZONE 'America/New_York') AS confirmed_et,
       (closed_at AT TIME ZONE 'America/New_York') AS closed_et
FROM mi_live_trades
WHERE account_mode = 'live'
  AND alert_date <= DATE '2026-10-09'
  AND confirmed_at < (DATE '2026-10-09' + TIME '09:35') AT TIME ZONE 'America/New_York'
  AND (closed_at IS NULL OR closed_at >= (DATE '2026-10-09' + TIME '09:35') AT TIME ZONE 'America/New_York')
  AND status NOT IN ('cancelled','skipped')
ORDER BY alert_date, id;

\echo === E. paper rows that exist at all with id 417/418 (deleted -> expect 0 rows) ===
SELECT id, ticker, account_mode, status, alert_date FROM mi_live_trades WHERE id IN (417, 418);

\echo === F. the two check queries per allocator-audit day: CHECK-TIME status count vs the 09:28 book rebuilt from timestamps ===
\echo     naive = status IN open AND live AND alert_date < D, evaluated NOW (the flawed cross-check)
\echo     rebuilt = live AND alert_date < D AND confirmed_at < D 09:28 ET AND (closed_at IS NULL OR closed_at >= D 09:28 ET) AND status NOT IN (cancelled, skipped)
WITH days AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d
  FROM mi_audit_log
  WHERE event_type = 'unified_allocation_decided' AND created_at > NOW() - INTERVAL '60 days'
)
SELECT d.d,
  (SELECT COUNT(*) FROM mi_live_trades t
    WHERE t.status IN ('filled','order_placed','confirmed') AND t.account_mode = 'live' AND t.alert_date < d.d) AS naive_status_now,
  (SELECT COUNT(*) FROM mi_live_trades t
    WHERE t.account_mode = 'live' AND t.alert_date < d.d
      AND t.confirmed_at < (d.d + TIME '09:28') AT TIME ZONE 'America/New_York'
      AND (t.closed_at IS NULL OR t.closed_at >= (d.d + TIME '09:28') AT TIME ZONE 'America/New_York')
      AND t.status NOT IN ('cancelled','skipped')) AS rebuilt_0928,
  (SELECT a.detail::jsonb->>'open_positions' FROM mi_audit_log a
    WHERE a.event_type = 'unified_allocation_decided'
      AND (a.created_at AT TIME ZONE 'America/New_York')::date = d.d ORDER BY a.created_at LIMIT 1) AS audit_open_positions
FROM days d ORDER BY d.d;
