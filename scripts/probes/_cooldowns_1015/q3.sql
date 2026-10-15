-- what added the apparel names before 17:07 and what retired the furniture theme after (read-only)
SELECT id, created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary, 170) AS summary
  FROM mi_audit_log
 WHERE created_at >= TIMESTAMPTZ '2026-10-15 20:55+00' AND created_at <= TIMESTAMPTZ '2026-10-15 21:40+00'
   AND event_type NOT IN ('ticker_revalidated_out','validation_cooldown_triggered')
   AND (summary ILIKE '%Furniture%' OR summary ILIKE '%apparel%' OR summary ILIKE '% GAP%' OR summary ILIKE '%ANF%'
        OR summary ILIKE '%retire%' OR summary ILIKE '%merge%' OR summary ILIKE '%absorb%' OR summary ILIKE '%name_suspect%')
 ORDER BY id;
SELECT name, array_length(tickers,1) n, stage, source, left(array_to_string(tickers, ','), 160) AS tickers
  FROM mi_themes WHERE theme_date = DATE '2026-10-15'
   AND (tickers && ARRAY['GAP','ANF','AEO','URBN','M','KSS','ROST','RL','PVH'] OR name ILIKE '%apparel%' OR name ILIKE '%retail%' OR name ILIKE '%furniture%');
