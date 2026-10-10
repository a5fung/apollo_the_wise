SELECT 'jobrun' q, job_id, scheduled_for::text, status, rows_written::text, left(COALESCE(error_message,''),80) FROM mi_job_runs WHERE job_id ILIKE '%flag%' AND scheduled_for >= '2026-08-17' AND scheduled_for < '2026-08-27' 
UNION ALL SELECT 'jobrun_ids', job_id, MIN(scheduled_for)::text, MAX(scheduled_for)::text, COUNT(*)::text, '' FROM mi_job_runs WHERE job_id ILIKE '%flag%' OR job_id ILIKE '%close_digest%' OR job_id ILIKE '%friday%' OR job_id ILIKE '%watchlist%' GROUP BY job_id
UNION ALL SELECT 'joblog', job_name, MIN(run_date)::text, MAX(run_date)::text, COUNT(*)::text, '' FROM mi_job_log WHERE job_name ILIKE '%flag%' OR job_name ILIKE '%friday%' OR job_name ILIKE '%watchlist%' OR job_name ILIKE '%close%' GROUP BY job_name
UNION ALL SELECT 'stage_0818', ticker, stage, reason, '', '' FROM mi_flag_candidates WHERE scan_date='2026-08-18' AND stage IN ('TIGHTENING','COILED','TRIGGERED')
UNION ALL SELECT 'stage_0817', ticker, stage, reason, '', '' FROM mi_flag_candidates WHERE scan_date='2026-08-17' AND stage IN ('TIGHTENING','COILED','TRIGGERED')
UNION ALL SELECT 'hpe_scores', ticker, score_date::text, rs_rank::text, rs_1m::text, '' FROM mi_stock_scores WHERE ticker='HPE' AND score_date BETWEEN '2026-06-15' AND '2026-07-17'
ORDER BY 1,2,3;
