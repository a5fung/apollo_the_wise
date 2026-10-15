\set QUIET on
\pset format unaligned
\pset fieldsep '|'
\pset footer off
\pset null ''
-- L1. positive evidence the EP scanner/admit path ran on 10-15 (a dead scanner also shows zero alerts)
SELECT 'L1_ep_audit_today' AS chk, event_type, count(*) AS n, min(created_at AT TIME ZONE 'America/New_York') AS first_et, max(created_at AT TIME ZONE 'America/New_York') AS last_et FROM mi_audit_log WHERE created_at >= TIMESTAMPTZ '2026-10-15 00:00-04' AND (event_type ILIKE 'ep_%' OR event_type ILIKE '%ep_scan%') GROUP BY 2 ORDER BY 2;
SELECT 'L2_admit_today' AS chk, created_at AT TIME ZONE 'America/New_York' AS at_et, event_type, left(summary,150) AS summary FROM mi_audit_log WHERE created_at >= TIMESTAMPTZ '2026-10-15 00:00-04' AND event_type IN ('ep_rt_admit','ep_rt_sustain_reject','ep_rt_declined_not_missed','ep_alert') ORDER BY created_at LIMIT 20;
SELECT 'L3_alerts_created_today' AS chk, id, ticker, alert_date, source, score_tier, created_at AT TIME ZONE 'America/New_York' AS created_et FROM mi_ep_alerts WHERE created_at >= TIMESTAMPTZ '2026-10-15 00:00-04' ORDER BY id;
SELECT 'L4_jobs_today' AS chk, job_id, status, count(*) AS n, max(finished_at AT TIME ZONE 'America/New_York') AS last_fin_et FROM mi_job_runs WHERE started_at >= TIMESTAMPTZ '2026-10-15 00:00-04' AND (job_id ILIKE '%ep%' OR job_id ILIKE '%rank%' OR job_id ILIKE '%missed%' OR job_id ILIKE '%flag%' OR job_id ILIKE '%daily_close%' OR job_id ILIKE '%grouped%') GROUP BY 2,3 ORDER BY 2,3;
SELECT 'L5_live_trades_today' AS chk, id, ticker, alert_date, status, skip_reason, account_mode FROM mi_live_trades WHERE created_at >= TIMESTAMPTZ '2026-10-15 00:00-04' ORDER BY id;
SELECT 'L6_prior_alert_days' AS chk, alert_date, count(*) AS n FROM mi_ep_alerts WHERE alert_date >= DATE '2026-09-28' AND source='live' GROUP BY 2 ORDER BY 2;
-- L7. VICR / GNRC bars (the two rows reaching their 21st session today)
SELECT 'L7_bars' AS chk, ticker, trade_date, open_price, high_price, low_price, close_price FROM mi_daily_closes WHERE ticker IN ('VICR','GNRC') AND trade_date >= DATE '2026-09-17' ORDER BY ticker, trade_date;
