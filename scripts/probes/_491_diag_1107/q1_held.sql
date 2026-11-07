SET default_transaction_read_only = on;
-- every skip since the U2 deploy, one row per (night ET, theme): members barred, kept, cooldown source
WITH s AS (
  SELECT (a.created_at AT TIME ZONE 'America/New_York')::date AS night,
         a.detail::jsonb->>'theme' AS theme, a.detail::jsonb->>'ticker' AS ticker,
         a.detail::jsonb->>'path' AS path, (a.detail::jsonb->>'kept')::int AS kept,
         (a.detail::jsonb->>'held_below_floor')::boolean AS held, a.created_at
  FROM mi_audit_log a
  WHERE a.event_type='promote_member_skipped' AND a.created_at > TIMESTAMPTZ '2026-10-23 20:00+00')
SELECT s.night, s.theme, bool_or(s.held) AS held, max(s.kept) AS kept,
       string_agg(s.ticker||'('||s.path||':'||coalesce(
          (SELECT CASE WHEN c.removal_reason ILIKE 'rehome%' THEN 'rehome' ELSE left(c.removal_reason,40) END
             FROM mi_validation_cooldowns c WHERE c.ticker=s.ticker AND c.theme_name=s.theme
              AND c.removed_at <= s.created_at ORDER BY c.removed_at DESC LIMIT 1),'?')||')', ', ') AS barred
FROM s GROUP BY 1,2 ORDER BY 1,2;
