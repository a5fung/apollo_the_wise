SET default_transaction_read_only = on;
\echo == (1) hour-pass audit rows
SELECT (created_at AT TIME ZONE 'America/New_York')::timestamp(0) AS et, left(summary, 300) FROM mi_audit_log WHERE event_type = 'shadow_orb_hour_pass' ORDER BY created_at DESC LIMIT 3;
\echo == (2) every 60 row, beside its 5-minute sibling
SELECT h.id, h.ticker, h.alert_date, h.status, left(coalesce(h.skip_reason,''),70) AS skip, h.entry_price, h.hard_stop, h.entry_shares, h.orb_high, h.orb_low,
       h.risk_dollars, h.trigger_minute_et, h.hold_days,
       CASE WHEN jsonb_typeof(h.running_closes) = 'array' THEN jsonb_array_length(h.running_closes) ELSE -1 END AS n_closes,
       f.id AS five_id, f.orb_high AS f_orb_high, f.orb_low AS f_orb_low
FROM mi_orb_shadow_trades h LEFT JOIN mi_orb_shadow_trades f
  ON f.ticker = h.ticker AND f.alert_date = h.alert_date AND f.bar_size_minutes = 5
WHERE h.bar_size_minutes = 60 ORDER BY h.alert_date, h.ticker;
\echo == (2b) per-row checks on the 60 rows (each count must be 0)
SELECT
  count(*) FILTER (WHERE trigger_minute_et IS NOT NULL AND trigger_minute_et < '10:30:00') AS early_trigger,
  count(*) FILTER (WHERE status = 'open' AND entry_price < orb_high) AS open_below_high,
  count(*) FILTER (WHERE status = 'open' AND entry_shares <> 1) AS open_not_one_share,
  count(*) FILTER (WHERE status = 'open' AND abs(hard_stop - (2*orb_low - orb_high)) > 0.005) AS open_bad_stop,
  count(*) FILTER (WHERE status = 'open' AND abs(risk_dollars - (entry_price - hard_stop)) > 0.005) AS open_bad_risk,
  count(*) AS n60
FROM mi_orb_shadow_trades WHERE bar_size_minutes = 60;
\echo == (2c) 5-minute rows in the window with no 60 sibling
SELECT f.id, f.ticker, f.alert_date, f.status FROM mi_orb_shadow_trades f
WHERE f.bar_size_minutes = 5 AND f.alert_date >= DATE '2026-10-27' - 14
  AND NOT EXISTS (SELECT 1 FROM mi_orb_shadow_trades h WHERE h.bar_size_minutes = 60 AND h.ticker = f.ticker AND h.alert_date = f.alert_date)
ORDER BY f.id;
\echo == (3) snapshot (b) re-run (same columns as the baseline)
SELECT id, ticker, alert_date, status, skip_reason, entry_price, hard_stop, entry_shares, orb_high, orb_low, trigger_minute_et, total_pnl,
       CASE WHEN jsonb_typeof(running_closes) = 'array' THEN jsonb_array_length(running_closes) ELSE -1 END AS n_closes
FROM mi_orb_shadow_trades WHERE bar_size_minutes = 5 AND alert_date >= DATE '2026-10-27' - 14 ORDER BY id;
\echo == (4) stale quarantine since the deploy
SELECT count(*) AS quarantine_rows FROM mi_audit_log WHERE event_type = 'shadow_orb_stale_quarantine' AND created_at > '2026-10-27 21:27-04';
SELECT left(summary, 200) FROM mi_audit_log WHERE event_type = 'shadow_orb_stale_quarantine' AND created_at > '2026-10-27 21:27-04' LIMIT 5;
\echo == (5) L2 metric both ways for 10-28
SELECT count(*) FILTER (WHERE bar_size_minutes = 5) AS filtered, count(*) AS unfiltered
FROM mi_orb_shadow_trades WHERE alert_date = '2026-10-28' AND status IN ('open','closed');
\echo == (x) failure pages / errors since the deploy
SELECT event_type, count(*) FROM mi_audit_log WHERE created_at > '2026-10-27 21:27-04'
  AND (event_type ILIKE 'shadow_orb%error%' OR event_type ILIKE '%hour_entry%' OR event_type ILIKE 'shadow_orb_exit%') GROUP BY 1;
SELECT job_id, status, (started_at AT TIME ZONE 'America/New_York')::timestamp(0) AS et FROM mi_job_runs WHERE job_id ILIKE '%shadow_orb%' AND started_at > '2026-10-27 21:27-04' ORDER BY started_at;
