SELECT theme_date, name, stage, source, parent_theme, array_length(tickers,1) nt, days_active
FROM mi_themes
WHERE name IN ('Diabetes Management Devices (CGM, Insulin Pumps & Delivery)','Orthopedic Surgical Devices & Instruments','Semiconductor Equipment Capex Cycle: AI-Driven Fab & Advanced Packaging Demand','Semiconductor Test, Yield & Assembly Supply Chain')
AND theme_date >= '2026-10-07' ORDER BY name, theme_date;
\echo == audit rows around retire/fold of these
SELECT id,(created_at AT TIME ZONE 'America/New_York')::text ts, event_type, left(summary,260) s FROM mi_audit_log
WHERE created_at > '2026-10-12 16:30:00-04' AND (summary ILIKE '%Semiconductor Equipment Capex%' OR summary ILIKE '%Diabetes Management%' OR summary ILIKE '%Orthopedic Surgical%') ORDER BY id;
\echo == event types tonight 17:00-18:15 ET containing theme
SELECT event_type, count(*) FROM mi_audit_log WHERE created_at > '2026-10-12 17:00:00-04' AND created_at < '2026-10-12 18:30:00-04' AND (event_type ILIKE 'theme%' OR event_type ILIKE '%fold%') GROUP BY 1 ORDER BY 1;
