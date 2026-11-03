-- Gap re-check retest (2026-11-03, his "Yes"): every live HIGH MAGNA53 alert since 2026-08-28 (the real-time gap
-- authoritative era), its stored trade rows (entered / skipped and why), the alert's own fields, and the bars a
-- replay needs. READ-ONLY, $0, run ONCE from the laptop; read the .out many times.
SET default_transaction_read_only = on;
\pset footer off
\echo === POP ===
WITH pop AS (SELECT DISTINCT ticker, alert_date AS d FROM mi_ep_alerts WHERE score_tier = 'HIGH' AND alert_date >= DATE '2026-08-28')
SELECT p.ticker, p.d,
       (SELECT round(max(a.ep_score)::numeric, 2) FROM mi_ep_alerts a WHERE a.ticker = p.ticker AND a.alert_date = p.d) AS ep_score,
       (SELECT round(max(a.gap_pct)::numeric, 3) FROM mi_ep_alerts a WHERE a.ticker = p.ticker AND a.alert_date = p.d) AS alert_gap_pct,
       (SELECT to_char(min(a.created_at) AT TIME ZONE 'America/New_York', 'HH24:MI') FROM mi_ep_alerts a WHERE a.ticker = p.ticker AND a.alert_date = p.d) AS first_alert_et,
       (SELECT l.prev_close FROM mi_ep_scan_log l WHERE l.ticker = p.ticker AND l.scan_date = p.d ORDER BY l.scan_time_et DESC LIMIT 1) AS scan_prev_close,
       (SELECT count(*) FROM mi_audit_log x WHERE x.event_type = 'ep_rt_floor_flip_up' AND (x.created_at AT TIME ZONE 'America/New_York')::date = p.d AND substring(x.summary from '^([A-Z.]{1,6}) ') = p.ticker) AS flip_up_rows,
       lt.id AS trade_id, lt.account_mode, lt.status, replace(replace(coalesce(lt.skip_reason, ''), '|', '¦'), E'\n', ' ') AS skip_reason,
       lt.entry_price, lt.stop_price, lt.orb_high, lt.orb_low, lt.exit_rule, lt.exits::text AS exits_json
FROM pop p
LEFT JOIN mi_live_trades lt ON lt.ticker = p.ticker AND lt.alert_date = p.d AND lt.signal_type = 'magna53'
ORDER BY p.d, p.ticker, lt.id;
\echo === MIN ===
WITH pop AS (SELECT DISTINCT ticker, alert_date AS d FROM mi_ep_alerts WHERE score_tier = 'HIGH' AND alert_date >= DATE '2026-08-28')
SELECT p.ticker, p.d, to_char(b.bar_time AT TIME ZONE 'America/New_York', 'HH24:MI') AS hhmm, b.open, b.high, b.low, b.close, b.volume, b.vwap
FROM pop p JOIN mi_intraday_bars b ON b.ticker = p.ticker
  AND b.bar_time >= ((p.d::text || ' 09:30')::timestamp AT TIME ZONE 'America/New_York')
  AND b.bar_time <  ((p.d::text || ' 16:00')::timestamp AT TIME ZONE 'America/New_York')
ORDER BY p.d, p.ticker, b.bar_time;
\echo === DAILY ===
WITH pop AS (SELECT DISTINCT ticker, alert_date AS d FROM mi_ep_alerts WHERE score_tier = 'HIGH' AND alert_date >= DATE '2026-08-28'),
tk AS (SELECT DISTINCT ticker FROM pop)
SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close, d.volume
FROM tk JOIN mi_daily_closes d ON d.ticker = tk.ticker
WHERE d.trade_date BETWEEN DATE '2026-06-15' AND current_date ORDER BY d.ticker, d.trade_date;
\echo === COUNTS ===
WITH pop AS (SELECT DISTINCT ticker, alert_date AS d FROM mi_ep_alerts WHERE score_tier = 'HIGH' AND alert_date >= DATE '2026-08-28')
SELECT (SELECT count(*) FROM pop) AS pop_ticker_days,
       (SELECT count(*) FROM pop p JOIN mi_intraday_bars b ON b.ticker = p.ticker AND b.bar_time >= ((p.d::text || ' 09:30')::timestamp AT TIME ZONE 'America/New_York') AND b.bar_time < ((p.d::text || ' 16:00')::timestamp AT TIME ZONE 'America/New_York')) AS min_rows;
