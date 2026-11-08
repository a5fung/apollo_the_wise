SET default_transaction_read_only = on;
-- the detector's candidates this week by stage (what the shadow arms from)
SELECT scan_date, stage, count(*) FROM mi_parabolic_candidates WHERE scan_date > DATE '2026-10-30' GROUP BY 1,2 ORDER BY 1,2;
