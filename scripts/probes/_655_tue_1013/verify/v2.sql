-- #655 Tue 2026-10-13 VERIFIER part 2: near-name re-mints of Monday's folds. READ-ONLY.
\pset format unaligned
\pset fieldsep '\t'
\echo == 1 Monday fold rows: theme, home, moved, released
SELECT id, detail::json->>'theme' th, detail::json->>'home' home, detail::json->>'moved' moved, detail::json->>'released' rel
FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-12 16:30:00-04' AND created_at < '2026-10-13 06:00:00-04' ORDER BY id;
\echo == 2 tonight split rows full detail
SELECT id, summary, left(detail,600) FROM mi_audit_log WHERE event_type='theme_split' AND created_at >= '2026-10-13 16:30:00-04' AND created_at < '2026-10-14 06:00:00-04' ORDER BY id;
\echo == 3 10-13 rows that are new names (no row 10-06..10-12) or shadow_promoted, with members
SELECT t.name, t.stage, t.source, array_length(t.tickers,1) n, array_to_string(t.tickers,',') tk
FROM mi_themes t WHERE t.theme_date='2026-10-13' AND t.stage<>'Retired'
 AND (t.source='shadow_promoted' OR NOT EXISTS (SELECT 1 FROM mi_themes p WHERE p.name=t.name AND p.theme_date BETWEEN '2026-10-06' AND '2026-10-12')) ORDER BY t.name;
\echo == 4 where Monday's moved+released members sit on the 10-13 board
WITH m AS (SELECT json_array_elements_text(detail::json->'moved') tk, 'moved' k, detail::json->>'theme' src FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-12 16:30:00-04' AND created_at < '2026-10-13 06:00:00-04'
 UNION ALL SELECT json_array_elements_text(detail::json->'released'), 'released', detail::json->>'theme' FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-12 16:30:00-04' AND created_at < '2026-10-13 06:00:00-04')
SELECT m.src, m.k, m.tk, string_agg(t.name || ' [' || t.stage || ']', ' ; ') on_1013
FROM m LEFT JOIN mi_themes t ON t.theme_date='2026-10-13' AND t.stage<>'Retired' AND m.tk = ANY(t.tickers)
GROUP BY 1,2,3 ORDER BY 1,2,3;
