-- last 60 distinct scan dates: per-day stage counts
WITH days AS (SELECT DISTINCT scan_date FROM mi_flag_candidates ORDER BY scan_date DESC LIMIT 60)
SELECT scan_date, COUNT(*) total,
  SUM((stage='unqualified')::int) unq, SUM((stage='INVALIDATED')::int) inv, SUM((stage='WATCH')::int) watch,
  SUM((stage='TIGHTENING')::int) tight, SUM((stage='COILED')::int) coiled, SUM((stage='TRIGGERED')::int) trig,
  SUM((reason LIKE 'mna_filter:%')::int) mna
FROM mi_flag_candidates WHERE scan_date IN (SELECT scan_date FROM days)
GROUP BY scan_date ORDER BY scan_date;
