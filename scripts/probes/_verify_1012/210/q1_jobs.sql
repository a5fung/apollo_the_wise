\echo === Q1a mi_job_runs tv_news_shadow last 14 rows
SELECT * FROM (
  SELECT job_name, started_at AT TIME ZONE 'America/New_York' AS started_et, status, left(coalesce(result_summary,''),200) AS summ
  FROM mi_job_runs WHERE job_name='tv_news_shadow' ORDER BY started_at DESC LIMIT 14
) x;
