-- #697 item 2 admit-count replay. READ-ONLY. Captured once -> q1_admit_replay.out
-- For each of the last 60 scan SESSIONS D (scan dates that are market sessions: a row in mi_daily_closes
-- for that date; this drops the 09-07 Labor Day partial scan), compare:
--   rows_D   = tickers the realised scan scored on D (the OLD universe, incl. the old carry)
--   old_carry= old rule: stored COILED/TIGHTENING in the last 5 CALENDAR days
--   new_carry= new rule: stored WATCH/TIGHTENING/COILED/TRIGGERED in the last 5 scan sessions
--              OR stored TIGHTENING/COILED/TRIGGERED in the last 25 scan sessions
--   extra    = new_carry NOT in rows_D  (names the new rule would ADD to that night's scan)
-- First-order: stored rows are the OLD run's rows (an extra name's own rows on earlier nights are unknown).
WITH sess AS (
  SELECT scan_date, ROW_NUMBER() OVER (ORDER BY scan_date) AS n
  FROM (SELECT DISTINCT scan_date FROM mi_flag_candidates) s
  WHERE EXISTS (SELECT 1 FROM mi_daily_closes d WHERE d.trade_date = s.scan_date)
),
tgt AS (SELECT scan_date AS d, n AS nd FROM sess WHERE n > (SELECT MAX(n) FROM sess) - 60),
src AS (
  SELECT t.d, c.ticker, c.stage, c.scan_date AS sd, t.nd - s.n AS lag
  FROM tgt t
  JOIN sess s ON s.n BETWEEN t.nd - 25 AND t.nd - 1
  JOIN mi_flag_candidates c ON c.scan_date = s.scan_date
  WHERE c.stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED')
),
newc AS (
  SELECT d, ticker,
         bool_or(stage='TRIGGERED' AND lag<=5)                     AS trig5,
         bool_or(stage IN ('TIGHTENING','COILED') AND lag<=5)      AS tight5,
         bool_or(stage='WATCH' AND lag<=5)                         AS watch5,
         bool_or(stage IN ('TIGHTENING','COILED','TRIGGERED'))     AS tight25
  FROM src
  WHERE lag <= 5 OR stage IN ('TIGHTENING','COILED','TRIGGERED')
  GROUP BY d, ticker
),
rowsd AS (SELECT c.scan_date AS d, c.ticker FROM mi_flag_candidates c WHERE c.scan_date IN (SELECT d FROM tgt)),
oldc AS (
  SELECT DISTINCT t.d, c.ticker
  FROM tgt t JOIN mi_flag_candidates c
    ON c.scan_date < t.d AND c.scan_date >= t.d - 5 AND c.stage IN ('COILED','TIGHTENING')
),
extra AS (
  SELECT n.*, CASE WHEN n.trig5 THEN 'trig5' WHEN n.tight5 THEN 'tight5' WHEN n.watch5 THEN 'watch5' ELSE 'tight25' END AS cls
  FROM newc n WHERE NOT EXISTS (SELECT 1 FROM rowsd r WHERE r.d = n.d AND r.ticker = n.ticker)
)
SELECT 'night' k, t.d::text a,
       (SELECT COUNT(*) FROM rowsd r WHERE r.d=t.d)::text b,
       (SELECT COUNT(*) FROM oldc o WHERE o.d=t.d)::text c,
       (SELECT COUNT(*) FROM newc x WHERE x.d=t.d)::text d,
       (SELECT COUNT(*) FROM extra e WHERE e.d=t.d)::text e,
       (SELECT string_agg(e.cls||':'||e.ticker, ' ' ORDER BY e.cls, e.ticker) FROM extra e WHERE e.d=t.d) f
FROM tgt t
UNION ALL
SELECT 'cls', cls, COUNT(*)::text, COUNT(DISTINCT ticker)::text, COUNT(DISTINCT d)::text, NULL, NULL FROM extra GROUP BY cls
UNION ALL
-- what each extra name's last stored qualifying stage was (for the admit-list read)
SELECT 'extra', e.d::text, e.ticker, e.cls,
       (SELECT s.stage||'@'||s.sd::text FROM src s WHERE s.d=e.d AND s.ticker=e.ticker ORDER BY s.sd DESC LIMIT 1),
       (SELECT MIN(s.lag)::text FROM src s WHERE s.d=e.d AND s.ticker=e.ticker), NULL
FROM extra e
ORDER BY 1, 2, 3;
