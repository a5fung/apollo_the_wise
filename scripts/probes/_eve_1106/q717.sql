SET default_transaction_read_only = on;
SELECT scan_date, count(*) names, round(min(adr20)::numeric*100,2) min_adr_pct, count(*) FILTER (WHERE adr20 < 0.021) under_2_1,
       count(*) FILTER (WHERE order_score IS NULL) null_score, count(*) FILTER (WHERE runup6m_adr IS NULL OR spread10_adr IS NULL) null_inputs
FROM mi_breakout_v1_list WHERE scan_date >= DATE '2026-11-03' GROUP BY 1 ORDER BY 1;
SELECT ticker, list_rank, round(order_score::numeric,3) score FROM mi_breakout_v1_list WHERE scan_date = DATE '2026-11-06' ORDER BY list_rank LIMIT 3;
SELECT (SELECT ticker FROM mi_breakout_v1_list WHERE scan_date=DATE '2026-11-06' ORDER BY order_score DESC NULLS LAST, ticker LIMIT 1) AS max_score_ticker;
SELECT created_at AT TIME ZONE 'America/New_York' et, event_type, left(summary,220) FROM mi_audit_log WHERE event_type IN ('breakout_v1_list_run','breakout_v1_list_error') AND created_at > TIMESTAMPTZ '2026-11-06 12:00+00' ORDER BY id;
SELECT count(*) breakout_trades_today FROM mi_live_trades WHERE signal_type='breakout_v1' AND alert_date >= DATE '2026-11-06';
SELECT state FROM mi_safeguard_state WHERE safeguard='breakout_v1_paper';
SELECT status, count(*) FROM mi_job_runs WHERE job_id ILIKE 'breakout_v1%' AND started_at > TIMESTAMPTZ '2026-11-06 13:00+00' GROUP BY 1;
