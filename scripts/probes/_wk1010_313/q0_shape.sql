-- READ-ONLY. Shape checks before building the #313 spend-vs-P&L section.
-- closed trades the window query could silently drop (no close time / no pnl)
SELECT 'closed_gaps' AS q, account_mode,
       count(*)::text AS n_closed,
       count(*) FILTER (WHERE closed_at IS NULL)::text AS no_closed_at,
       count(*) FILTER (WHERE total_pnl IS NULL)::text AS no_pnl,
       count(*) FILTER (WHERE pnl_attribution IS NOT NULL)::text AS bug_attributed,
       min((closed_at AT TIME ZONE 'America/New_York')::date)::text AS first_close,
       max((closed_at AT TIME ZONE 'America/New_York')::date)::text AS last_close
  FROM mi_live_trades WHERE status = 'closed' GROUP BY account_mode ORDER BY account_mode;
-- api_usage hygiene over 35 days
SELECT 'usage_shape' AS q,
       count(*)::text AS n,
       count(*) FILTER (WHERE cost_usd IS NULL)::text AS null_cost,
       count(*) FILTER (WHERE caller IS NULL)::text AS null_caller,
       count(DISTINCT caller)::text AS n_callers,
       min(created_at)::text AS first_row, max(created_at)::text AS last_row
  FROM api_usage WHERE created_at >= now() - interval '35 days';
SELECT 'cols' AS q, column_name, data_type FROM information_schema.columns
 WHERE table_name = 'api_usage' ORDER BY ordinal_position;
