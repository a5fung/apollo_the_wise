-- #655 Wed 2026-10-14 VERIFIER v2. READ-ONLY. (a) the 2 board themes on 10-12 not in the 10-12 G3 array; (b) re-mint identity
-- of the promote-lane names vs their 10-12 rows; (c) how OTEX/BSY/OMCL left their fold homes tonight; (d) mi_themes columns.
\pset format unaligned
\pset fieldsep '\t'
\echo == W1 10-12 active board rows NOT in the 10-12 G3 array
WITH g AS (SELECT e->>'name' name FROM mi_audit_log a, json_array_elements(a.detail::json->'g3'->'themes') e WHERE a.id=55813)
SELECT t.name, t.stage, array_length(t.tickers,1) n, t.source, (t.created_at AT TIME ZONE 'America/New_York')::text written, array_to_string(t.tickers,',') tk
FROM mi_themes t WHERE t.theme_date='2026-10-12' AND t.stage<>'Retired' AND t.name NOT IN (SELECT name FROM g) ORDER BY 1;
\echo == W1b 10-12 board write-time spread by source (did anything land after the 17:31 check?)
SELECT source, stage='Retired' retired, count(*), min(created_at AT TIME ZONE 'America/New_York')::text first_w, max(created_at AT TIME ZONE 'America/New_York')::text last_w
FROM mi_themes WHERE theme_date='2026-10-12' GROUP BY 1,2 ORDER BY 1,2;
\echo == W2 re-mint identity: promote-lane names tonight vs their 10-12 and 10-13 rows (sorted tickers)
SELECT name, theme_date, stage, source, (SELECT string_agg(x,',' ORDER BY x) FROM unnest(tickers) x) tk_sorted, (created_at AT TIME ZONE 'America/New_York')::time(0)::text w
FROM mi_themes WHERE name IN ('Diagnostic Testing & Lab Equipment Re-Rating','Enterprise Information Management & Infrastructure Engineering Software','Capital Markets & Deal-Flow Re-Rating')
  AND theme_date >= '2026-10-09' ORDER BY name, theme_date;
\echo == W3 audit rows tonight 16:30-18:30 ET whose summary names OTEX BSY OMCL MDLN TMDX QDEL P
SELECT id, (created_at AT TIME ZONE 'America/New_York')::time(0)::text t, event_type, left(summary,220) s FROM mi_audit_log
WHERE created_at >= '2026-10-14 16:30:00-04' AND created_at < '2026-10-14 18:30:00-04'
  AND summary ~ '(^|[^A-Z])(OTEX|BSY|OMCL|MDLN|TMDX|QDEL)([^A-Z]|$)' ORDER BY id;
\echo == W4 mi_themes columns
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_themes' ORDER BY ordinal_position;
