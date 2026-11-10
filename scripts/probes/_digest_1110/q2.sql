SET default_transaction_read_only = on;
SELECT started_at::date d, count(*) runs, count(*) FILTER (WHERE status='success') ok, sum(rows_written) rows, max(error_message) err
FROM mi_job_runs WHERE job_id='undercut_rally_scan' AND started_at >= NOW() - INTERVAL '10 days' GROUP BY 1 ORDER BY 1;
SELECT ur_date, ticker FROM mi_flag_undercut_rally ORDER BY ur_date;
