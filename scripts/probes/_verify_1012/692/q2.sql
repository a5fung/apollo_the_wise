\echo == A. all %mna% events since 10-03 by type
SELECT event_type, count(*) FROM mi_audit_log WHERE created_at >= '2026-10-03 00:00:00-04' AND event_type LIKE '%mna%' GROUP BY 1 ORDER BY 2 DESC;
\echo == B. non-mna-prefixed mna-ish events (anticipation/open_window)
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS et, event_type, left(summary,200) FROM mi_audit_log WHERE created_at >= '2026-10-03 00:00:00-04' AND (event_type LIKE '%mna%' AND event_type NOT LIKE 'mna%' OR event_type LIKE 'open_window%' OR event_type LIKE 'alpaca%') ORDER BY created_at;
\echo == C. any audit row since 10-10 whose detail mentions alpaca news_source
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS et, event_type, left(summary,160) FROM mi_audit_log WHERE created_at >= '2026-10-10 00:00:00-04' AND (detail LIKE '%"news_source": "alpaca"%' OR detail LIKE '%alpaca_headline_model%' OR summary LIKE '%alpaca_headline_model%') ORDER BY created_at;
\echo == D. toggle state
SELECT * FROM mi_safeguard_state WHERE safeguard LIKE '%mna%' OR safeguard LIKE '%alpaca%';
\echo == E. SYNA board rows
SELECT ticker, anchor_date, state, mna_screened_on, to_char(updated_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') AS upd FROM mi_anticipation_consolidation WHERE ticker='SYNA' ORDER BY anchor_date DESC LIMIT 8;
\echo == F. EP alerts for the blocked names
SELECT ticker, alert_date, score_tier, ep_score, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') AS t FROM mi_ep_alerts WHERE ticker IN ('PTC','OPCH','PCRX','CCC','AFYA','CMG','SWKS','SNDK','IOVA') AND alert_date >= '2026-10-05' ORDER BY created_at;
\echo == G. live trades for the blocked names
SELECT id, ticker, status, account_mode, skip_reason, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') AS t FROM mi_live_trades WHERE ticker IN ('PTC','OPCH','PCRX','CCC','AFYA','CMG','SWKS','SNDK','IOVA') AND created_at >= '2026-10-05' ORDER BY created_at;
