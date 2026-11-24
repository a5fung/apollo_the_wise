SET default_transaction_read_only = on;
SELECT count(DISTINCT scan_date) scans, min(scan_date), max(scan_date) FROM mi_flag_candidates WHERE scan_date >= '2026-10-12';
SELECT stage, held_from_stage IS NOT NULL held, triggered_from, count(*) FROM mi_flag_candidates WHERE scan_date >= '2026-10-12' GROUP BY 1,2,3 ORDER BY 1,2,3;
SELECT scan_date, stage, count(*) FROM mi_flag_candidates WHERE scan_date >= '2026-11-16' GROUP BY 1,2 ORDER BY 1,2;
