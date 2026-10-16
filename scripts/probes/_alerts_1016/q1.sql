-- 10-16 alerts, READ-ONLY. (1) consolidation confirm recorder silent 15d: is the coil board writing, and did the job error?
SELECT max(entry_date) AS last_entry, count(*) FILTER (WHERE entry_date >= '2026-09-01') AS since_0901,
       count(*) FILTER (WHERE entry_mode='confirm') AS confirm_total
FROM mi_consolidation_entry_shadow;
SELECT updated_at::date AS d, count(*) AS board_rows, count(*) FILTER (WHERE state='coiled') AS coiled
FROM mi_anticipation_consolidation WHERE updated_at >= now() - interval '25 days' GROUP BY 1 ORDER BY 1;
SELECT created_at::date AS d, event_type, left(summary,160) AS summary
FROM mi_audit_log WHERE created_at >= now() - interval '20 days'
  AND (summary ILIKE '%consolidation_readiness%' OR event_type ILIKE '%consolidation%')
ORDER BY created_at DESC LIMIT 25;
-- (2) IBP left Residential Building Materials: membership by date + any audit mention
SELECT theme_date, name, stage, 'IBP' = ANY(tickers) AS has_ibp, cardinality(tickers) AS n
FROM mi_themes WHERE theme_date >= '2026-10-12' AND name ILIKE '%Residential Building Materials%' ORDER BY theme_date;
SELECT created_at, event_type, left(summary,200) AS summary
FROM mi_audit_log WHERE created_at >= '2026-10-14' AND (summary ILIKE '%IBP%' OR detail ILIKE '%"IBP"%') ORDER BY created_at LIMIT 20;
