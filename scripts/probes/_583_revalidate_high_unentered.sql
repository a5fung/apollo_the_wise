-- #583 read-only diagnostic: re-run the CURRENT high_unentered/window_missed
-- categorisation logic (mirrors refresh_missed_outcomes's high_unentered CTE +
-- categorisation CASE) over the full retained source-table history, and diff
-- against what's frozen in mi_ep_missed_outcomes. SELECT-only, no writes.
WITH traded AS (
    SELECT ticker, alert_date FROM mi_live_trades
    WHERE status NOT IN ('skipped', 'cancelled', 'order_failed')
    UNION
    SELECT ticker, alert_date FROM mi_paper_trades
),
high_unentered AS (
    SELECT DISTINCT ON (a.ticker, a.alert_date)
        a.ticker,
        a.alert_date,
        sk.skip_reason,
        a.score_tier
    FROM mi_ep_alerts a
    LEFT JOIN LATERAL (
        SELECT skip_reason FROM mi_live_trades lt
        WHERE lt.ticker = a.ticker AND lt.alert_date = a.alert_date
          AND lt.status IN ('skipped', 'cancelled', 'order_failed')
        ORDER BY lt.id DESC LIMIT 1
    ) sk ON TRUE
    WHERE a.score_tier = 'HIGH'
      AND COALESCE(a.source, 'live') = 'live'
      AND NOT EXISTS (
          SELECT 1 FROM traded t
          WHERE t.ticker = a.ticker AND t.alert_date = a.alert_date
      )
    ORDER BY a.ticker, a.alert_date, a.created_at DESC
),
recomputed AS (
    SELECT
        ticker, alert_date,
        CASE
            WHEN skip_reason ILIKE 'block:max_positions%' THEN 'cap_blocked'
            WHEN skip_reason ILIKE 'block:circuit_breaker%' THEN 'breaker_blocked'
            WHEN skip_reason ILIKE 'block:%' THEN 'block_other'
            WHEN skip_reason ILIKE 'window:%' THEN 'window_missed'
            WHEN skip_reason ILIKE 'setup:stop_too_wide%' THEN 'stop_too_wide'
            WHEN skip_reason ILIKE 'setup:faded%' THEN 'faded_from_orb'
            WHEN skip_reason ILIKE 'setup:account_fetch%'
              OR skip_reason ILIKE 'infra:%' THEN 'infra_skip'
            WHEN skip_reason ILIKE 'setup:%' THEN 'setup_other'
            ELSE 'high_unentered'
        END AS recomputed_category
    FROM high_unentered
)
SELECT
    COALESCE(m.skip_category, 'MISSING_FROM_RECOMPUTE') AS stored_category,
    COALESCE(r.recomputed_category, 'MISSING_FROM_STORED') AS recomputed_category,
    COUNT(*) AS n
FROM mi_ep_missed_outcomes m
FULL OUTER JOIN recomputed r
  ON r.ticker = m.ticker AND r.alert_date = m.alert_date
WHERE m.skip_category IN ('high_unentered', 'window_missed')
   OR r.recomputed_category IN ('high_unentered', 'window_missed')
GROUP BY 1, 2
ORDER BY 1, 2;
