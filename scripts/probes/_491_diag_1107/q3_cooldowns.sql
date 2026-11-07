SET default_transaction_read_only = on;
-- when were the barred pairs' cooldowns written, and by what?
SELECT DISTINCT ON (s.ticker, s.theme) s.ticker, s.theme,
       (c.removed_at AT TIME ZONE 'America/New_York')::date AS removed_et, c.removal_count,
       CASE WHEN c.removal_reason ILIKE 'rehome%' THEN 'rehome' ELSE 'validation' END AS kind,
       (c.cooldown_until AT TIME ZONE 'America/New_York')::date AS until_et
FROM (SELECT DISTINCT detail::jsonb->>'ticker' AS ticker, detail::jsonb->>'theme' AS theme FROM mi_audit_log
      WHERE event_type='promote_member_skipped' AND created_at > TIMESTAMPTZ '2026-10-23 20:00+00') s
JOIN mi_validation_cooldowns c ON c.ticker=s.ticker AND c.theme_name=s.theme
ORDER BY s.ticker, s.theme, c.removed_at DESC;
-- validation vs rehome cooldowns written per week since September
SELECT date_trunc('week', removed_at AT TIME ZONE 'America/New_York')::date AS wk,
       count(*) FILTER (WHERE removal_reason ILIKE 'rehome%') AS rehome,
       count(*) FILTER (WHERE removal_reason NOT ILIKE 'rehome%') AS validation
FROM mi_validation_cooldowns WHERE removed_at > '2026-09-01' GROUP BY 1 ORDER BY 1;
