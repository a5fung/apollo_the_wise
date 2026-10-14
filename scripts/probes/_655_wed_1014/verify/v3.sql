-- #655 Wed 2026-10-14 VERIFIER v3. READ-ONLY. (a) every fold-moved member since 10-12: removed from its fold home by validation? when?
-- (b) what wrote the two 10-12 board rows at 18:36 ET (after the 17:31 G3 check)?
\pset format unaligned
\pset fieldsep '\t'
\echo == X1 fold-moved members since 10-12 vs ticker_revalidated_out rows naming the same ticker AND the same home
WITH f AS (SELECT id, created_at fat, (created_at AT TIME ZONE 'America/New_York')::date fd, detail::json d FROM mi_audit_log WHERE event_type='theme_small_folded' AND created_at >= '2026-10-12 00:00:00-04'),
m AS (SELECT f.id, f.fat, f.fd, f.d->>'theme' old_theme, f.d->>'home' home, x tk FROM f, json_array_elements_text(f.d->'moved') x)
SELECT m.fd, m.tk, m.home,
 (SELECT string_agg((v.created_at AT TIME ZONE 'America/New_York')::text, ',') FROM mi_audit_log v WHERE v.event_type='ticker_revalidated_out' AND v.created_at > m.fat
   AND v.summary LIKE m.tk || ' removed from ''' || replace(m.home,'''','''''') || '''%') validated_out_at,
 EXISTS(SELECT 1 FROM mi_themes h WHERE h.name=m.home AND h.theme_date='2026-10-14' AND h.stage<>'Retired' AND m.tk = ANY(h.tickers)) in_home_1014
FROM m ORDER BY m.fd, m.home, m.tk;
\echo == X2 validation passes 10-12..10-14: ticker_revalidated_out count + time window per ET date
SELECT (created_at AT TIME ZONE 'America/New_York')::date d, count(*) n, min((created_at AT TIME ZONE 'America/New_York')::time(0))::text, max((created_at AT TIME ZONE 'America/New_York')::time(0))::text
FROM mi_audit_log WHERE event_type='ticker_revalidated_out' AND created_at >= '2026-10-12 00:00:00-04' GROUP BY 1 ORDER BY 1;
\echo == X3 audit rows 10-12 18:30-18:40 ET (what wrote the 18:36 board rows)
SELECT id, (created_at AT TIME ZONE 'America/New_York')::time(0)::text t, event_type, left(summary,200) s FROM mi_audit_log
WHERE created_at >= '2026-10-12 18:30:00-04' AND created_at < '2026-10-12 18:40:00-04' ORDER BY id;
\echo == X3b job runs 10-12 18:25-18:40 ET
SELECT id, job_id, (started_at AT TIME ZONE 'America/New_York')::time(0)::text st, status FROM mi_job_runs
WHERE started_at >= '2026-10-12 18:25:00-04' AND started_at < '2026-10-12 18:40:00-04' ORDER BY id;
