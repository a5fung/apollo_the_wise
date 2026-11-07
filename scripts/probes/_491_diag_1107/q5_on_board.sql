SET default_transaction_read_only = on;
-- each held cohort: was a theme of that exact name on the board that night anyway (any source), and with how many members?
WITH h AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS night, detail::jsonb->>'theme' AS theme
  FROM mi_audit_log WHERE event_type='promote_member_skipped' AND created_at > TIMESTAMPTZ '2026-10-23 20:00+00'
    AND (detail::jsonb->>'held_below_floor')::boolean)
SELECT h.night, h.theme,
       (SELECT t.source||' '||t.stage||' '||t.theme_date||' n='||cardinality(t.tickers) FROM mi_themes t
         WHERE t.name=h.theme AND t.theme_date BETWEEN h.night - 7 AND h.night ORDER BY t.theme_date DESC LIMIT 1) AS latest_row_in_7d,
       (SELECT min(t.theme_date) FROM mi_themes t WHERE t.name=h.theme) AS first_ever,
       (SELECT max(t.theme_date) FROM mi_themes t WHERE t.name=h.theme) AS last_ever
FROM h ORDER BY h.theme, h.night;
