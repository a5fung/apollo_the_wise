-- verify #694: logged in_active_theme on mi_ep_alerts (any time of day) and on the shortlist shadow 08-22..08-28, to test the REBUILT flag. Read-only.
\echo '### V7a alerts'
SELECT alert_date, ticker, in_active_theme, to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI') t
  FROM mi_ep_alerts WHERE alert_date BETWEEN '2026-05-01' AND '2026-08-28' AND in_active_theme IS NOT NULL ORDER BY 1,2;
\echo '### V7b shadow last pre-open tick 08-22..08-28'
WITH s AS (SELECT * FROM mi_ep_shortlist_shadow WHERE scan_date <= '2026-08-28' AND (scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30'),
lt AS (SELECT scan_date, max(scan_time_et) t FROM s GROUP BY 1)
SELECT s.scan_date, s.ticker, s.in_active_theme FROM s JOIN lt ON lt.scan_date=s.scan_date AND lt.t=s.scan_time_et ORDER BY 1,2;
