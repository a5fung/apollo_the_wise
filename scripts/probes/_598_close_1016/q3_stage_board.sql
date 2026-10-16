-- scan dates since 10-03 with stage counts; then COILED names; then TIGHTENING names
SELECT scan_date, stage, count(*) n
FROM mi_flag_candidates WHERE scan_date >= '2026-10-03'
GROUP BY 1,2 ORDER BY 1,2;
SELECT '--- COILED/TRIGGERED rows since 10-04 ---' AS x;
SELECT scan_date, ticker, stage, base_age, round(runup_pct::numeric,3) runup, pivot_high_price pivot,
       round(range_contraction_ratio::numeric,2) rng, round(vol_contraction_ratio::numeric,2) vol, held_from_stage, reason
FROM mi_flag_candidates WHERE scan_date >= '2026-10-04' AND stage IN ('COILED','TRIGGERED')
ORDER BY scan_date, stage, ticker;
SELECT '--- TIGHTENING names with first/last scan since 10-04 ---' AS x;
SELECT ticker, min(scan_date) first_scan, max(scan_date) last_scan, count(*) days
FROM mi_flag_candidates WHERE scan_date >= '2026-10-04' AND stage='TIGHTENING'
GROUP BY 1 ORDER BY 2,1;
