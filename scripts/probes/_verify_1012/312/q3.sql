\echo === G. mi_ep_alerts today: tier counts ===
SELECT alert_date, tier, COUNT(*) n FROM mi_ep_alerts WHERE alert_date >= DATE '2026-10-08' GROUP BY 1,2 ORDER BY 1,2;
\echo === G2. today alerts list ===
SELECT ticker, tier, ep_score, (detected_at AT TIME ZONE 'America/New_York') AS det_et
FROM mi_ep_alerts WHERE alert_date = DATE '2026-10-12' ORDER BY detected_at;
\echo === H. Telegram/log: scan candidates with HIGH/MODERATE today (ep_scan log) ===
SELECT column_name FROM information_schema.columns WHERE table_name='mi_ep_scan_candidates' ORDER BY ordinal_position;
