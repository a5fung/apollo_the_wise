SET default_transaction_read_only = on;
-- every infra:no_bar skip ever, and how many entries each such day still placed
SELECT alert_date, account_mode, signal_type, ticker, left(skip_reason, 80) AS reason
FROM mi_live_trades WHERE skip_reason ILIKE 'infra:no_bar%' ORDER BY alert_date, ticker;
-- stream-cache use per day since the 08-13 fix (attempt number shows how late the bar landed)
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, count(*) AS n,
       count(*) FILTER (WHERE summary NOT ILIKE '%attempt 1 %') AS after_attempt_1
FROM mi_audit_log WHERE event_type = 'orb_bar_stream_used' GROUP BY 1 ORDER BY 1;
SELECT count(*) AS bar_miss_rows, count(DISTINCT (created_at AT TIME ZONE 'America/New_York')::date) AS days
FROM mi_audit_log WHERE event_type = 'orb_bar_miss';
