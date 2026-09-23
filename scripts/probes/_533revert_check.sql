-- "don't revert, check" (operator 2026-09-02). Would REVERTING the #533 score flip have
-- produced any EP alert on the two zero-alert days? $0 — mi_ep_score_shadow already records
-- BOTH sides on every scan tick: sep_* (the acting separation side) and legacy_* (the
-- pre-2026-08-22 rubric at the per-regime bar 65/70/75/80). No recompute, no guessing.
\echo ===Q1_BOTH_SIDES_ON_THE_TWO_ZERO_ALERT_DAYS===
SELECT scan_date, live_side,
       COUNT(*)                                        AS rows,
       COUNT(*) FILTER (WHERE sep_tier_last    = 'HIGH')    AS sep_HIGH,
       COUNT(*) FILTER (WHERE legacy_tier_last = 'HIGH')    AS legacy_HIGH,
       COUNT(*) FILTER (WHERE legacy_tier_last = 'MODERATE') AS legacy_MODERATE,
       ROUND(MAX(sep_score_last)::numeric,1)                AS best_sep,
       ROUND(MAX(legacy_score_last)::numeric,1)             AS best_legacy
FROM mi_ep_score_shadow
WHERE scan_date >= '2026-09-01'
GROUP BY 1,2 ORDER BY 1 DESC;

\echo ===Q2_ANY_NAME_THE_LEGACY_SIDE_WOULD_HAVE_ALERTED===
SELECT scan_date, ticker,
       ROUND(sep_score_last::numeric,1) AS sep, sep_tier_last,
       ROUND(legacy_score_last::numeric,1) AS legacy, legacy_tier_last, legacy_bar
FROM mi_ep_score_shadow
WHERE scan_date >= '2026-09-01' AND legacy_tier_last = 'HIGH'
ORDER BY legacy_score_last DESC LIMIT 20;

\echo ===Q3_THE_TOP_OF_EACH_SIDE_REGARDLESS_OF_TIER===
SELECT scan_date, ticker,
       ROUND(sep_score_last::numeric,1) AS sep, ROUND(legacy_score_last::numeric,1) AS legacy,
       sep_bar, legacy_bar
FROM mi_ep_score_shadow
WHERE scan_date >= '2026-09-01'
ORDER BY legacy_score_last DESC NULLS LAST LIMIT 10;

\echo ===Q4_HOW_OFTEN_HAS_LEGACY_BEATEN_SEPARATION_SINCE_THE_FLIP===
SELECT scan_date,
       COUNT(*) FILTER (WHERE sep_tier_last = 'HIGH')    AS sep_HIGH,
       COUNT(*) FILTER (WHERE legacy_tier_last = 'HIGH') AS legacy_HIGH
FROM mi_ep_score_shadow
WHERE scan_date >= '2026-08-22'
GROUP BY 1 ORDER BY 1 DESC LIMIT 12;
