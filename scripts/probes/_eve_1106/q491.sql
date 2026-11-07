SET default_transaction_read_only = on;
\echo '== A. bounces: re-homed name back in a shadow_promoted row named exactly its from-theme, post-fix nights (expect 0)'
WITH m AS MATERIALIZED (SELECT id, created_at, detail::jsonb j FROM mi_audit_log WHERE event_type='theme_member_rehomed' AND created_at >= '2026-10-10')
SELECT m.j->>'ticker' tk, m.j->>'from' frm, (m.created_at AT TIME ZONE 'America/New_York')::date moved, t.theme_date
FROM m JOIN mi_themes t ON t.source='shadow_promoted' AND t.name = m.j->>'from' AND (m.j->>'ticker') = ANY(t.tickers)
 AND t.theme_date >  (m.created_at AT TIME ZONE 'America/New_York')::date
 AND t.theme_date <= (m.created_at AT TIME ZONE 'America/New_York')::date + 14
 AND t.theme_date >= '2026-10-26'
ORDER BY t.theme_date LIMIT 20;
\echo '== B. DONE-WHEN 1: skip rows since the fix, with the matching re-home (non-null rehomed_at + path=cooldown = met)'
WITH s AS MATERIALIZED (SELECT id, created_at, detail::jsonb j FROM mi_audit_log WHERE event_type='promote_member_skipped' AND created_at >= '2026-10-24'),
     m AS MATERIALIZED (SELECT created_at, detail::jsonb j FROM mi_audit_log WHERE event_type='theme_member_rehomed' AND created_at >= '2026-10-01')
SELECT s.created_at AT TIME ZONE 'America/New_York' et, s.j->>'ticker' tk, s.j->>'theme' theme, s.j->>'path' path, s.j->>'held_below_floor' held,
 (SELECT max(m.created_at AT TIME ZONE 'America/New_York') FROM m WHERE m.j->>'ticker' = s.j->>'ticker' AND m.j->>'from' = s.j->>'theme'
   AND m.created_at < s.created_at AND m.created_at >= s.created_at - interval '15 days') rehomed_at
FROM s ORDER BY s.id LIMIT 30;
\echo '== C. per ET night since 10-26: heartbeat, promotion row, failures, skips, moves'
SELECT (created_at AT TIME ZONE 'America/New_York')::date d,
 count(*) FILTER (WHERE event_type='theme_rehome_pass_ran') hb,
 count(*) FILTER (WHERE event_type='shadow_themes_promoted') promo,
 count(*) FILTER (WHERE event_type='shadow_promotion_failed') fail,
 count(*) FILTER (WHERE event_type='promote_member_skipped') skips,
 count(*) FILTER (WHERE event_type='theme_member_rehomed') moves
FROM mi_audit_log
WHERE created_at >= '2026-10-26 00:00-04'
  AND event_type IN ('theme_rehome_pass_ran','shadow_themes_promoted','shadow_promotion_failed','promote_member_skipped','theme_member_rehomed')
GROUP BY 1 ORDER BY 1;
\echo '== D. trim/hold share + promoted names (detail is a text repr, NOT json, never cast)'
SELECT created_at AT TIME ZONE 'America/New_York' et, left(summary,220) summ, left(detail,300) det
FROM mi_audit_log WHERE event_type='shadow_themes_promoted' AND created_at >= '2026-10-26 00:00-04' ORDER BY id LIMIT 15;
\echo '== E. DoD cohort clause: live homes of the eight (get_active_themes shape, 7-day recency, ET date)'
WITH act AS (
  SELECT * FROM (SELECT DISTINCT ON (name) name, stage, tickers, theme_date FROM mi_themes
                 WHERE theme_date >= (now() AT TIME ZONE 'America/New_York')::date - 7
                 ORDER BY name, theme_date DESC) x
  WHERE stage <> 'Retired')
SELECT tk, string_agg(a.name || ' [' || a.stage || ', ' || a.theme_date || ']', ' | ') homes
FROM unnest(ARRAY['APLD','CIFR','CLSK','CORZ','CRWV','HUT','IREN','WULF']) tk
LEFT JOIN act a ON tk = ANY(a.tickers)
GROUP BY tk ORDER BY tk;