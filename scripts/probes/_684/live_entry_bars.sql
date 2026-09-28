-- #684 ADDENDUM v2 — full-day 1-minute bars (09:30-16:00 ET) for every population row, so the
-- live MAGNA53 entry mechanics (entry_pipeline.fetch_orb_bar_with_retry / order_manager's single
-- 09:30 bar ORB / entry_walk's stop-limit-buy trigger walk) can be replayed bar-by-bar in Python,
-- not approximated from a 15-minute aggregate. Read-only, $0. Population = the exact same POP CTE
-- as extract.sh (verbatim). One row per (ticker, scan_date, minute).
\pset format unaligned
\pset fieldsep '|'
\pset footer off
WITH sess AS (SELECT trade_date FROM mi_daily_closes GROUP BY trade_date HAVING count(*) >= 500),
last_ok AS (SELECT max(s.trade_date) AS d FROM sess s WHERE (SELECT count(*) FROM sess s2 WHERE s2.trade_date > s.trade_date) >= 15),
raw AS (SELECT l.* FROM mi_ep_scan_log l WHERE l.scan_date BETWEEN DATE '2026-05-01' AND (SELECT d FROM last_ok) AND l.ep_score IS NOT NULL),
pop AS (SELECT DISTINCT ON (r.ticker, r.scan_date) r.* FROM raw r
        ORDER BY r.ticker, r.scan_date, (r.filter_reason IS NULL AND r.score_tier IS NOT NULL) DESC, r.ep_score DESC, r.scan_time_et DESC)
SELECT p.ticker, p.scan_date, to_char(b.bar_time AT TIME ZONE 'America/New_York', 'HH24:MI') AS hhmm,
       b.open, b.high, b.low
FROM pop p
JOIN mi_intraday_bars b ON b.ticker = p.ticker
  AND b.bar_time >= ((p.scan_date::text||' 09:30')::timestamp AT TIME ZONE 'America/New_York')
  AND b.bar_time <  ((p.scan_date::text||' 16:00')::timestamp AT TIME ZONE 'America/New_York')
ORDER BY p.scan_date, p.ticker, b.bar_time;
