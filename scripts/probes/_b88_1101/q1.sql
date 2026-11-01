SET default_transaction_read_only = on;
SELECT DISTINCT ON (split_part(summary,' via',1), (created_at AT TIME ZONE 'America/New_York')::date)
  (created_at AT TIME ZONE 'America/New_York')::date AS d, split_part(summary,' via',1) AS ticker,
  LEFT(summary, 160) AS summary,
  COALESCE(detail::jsonb->>'match_path', detail::jsonb->>'source', '') AS path,
  COALESCE(detail::jsonb->>'role','') AS role, COALESCE(detail::jsonb->>'status','') AS status,
  COALESCE(detail::jsonb->>'consideration','') AS consid,
  LEFT(COALESCE(detail::jsonb->>'title', detail::jsonb->>'headline', detail::jsonb->'headlines'->0->>'title', ''), 150) AS title
FROM mi_audit_log WHERE event_type = 'mna_filter_fired' AND created_at >= NOW() - INTERVAL '30 days'
ORDER BY split_part(summary,' via',1), (created_at AT TIME ZONE 'America/New_York')::date, created_at DESC;
