-- READ-ONLY. The exact rows the new guard query reads, for the two nights the guard paged (09-17, 10-16).
SELECT json_agg(row_to_json(t)) FROM (
  SELECT (created_at AT TIME ZONE 'America/New_York')::date AS et_date, event_type, summary, detail FROM mi_audit_log
  WHERE event_type IN ('theme_carryforward_filter_stripped', 'ticker_revalidated_out')
    AND (created_at AT TIME ZONE 'America/New_York')::date IN ('2026-09-17', '2026-10-16')) t;
