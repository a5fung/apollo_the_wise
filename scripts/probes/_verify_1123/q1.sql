SET default_transaction_read_only = on;
\echo == 731 scan rows today (float<50M)
SELECT ticker, to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI') t, round(float_shares/1e6,1) float_m, score_breakdown->>'float' fpts, ep_score, filter_reason
FROM mi_ep_scan_log WHERE scan_date='2026-11-23' AND score_breakdown IS NOT NULL AND float_shares < 50e6 ORDER BY scan_time_et LIMIT 25;
\echo == 731 counts by float pts today
SELECT score_breakdown->>'float' fpts, count(*), sum((float_shares<50e6)::int) lowfloat FROM mi_ep_scan_log WHERE scan_date='2026-11-23' AND score_breakdown IS NOT NULL GROUP BY 1;
\echo == 729 slot rank rows today
SELECT ticker, to_char(recorded_at AT TIME ZONE 'America/New_York','HH24:MI:SS') rec, trigger, board_n, rank_rs, rank_shelf, round(shelf_dmin::numeric,2) dmin, shelf_null, shelf_structure, acting_key FROM mi_ep_slot_rank_shadow WHERE alert_date='2026-11-23' ORDER BY recorded_at, rank_rs;
\echo == audit rows today of interest
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') t, event_type, left(summary,200) FROM mi_audit_log WHERE created_at >= '2026-11-23 00:00-05' AND (event_type ILIKE '%shelf%' OR event_type ILIKE '%stop%' OR summary ILIKE '%EVER%' OR event_type ILIKE '%watchdog%' OR event_type ILIKE '%breach%') ORDER BY created_at;
