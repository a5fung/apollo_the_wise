SELECT 'A' q, to_char(date_trunc('month', created_at AT TIME ZONE 'America/New_York'),'YYYY-MM') k, event_type k2, COUNT(*)::text v
FROM mi_audit_log WHERE event_type LIKE '%flag%' AND created_at >= '2026-05-01' GROUP BY 2,3
UNION ALL
SELECT 'B', (created_at AT TIME ZONE 'America/New_York')::date::text, summary, left(detail,300)
FROM mi_audit_log WHERE event_type='flag_stage_transition'
UNION ALL
SELECT 'C', (created_at AT TIME ZONE 'America/New_York')::text, event_type||' | '||summary, left(detail,200)
FROM mi_audit_log WHERE (created_at AT TIME ZONE 'America/New_York')::date IN ('2026-08-18','2026-08-19','2026-08-25') AND (summary ILIKE '%CDNA%' OR detail ILIKE '%CDNA%' OR event_type LIKE '%flag%')
UNION ALL
SELECT 'D', run_date::text, job_name, ran_at::text FROM mi_job_log WHERE job_name ILIKE '%flag%' AND run_date IN ('2026-08-18','2026-08-19','2026-08-25','2026-09-16','2026-09-17')
UNION ALL
SELECT 'E', break_date::text, ticker||' '||parent_stage, 'bh='||base_high||' px='||break_price||' inv='||COALESCE(parent_invalidated_eod::text,'?') FROM mi_flag_breaks WHERE ticker IN ('CDNA','HNGE','MRNA')
UNION ALL
SELECT 'F', 'event_types_cmd', event_type, COUNT(*)::text FROM mi_audit_log WHERE (event_type ILIKE '%command%' OR event_type ILIKE '%telegram%' OR summary ILIKE '%/flags%' OR summary ILIKE '%/htf%') AND created_at >= '2026-05-01' GROUP BY event_type
UNION ALL
SELECT 'G', 'flag_breaks_by_month', to_char(break_date,'YYYY-MM'), COUNT(*)::text FROM mi_flag_breaks GROUP BY 3
UNION ALL
SELECT 'H', 'job_runs_cols', (SELECT string_agg(column_name,',') FROM information_schema.columns WHERE table_name='mi_job_runs'), ''
ORDER BY 1,2,3;
