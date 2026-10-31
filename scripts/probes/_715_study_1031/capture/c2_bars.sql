-- #715 (2026-10-31) — capture 2 of 2: the STORED BARS for the population c1 defined. READ-ONLY, $0,
-- run ONCE; the output (~20k minute rows + ~6k daily rows) is reproducible from this file and is NOT
-- to be committed — no existing .gitignore rule covers probe .out files (checked 10-31 with
-- `git check-ignore`), so add `scripts/probes/_715_study_1031/capture/c2_bars.out` at commit time.
--
--   ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|'" \
--     < scripts/probes/_715_study_1031/capture/c2_bars.sql \
--     > scripts/probes/_715_study_1031/capture/c2_bars.out
--
-- BOUNDED to the population: MIN = the 51 ticker-days' 1-minute bars 09:30-16:00 ET (the whole
-- session, not "from the crossing": the crossing bar is DEFINED offline in stage 2 from these bars,
-- so a definition change never re-pulls; the fill-day walk needs the bars through the close anyway).
-- DAILY = the 51 tickers' daily rows 2026-06-01 .. today: 60 calendar days before the earliest
-- alert covers the ADR20 window (≤20 sessions), the trail's prior closes (40 cal days) and ATR14
-- (35 cal days); after the alert it covers the 40-session walk horizon for every settled session.
-- The POP CTE is VERBATIM c1_population.sql / q3_flipups.sql.
SET default_transaction_read_only = on;
\set ON_ERROR_STOP off
\pset footer off

\echo === MIN ===
WITH f AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d, substring(summary from '^([A-Z.]{1,6}) ') AS t
  FROM mi_audit_log WHERE event_type = 'ep_rt_floor_flip_up' AND created_at >= '2026-08-02'
), pop AS (
  SELECT f.d, f.t FROM f
  JOIN (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts WHERE score_tier='HIGH') a ON a.ticker = f.t AND a.alert_date = f.d
)
SELECT p.t AS ticker, p.d AS d,
       to_char(b.bar_time AT TIME ZONE 'America/New_York', 'HH24:MI') AS hhmm,
       b.open, b.high, b.low, b.close, b.volume, b.vwap
FROM pop p
JOIN mi_intraday_bars b ON b.ticker = p.t
  AND b.bar_time >= ((p.d::text || ' 09:30')::timestamp AT TIME ZONE 'America/New_York')
  AND b.bar_time <  ((p.d::text || ' 16:00')::timestamp AT TIME ZONE 'America/New_York')
ORDER BY p.d, p.t, b.bar_time;

\echo === DAILY ===
WITH f AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d, substring(summary from '^([A-Z.]{1,6}) ') AS t
  FROM mi_audit_log WHERE event_type = 'ep_rt_floor_flip_up' AND created_at >= '2026-08-02'
), pop AS (
  SELECT f.d, f.t FROM f
  JOIN (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts WHERE score_tier='HIGH') a ON a.ticker = f.t AND a.alert_date = f.d
), tk AS (SELECT DISTINCT t AS ticker FROM pop)
SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close, d.volume
FROM tk JOIN mi_daily_closes d ON d.ticker = tk.ticker
WHERE d.trade_date BETWEEN '2026-06-01' AND current_date
ORDER BY d.ticker, d.trade_date;

\echo === MINCOUNT ===
-- the row count stage 2 asserts against MIN (a truncated transfer must be loud, never a short walk)
WITH f AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d, substring(summary from '^([A-Z.]{1,6}) ') AS t
  FROM mi_audit_log WHERE event_type = 'ep_rt_floor_flip_up' AND created_at >= '2026-08-02'
), pop AS (
  SELECT f.d, f.t FROM f
  JOIN (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts WHERE score_tier='HIGH') a ON a.ticker = f.t AND a.alert_date = f.d
)
SELECT count(*) AS min_rows, count(DISTINCT (p.d, p.t)) AS ticker_days_with_bars
FROM pop p
JOIN mi_intraday_bars b ON b.ticker = p.t
  AND b.bar_time >= ((p.d::text || ' 09:30')::timestamp AT TIME ZONE 'America/New_York')
  AND b.bar_time <  ((p.d::text || ' 16:00')::timestamp AT TIME ZONE 'America/New_York');
