-- #655 Thu 2026-10-15 night 4, part 3: (1) the apparel neighbours board history incl Footwear and Branded Apparel; (2) per-fold undone check 10-12..10-15 for the Sat 10-17 churn table. READ-ONLY.
\pset format unaligned
\pset fieldsep '\t'
\echo == now
SELECT (now() AT TIME ZONE 'America/New_York')::text now_et;
\echo == 1. apparel neighbours board history 10-08 on (stage, n, source, written, tickers)
SELECT name, theme_date, stage, array_length(tickers,1) n, source, (created_at AT TIME ZONE 'America/New_York')::time(0)::text written, array_to_string(tickers,',') tk
FROM mi_themes WHERE theme_date >= '2026-10-08' AND name IN ('Footwear & Branded Apparel Consumer Turnaround','Specialty Apparel & Mall-Based Specialty Retail Strength','Off-Price & Branded Apparel/Footwear Retail Rotation','Off-Price & Specialty Retail Consumer Rotation','Casual Footwear & Athletic Lifestyle Brands') ORDER BY name, theme_date;
\echo == 2. PER-FOLD undone check, every fold 10-12..10-15 (window = fold night + 2 calendar days, data ends 10-15)
WITH f AS (SELECT id, (created_at AT TIME ZONE 'America/New_York')::date fd, created_at ca, detail::json d FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-12'),
fo AS (SELECT id, fd, ca, d->>'theme' old_theme, d->>'home' home, (SELECT array_agg(x) FROM json_array_elements_text(d->'members') x) mem, (SELECT array_agg(x) FROM json_array_elements_text(d->'moved') x) moved FROM f)
SELECT fo.fd, fo.old_theme, fo.home, array_length(fo.mem,1) n_mem, coalesce(array_length(fo.moved,1),0) n_moved,
 (SELECT string_agg(DISTINCT t.theme_date::text, ',') FROM mi_themes t WHERE t.name=fo.old_theme AND t.theme_date>fo.fd AND t.stage<>'Retired') same_name_active_after,
 (SELECT string_agg(DISTINCT t.name || '@' || t.theme_date::text, '; ') FROM mi_themes t WHERE t.theme_date>fo.fd AND t.theme_date<=fo.fd+2 AND t.stage<>'Retired' AND t.name<>fo.home AND t.name<>fo.old_theme AND (SELECT count(*) FROM unnest(t.tickers) u WHERE u = ANY(fo.mem))>=2) other_name_remint,
 (SELECT string_agg(c.ticker || '@' || (c.removed_at AT TIME ZONE 'America/New_York')::date::text, ',') FROM mi_validation_cooldowns c WHERE c.theme_name=fo.home AND c.ticker = ANY(fo.moved) AND c.removed_at>fo.ca AND (c.removed_at AT TIME ZONE 'America/New_York')::date <= fo.fd+2) validator_removed_moved
FROM fo ORDER BY fo.id;
\echo == 3. tonight: tickers that sit in 2+ active themes among the apparel births
SELECT u tk, count(*) n_themes, string_agg(t.name, ' | ') themes FROM mi_themes t, unnest(t.tickers) u
WHERE t.theme_date='2026-10-15' AND t.stage<>'Retired' AND t.name IN ('Specialty Apparel & Mall-Based Specialty Retail Strength','Off-Price & Branded Apparel/Footwear Retail Rotation','Off-Price & Specialty Retail Consumer Rotation','Footwear & Branded Apparel Consumer Turnaround','Casual Footwear & Athletic Lifestyle Brands')
GROUP BY u HAVING count(*) >= 2;
