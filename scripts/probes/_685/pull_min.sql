-- #685 — minute bars (gzipped on capture). Two sets, one file, sections read by ep_replay.read_sections-style parsing.
-- MIN_DAY0: the entry-day bars of every live alert since 2026-09-01 (the day-0 walk).
-- MIN_SEP:  every stored bar in September 2026 for the cohort (held-session line tests + the OKTA day).
\echo === MIN_DAY0 ===
WITH pairs AS (
  SELECT DISTINCT ticker, alert_date AS d FROM mi_ep_alerts WHERE COALESCE(source,'live')='live' AND alert_date >= '2026-09-01'
)
SELECT b.ticker, to_char(b.bar_time AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') AS m, b.open, b.high, b.low, b.close, b.volume
FROM mi_intraday_bars b JOIN pairs p ON p.ticker = b.ticker
 AND b.bar_time >= (p.d::timestamp AT TIME ZONE 'America/New_York')
 AND b.bar_time <  ((p.d+1)::timestamp AT TIME ZONE 'America/New_York')
ORDER BY b.ticker, b.bar_time;
\echo === MIN_SEP ===
WITH cohort AS (
  SELECT DISTINCT ticker FROM mi_ep_alerts WHERE COALESCE(source,'live')='live'
  UNION SELECT DISTINCT ticker FROM mi_live_trades WHERE signal_type LIKE 'magna53%'
)
SELECT b.ticker, to_char(b.bar_time AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') AS m, b.open, b.high, b.low, b.close, b.volume
FROM mi_intraday_bars b JOIN cohort c USING (ticker)
WHERE b.bar_time >= ('2026-09-01'::timestamp AT TIME ZONE 'America/New_York')
ORDER BY b.ticker, b.bar_time;
