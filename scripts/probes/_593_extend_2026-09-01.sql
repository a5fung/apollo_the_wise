-- #593 narrow extension query (read-only, $0) — check for NEW ep_rt_sustain_reject
-- ticker-days since the 2026-08-28 signed analysis, under the SIGNED methodology
-- (declined-level basis, tradeability filters). Never re-run to re-read.

\echo ===Q1_NEW_REJECTS===
SELECT (created_at AT TIME ZONE 'America/New_York')::date          AS d_et,
       to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') AS t_et,
       detail::jsonb->>'ticker'        AS ticker,
       detail::jsonb->>'rt_gap'        AS rt_gap
FROM mi_audit_log
WHERE event_type = 'ep_rt_sustain_reject'
  AND created_at AT TIME ZONE 'America/New_York' >= '2026-08-29'
ORDER BY created_at;

\echo ===Q2_NEW_CATCHES===
SELECT (created_at AT TIME ZONE 'America/New_York')::date          AS d_et,
       detail::jsonb->>'ticker'        AS ticker
FROM mi_audit_log
WHERE event_type = 'ep_rt_universe_catch'
  AND created_at AT TIME ZONE 'America/New_York' >= '2026-08-29'
ORDER BY created_at;

\echo ===Q3_DAILY_CLOSES===
WITH universe AS (
  SELECT DISTINCT detail::jsonb->>'ticker' AS ticker
  FROM mi_audit_log
  WHERE event_type IN ('ep_rt_sustain_reject','ep_rt_universe_catch')
    AND created_at AT TIME ZONE 'America/New_York' >= '2026-08-29'
    AND detail::jsonb->>'ticker' IS NOT NULL
)
SELECT c.trade_date, c.ticker, c.open_price, c.high_price, c.low_price, c.close, c.volume
FROM mi_daily_closes c
JOIN universe u ON u.ticker = c.ticker
WHERE c.trade_date BETWEEN '2026-08-24' AND '2026-09-01'
ORDER BY c.ticker, c.trade_date;

\echo ===Q4_NOW===
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS now_et;
