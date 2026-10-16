-- READ-ONLY. #598 zero arm: did the FLAG scan's buyout screen run each night? Per scan date since 10-05: screened-stage
-- flag rows, and screen activity inside the flag scan's own window (17:25:00-17:34:59 ET; the coil scan is 17:35).
WITH d AS (SELECT DISTINCT scan_date FROM mi_flag_candidates WHERE scan_date >= '2026-10-05')
SELECT d.scan_date,
  (SELECT count(*) FROM mi_flag_candidates f WHERE f.scan_date=d.scan_date AND f.stage IN ('TIGHTENING','COILED','TRIGGERED')) AS screened_stage_rows,
  (SELECT string_agg(DISTINCT f.ticker, ',') FROM mi_flag_candidates f WHERE f.scan_date=d.scan_date AND f.stage IN ('TIGHTENING','COILED','TRIGGERED')) AS tickers,
  (SELECT count(*) FROM mi_audit_log a WHERE a.event_type LIKE 'mna%' AND (a.created_at AT TIME ZONE 'America/New_York')::date=d.scan_date
      AND (a.created_at AT TIME ZONE 'America/New_York')::time BETWEEN '17:25' AND '17:34:59') AS mna_rows_in_flag_window,
  (SELECT count(*) FROM api_usage u WHERE u.caller='mna_headline_question' AND (u.created_at AT TIME ZONE 'America/New_York')::date=d.scan_date
      AND (u.created_at AT TIME ZONE 'America/New_York')::time BETWEEN '17:25' AND '17:34:59') AS headline_calls_in_flag_window,
  (SELECT min((j.started_at AT TIME ZONE 'America/New_York')::time) FROM mi_job_runs j WHERE j.job_id ILIKE '%flag%' AND (j.started_at AT TIME ZONE 'America/New_York')::date=d.scan_date) AS flag_job_start_et
FROM d ORDER BY 1;
SELECT DISTINCT job_id FROM mi_job_runs WHERE job_id ILIKE '%flag%' AND started_at >= '2026-10-12';
