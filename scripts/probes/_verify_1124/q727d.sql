SET default_transaction_read_only = on;
SELECT created_at AT TIME ZONE 'America/New_York', event_type, left(summary,260), left(detail::text,300) FROM mi_audit_log WHERE created_at >= '2026-11-23 21:00-05' AND (summary ~ '\m(CORZ|CRWV)\M' OR detail::text ~ '\m(CORZ|CRWV)\M') ORDER BY created_at;
SELECT theme_date, name, tickers FROM mi_themes WHERE theme_date='2026-11-24' AND (tickers && ARRAY['CORZ','CRWV']::text[]);
