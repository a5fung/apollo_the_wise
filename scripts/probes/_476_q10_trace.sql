\echo '--- ping-pong elites: their mi_themes rows (25d) ---'
SELECT t.theme_date, x.tk AS ticker, t.name, t.stage, t.source
FROM mi_themes t
CROSS JOIN LATERAL unnest(ARRAY['TGTX','ELVN','ALMS','KURA','XENE','ACAD']) AS x(tk)
WHERE t.theme_date >= CURRENT_DATE - 25 AND x.tk = ANY(t.tickers)
ORDER BY x.tk, t.theme_date;
\echo '--- first shadow_themes_promoted audit (resolve NRIX 6/24) ---'
SELECT MIN((created_at AT TIME ZONE 'America/New_York')::date) AS first_promote_date,
       COUNT(*) AS total_events
FROM mi_audit_log WHERE event_type = 'shadow_themes_promoted';
