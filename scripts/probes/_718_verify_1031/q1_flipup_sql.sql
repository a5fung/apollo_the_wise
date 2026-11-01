SET default_transaction_read_only = on;
PREPARE q(text, date) AS SELECT created_at, summary, detail
    FROM mi_audit_log
    WHERE event_type = 'ep_rt_floor_flip_up'
      AND created_at >= ($2::date - INTERVAL '1 day')
      AND (created_at AT TIME ZONE 'America/New_York')::date = $2
      AND substring(summary from '^([A-Z.]{1,6}) ') = $1
    ORDER BY created_at, id
    LIMIT 1;
\echo == REGN 2026-10-30 (expect 1 row)
EXECUTE q('REGN', '2026-10-30');
\echo == REGN 2026-10-29 (expect 0 rows)
EXECUTE q('REGN', '2026-10-29');
\echo == CEG 2026-10-06 (a studied flip-up, expect 1 row)
EXECUTE q('CEG', '2026-10-06');
\echo == population cross-check: HIGH alerts since 2026-08-02 that the SQL marks flip-up admitted (the study read 51)
SELECT count(*) FROM mi_ep_alerts a WHERE a.alert_date >= '2026-08-02' AND a.alert_date <= '2026-10-30' AND a.score_tier = 'HIGH'
  AND EXISTS (SELECT 1 FROM mi_audit_log l WHERE l.event_type = 'ep_rt_floor_flip_up'
    AND l.created_at >= (a.alert_date - INTERVAL '1 day') AND (l.created_at AT TIME ZONE 'America/New_York')::date = a.alert_date
    AND substring(l.summary from '^([A-Z.]{1,6}) ') = a.ticker);
