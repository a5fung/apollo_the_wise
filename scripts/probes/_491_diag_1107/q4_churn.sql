SET default_transaction_read_only = on;
-- before the wall (10-05..10-23): how often did the nightly promotion put a validator-removed stock straight back
-- into the theme it was removed from, within 2 days? (the churn the wall now stops; a lower bound — the cooldown
-- table keeps one row per pair, so a re-removal overwrites the earlier one)
SELECT CASE WHEN c.removed_at < TIMESTAMPTZ '2026-10-23 21:00+00' THEN 'before wall' ELSE 'after wall' END AS era,
       CASE WHEN c.removal_reason ILIKE 'rehome%' THEN 'rehome' ELSE 'validation' END AS kind,
       count(*) AS removals,
       count(*) FILTER (WHERE EXISTS (
          SELECT 1 FROM mi_themes t WHERE t.source='shadow_promoted' AND t.name=c.theme_name
            AND c.ticker = ANY(t.tickers)
            AND t.theme_date BETWEEN (c.removed_at AT TIME ZONE 'America/New_York')::date
                                 AND (c.removed_at AT TIME ZONE 'America/New_York')::date + 2)) AS put_back_within_2d
FROM mi_validation_cooldowns c
WHERE c.removed_at BETWEEN '2026-10-05' AND '2026-11-07' AND NOT c.bypassed
GROUP BY 1,2 ORDER BY 1,2;
