-- #559 era-D re-cut (2026-10-10) — capture 2 of 2: STORED bars for the population capture 1 defined
-- (event union ∪ alerts ∪ trades, alert days 2026-09-08..2026-10-09). READ-ONLY, $0, run ONCE.
-- Output is >1MB and is NOT committed (.gitignore); it is reproducible from this file.
\set ON_ERROR_STOP off
\pset footer on

\echo === MIN ===
WITH ev AS (
  SELECT DISTINCT detail::json->>'ticker' AS ticker,
         (created_at AT TIME ZONE 'America/New_York')::date AS d
  FROM mi_audit_log
  WHERE event_type IN ('ep_rt_universe_catch','ep_rt_floor_flip_up','ep_rt_admit','ep_rt_live_miss')
    AND (created_at AT TIME ZONE 'America/New_York')::date BETWEEN '2026-09-08' AND '2026-10-09'
), al AS (
  SELECT ticker, alert_date AS d FROM mi_ep_alerts WHERE alert_date BETWEEN '2026-09-08' AND '2026-10-09'
), tr AS (
  SELECT ticker, alert_date AS d FROM mi_live_trades WHERE alert_date BETWEEN '2026-09-08' AND '2026-10-09'
), pairs AS (SELECT * FROM ev UNION SELECT * FROM al UNION SELECT * FROM tr)
SELECT b.ticker,
       to_char(b.bar_time AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI') AS et_min,
       b.open, b.high, b.low, b.close, b.volume
FROM mi_intraday_bars b
JOIN pairs p ON p.ticker = b.ticker
 AND (b.bar_time AT TIME ZONE 'America/New_York')::date = p.d
 AND (b.bar_time AT TIME ZONE 'America/New_York')::time >= '09:30'
 AND (b.bar_time AT TIME ZONE 'America/New_York')::time < '16:00'
ORDER BY b.ticker, b.bar_time;

\echo === DAILY ===
WITH ev AS (
  SELECT DISTINCT detail::json->>'ticker' AS ticker
  FROM mi_audit_log
  WHERE event_type IN ('ep_rt_universe_catch','ep_rt_floor_flip_up','ep_rt_admit','ep_rt_live_miss')
    AND (created_at AT TIME ZONE 'America/New_York')::date BETWEEN '2026-09-08' AND '2026-10-09'
), al AS (
  SELECT DISTINCT ticker FROM mi_ep_alerts WHERE alert_date BETWEEN '2026-09-08' AND '2026-10-09'
), tr AS (
  SELECT DISTINCT ticker FROM mi_live_trades WHERE alert_date BETWEEN '2026-09-08' AND '2026-10-09'
), tk AS (SELECT * FROM ev UNION SELECT * FROM al UNION SELECT * FROM tr)
SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close, d.volume
FROM mi_daily_closes d JOIN tk USING (ticker)
WHERE d.trade_date BETWEEN '2026-06-01' AND '2026-10-09'
ORDER BY d.ticker, d.trade_date;
