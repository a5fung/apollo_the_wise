-- READ-ONLY. Confirm-fire rate by week since August, and the job's own run ledger for the last 20 days.
SELECT date_trunc('week', entry_date)::date AS wk, entry_mode, count(*) FROM mi_consolidation_entry_shadow
WHERE entry_date >= '2026-08-01' GROUP BY 1,2 ORDER BY 1,2;
SELECT started_at::date AS d, status, rows_written, round(duration_s) AS secs
FROM mi_job_runs WHERE job_id='consolidation_readiness' AND started_at >= now() - interval '22 days' ORDER BY started_at;
SELECT entry_date, ticker, round(vol_ratio::numeric,2) AS vol_ratio, round(range_pct::numeric,3) AS range_pct
FROM mi_consolidation_entry_shadow WHERE entry_date >= '2026-09-20' ORDER BY entry_date;
