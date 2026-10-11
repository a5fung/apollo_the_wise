-- #697: which scan dates are market sessions vs not (the Labor Day artifact), and the WDAY rows.
SELECT 'scan_date' k, s.scan_date::text a, COUNT(*)::text b,
       (SELECT COUNT(*) FROM mi_daily_closes d WHERE d.trade_date = s.scan_date)::text c
FROM mi_flag_candidates s WHERE s.scan_date >= '2026-08-20' GROUP BY s.scan_date
UNION ALL
SELECT 'wday', scan_date::text, stage, COALESCE(held_from_stage,'')||' '||COALESCE(reason,'') FROM mi_flag_candidates
 WHERE ticker='WDAY' AND scan_date >= '2026-08-25'
ORDER BY 1, 2;
