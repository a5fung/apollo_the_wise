-- what the board did the scan day AFTER a TIGHTENING/COILED/TRIGGERED row (last 60 scan dates)
WITH days AS (SELECT DISTINCT scan_date FROM mi_flag_candidates ORDER BY scan_date DESC LIMIT 60),
w AS (SELECT ticker, scan_date, stage, base_age, pivot_high_date, pivot_high_price, reason,
        LEAD(scan_date) OVER (PARTITION BY ticker ORDER BY scan_date) nd,
        LEAD(stage) OVER (PARTITION BY ticker ORDER BY scan_date) ns,
        LEAD(base_age) OVER (PARTITION BY ticker ORDER BY scan_date) na,
        LEAD(pivot_high_price) OVER (PARTITION BY ticker ORDER BY scan_date) np,
        LEAD(reason) OVER (PARTITION BY ticker ORDER BY scan_date) nr
      FROM mi_flag_candidates WHERE scan_date >= (SELECT MIN(scan_date) FROM days))
SELECT ticker, scan_date, stage, base_age, pivot_high_price, nd, ns, na, np, left(nr,60) nr
FROM w WHERE stage IN ('TIGHTENING','COILED','TRIGGERED') AND scan_date IN (SELECT scan_date FROM days)
ORDER BY ticker, scan_date;
