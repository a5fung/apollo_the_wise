SET default_transaction_read_only = on;
SELECT scan_date, stage, count(*), count(base_low) with_base_low FROM mi_flag_candidates WHERE scan_date IN ('2026-08-21','2026-09-15','2026-11-10') GROUP BY 1,2 ORDER BY 1,2;
