SET default_transaction_read_only = on;
-- for every (day, ticker) that missed its bar at least once: first miss -> how it resolved, and how long it took
WITH ev AS (
  SELECT created_at, (created_at AT TIME ZONE 'America/New_York') AS et, event_type,
         substring(summary from '^[A-Za-z0-9 ]*? ([A-Z]{1,6})(?: attempt| —| O=|:)') AS tkr, summary
  FROM mi_audit_log
  WHERE event_type IN ('orb_bar_miss','orb_bar_fetched','orb_bar_stream_used','orb_skipped')
    AND created_at >= '2026-04-01'
), miss AS (
  SELECT et::date AS d, tkr, min(et) AS first_miss, count(*) AS misses FROM ev WHERE event_type='orb_bar_miss' GROUP BY 1,2
)
SELECT m.d, m.tkr, m.misses, m.first_miss::time(0) AS first_miss,
  (SELECT e.event_type || ' +' || round(extract(epoch FROM e.et - m.first_miss)::numeric,1) || 's'
   FROM ev e WHERE e.tkr = m.tkr AND e.et::date = m.d AND e.et >= m.first_miss AND e.event_type <> 'orb_bar_miss'
   ORDER BY e.et LIMIT 1) AS resolved
FROM miss m ORDER BY m.d, m.tkr;
