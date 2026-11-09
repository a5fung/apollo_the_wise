SET default_transaction_read_only = on;
SELECT raw_grade, sec_title, left(perplexity_text, 700) FROM mi_ep_grade_corpus WHERE ticker='APP' AND alert_date='2026-11-05';
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, left(summary, 300) FROM mi_audit_log
 WHERE created_at BETWEEN '2026-11-05 11:00+00' AND '2026-11-05 16:00+00' AND summary ~* '\mAPP\M' ORDER BY created_at LIMIT 12;
