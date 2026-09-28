-- #684 ADDENDUM — one row per population member: re-derived ORB (09:30-09:44, cross-check vs
-- orb.tsv), FILL detection in [09:45,10:00) against that SAME re-derived orb_high (same feed,
-- avoids mixing mi_intraday_bars vs mi_daily_closes for the trigger level), fill time, and the
-- max high from the fill bar through the end of the gap day (still mi_intraday_bars, same feed).
-- Read-only, $0. Population = the exact same POP CTE as extract.sh (verbatim).
\pset format unaligned
\pset fieldsep '|'
\pset footer off
WITH sess AS (SELECT trade_date FROM mi_daily_closes GROUP BY trade_date HAVING count(*) >= 500),
last_ok AS (SELECT max(s.trade_date) AS d FROM sess s WHERE (SELECT count(*) FROM sess s2 WHERE s2.trade_date > s.trade_date) >= 15),
raw AS (SELECT l.* FROM mi_ep_scan_log l WHERE l.scan_date BETWEEN DATE '2026-05-01' AND (SELECT d FROM last_ok) AND l.ep_score IS NOT NULL),
pop AS (SELECT DISTINCT ON (r.ticker, r.scan_date) r.* FROM raw r
        ORDER BY r.ticker, r.scan_date, (r.filter_reason IS NULL AND r.score_tier IS NOT NULL) DESC, r.ep_score DESC, r.scan_time_et DESC)
SELECT p.ticker, p.scan_date,
  o.n0930, o.orb2_high, o.orb2_low,
  f.n0945, f.fill_hhmm, f.touch_count,
  m.post_fill_max_high, m.post_fill_n_bars,
  d.day_n_bars
FROM pop p
LEFT JOIN LATERAL (
  SELECT count(*) AS n0930, max(high) AS orb2_high, min(low) AS orb2_low
  FROM mi_intraday_bars b WHERE b.ticker = p.ticker
    AND b.bar_time >= ((p.scan_date::text||' 09:30')::timestamp AT TIME ZONE 'America/New_York')
    AND b.bar_time <  ((p.scan_date::text||' 09:45')::timestamp AT TIME ZONE 'America/New_York')
) o ON TRUE
LEFT JOIN LATERAL (
  SELECT count(*) AS n0945,
         to_char(min(b.bar_time) FILTER (WHERE o.orb2_high IS NOT NULL AND b.high >= o.orb2_high) AT TIME ZONE 'America/New_York', 'HH24:MI:SS') AS fill_hhmm,
         count(*) FILTER (WHERE o.orb2_high IS NOT NULL AND b.high >= o.orb2_high) AS touch_count
  FROM mi_intraday_bars b WHERE b.ticker = p.ticker
    AND b.bar_time >= ((p.scan_date::text||' 09:45')::timestamp AT TIME ZONE 'America/New_York')
    AND b.bar_time <  ((p.scan_date::text||' 10:00')::timestamp AT TIME ZONE 'America/New_York')
) f ON TRUE
LEFT JOIN LATERAL (
  SELECT max(b.high) AS post_fill_max_high, count(*) AS post_fill_n_bars
  FROM mi_intraday_bars b WHERE b.ticker = p.ticker
    AND f.fill_hhmm IS NOT NULL
    AND b.bar_time >= ((p.scan_date::text||' '||f.fill_hhmm)::timestamp AT TIME ZONE 'America/New_York')
    AND b.bar_time <  ((p.scan_date+1)::timestamp AT TIME ZONE 'America/New_York')
) m ON TRUE
LEFT JOIN LATERAL (
  SELECT count(*) AS day_n_bars
  FROM mi_intraday_bars b WHERE b.ticker = p.ticker
    AND b.bar_time >= (p.scan_date::timestamp AT TIME ZONE 'America/New_York')
    AND b.bar_time <  ((p.scan_date+1)::timestamp AT TIME ZONE 'America/New_York')
) d ON TRUE
ORDER BY p.scan_date, p.ticker;
