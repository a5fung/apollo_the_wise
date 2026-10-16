-- READ-ONLY. The guard's last-30-day flags, and whether each ticker was stripped/revalidated out the same night.
WITH f AS (
  SELECT created_at, split_part(summary,'@',1) AS ticker, split_part(split_part(summary,'@',2),': pruned',1) AS theme
  FROM mi_audit_log WHERE event_type='theme_member_pruned_while_rising' AND created_at >= now() - interval '30 days')
SELECT f.created_at::date AS d, f.ticker, left(f.theme,60) AS theme,
  EXISTS (SELECT 1 FROM mi_audit_log a WHERE a.event_type='theme_carryforward_filter_stripped'
          AND a.created_at BETWEEN f.created_at - interval '1 hour' AND f.created_at
          AND a.summary ILIKE '%' || f.theme || '%' AND a.detail LIKE '%''' || f.ticker || '''%') AS stripped,
  EXISTS (SELECT 1 FROM mi_audit_log a WHERE a.event_type='ticker_revalidated_out'
          AND a.created_at BETWEEN f.created_at - interval '1 hour' AND f.created_at
          AND a.summary ILIKE '%' || f.ticker || '%') AS revalidated
FROM f ORDER BY 1;
