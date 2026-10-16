-- READ-ONLY. IBP: RS history, and did the theme engine run before tonight's RS rows existed?
SELECT score_date, round(rs_composite::numeric,1) AS rs FROM mi_stock_scores WHERE ticker='IBP' AND score_date >= '2026-10-05' ORDER BY score_date DESC;
SELECT theme_date, min(created_at) AS first_row, max(created_at) AS last_row FROM mi_themes WHERE theme_date >= '2026-10-15' GROUP BY 1 ORDER BY 1;
SELECT job_id, started_at, finished_at, status FROM mi_job_runs WHERE started_at >= '2026-10-16 18:00+00' AND (job_id ILIKE '%theme%' OR job_id ILIKE '%score%' OR job_id ILIKE '%rs%' OR job_id ILIKE '%nightly%') ORDER BY started_at;
