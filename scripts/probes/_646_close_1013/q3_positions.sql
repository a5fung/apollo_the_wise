\pset pager off
\pset null '-'
-- (a) account_mode census, ALL TIME
SELECT account_mode, status, count(*) AS n, min(alert_date) AS first_alert, max(alert_date) AS last_alert,
       count(*) FILTER (WHERE filled_at IS NOT NULL) AS ever_filled, count(*) FILTER (WHERE remaining_shares>0) AS rem_pos_now
FROM mi_live_trades GROUP BY 1,2 ORDER BY 1,2;

-- (b) every trade filled at/before the window end that was still open at any point on/after 2026-09-14
SELECT id, ticker, account_mode, status, signal_type,
       filled_at AT TIME ZONE 'America/New_York' AS filled_et, closed_at AT TIME ZONE 'America/New_York' AS closed_et,
       entry_shares, remaining_shares, (stop_order_id IS NOT NULL) AS stop_ptr_now, exit_rule, jsonb_array_length(coalesce(exits,'[]'::jsonb)) AS n_exits
FROM mi_live_trades
WHERE filled_at IS NOT NULL AND (closed_at IS NULL OR closed_at >= '2026-09-14') AND filled_at < '2026-10-13 12:00+00'
ORDER BY filled_at;

-- (c) per night, per slot: positions held (filled_at < slot AND not closed by slot), by account_mode
WITH days AS (
  SELECT d::date AS d FROM generate_series('2026-09-14'::date,'2026-10-12'::date,'1 day') g(d) WHERE extract(isodow FROM d) < 6
), slots AS (
  SELECT d, nm, ((d + t) AT TIME ZONE 'America/New_York') AS ts FROM days, (VALUES ('1700', time '17:00'),('1900', time '19:00'),('2110', time '21:10')) s(nm,t)
), held AS (
  SELECT slots.d, slots.nm, t.account_mode, t.ticker FROM slots JOIN mi_live_trades t
    ON t.filled_at IS NOT NULL AND t.filled_at < slots.ts AND (t.closed_at IS NULL OR t.closed_at > slots.ts)
)
SELECT d, to_char(d,'Dy') AS dow,
  count(*) FILTER (WHERE nm='1700' AND account_mode='live') AS live_1700, count(*) FILTER (WHERE nm='1900' AND account_mode='live') AS live_1900, count(*) FILTER (WHERE nm='2110' AND account_mode='live') AS live_2110,
  count(*) FILTER (WHERE nm='2110' AND account_mode<>'live') AS nonlive_2110,
  string_agg(DISTINCT ticker, ',') FILTER (WHERE nm='2110' AND account_mode='live') AS live_tickers_2110
FROM held GROUP BY d ORDER BY d;

-- (d) order-mirror vocabulary for live trades since 09-12 (sell side)
SELECT purpose, order_type, status, count(*) AS n, count(*) FILTER (WHERE cancelled_at IS NULL) AS cancelled_at_null, count(*) FILTER (WHERE filled_at IS NULL) AS filled_at_null
FROM mi_live_orders o JOIN mi_live_trades t ON t.id=o.trade_id
WHERE t.account_mode='live' AND o.submitted_at >= '2026-09-10' AND o.side ILIKE 'sell%'
GROUP BY 1,2,3 ORDER BY 1,2,3;
