-- Follow-up capture, 2026-08-26. READ-ONLY.
\pset pager off

\echo ===R1_metric_exact_theme_count_active
SELECT COUNT(DISTINCT name) AS metric_value FROM mi_themes
WHERE stage != 'Retired' AND theme_date >= CURRENT_DATE - INTERVAL '7 days';

\echo ===R1b_metric_vs_live_by_day
WITH d AS (SELECT generate_series((now() AT TIME ZONE 'America/New_York')::date - 20,
                                  (now() AT TIME ZONE 'America/New_York')::date, '1 day')::date AS dd)
SELECT dd,
  (SELECT count(DISTINCT name) FROM mi_themes t WHERE t.stage<>'Retired' AND t.theme_date BETWEEN dd-7 AND dd) AS metric_7d_distinct_names,
  (SELECT count(*) FROM (SELECT DISTINCT ON (name) name, stage FROM mi_themes t2
       WHERE t2.theme_date BETWEEN dd-7 AND dd ORDER BY name, theme_date DESC) x WHERE x.stage<>'Retired') AS live_latest_row_active,
  (SELECT count(*) FROM mi_themes t3 WHERE t3.theme_date=dd AND t3.stage<>'Retired') AS same_day_rows
FROM d ORDER BY dd DESC;

\echo ===R2_oil_theme_membership_history
SELECT theme_date, name, stage, cardinality(tickers) AS n, array_to_string(tickers,',') AS members
FROM mi_themes
WHERE name = 'Oil Refining & Marketing' AND theme_date >= (now() AT TIME ZONE 'America/New_York')::date - 20
ORDER BY theme_date DESC;

\echo ===R3_energy_cluster_theme_names_20d
SELECT theme_date, name, stage, cardinality(tickers) AS n
FROM mi_themes
WHERE theme_date >= (now() AT TIME ZONE 'America/New_York')::date - 20
  AND (name ILIKE '%oil%' OR name ILIKE '%refin%' OR name ILIKE '%midstream%'
       OR name ILIKE '%utility%' OR name ILIKE '%utilities%' OR name ILIKE '%energy%'
       OR name ILIKE '%drilling%' OR name ILIKE '%gas%' OR name ILIKE '%electric%' OR name ILIKE '%power%')
ORDER BY theme_date DESC, name;

\echo ===R4_stripped17_still_in_today_oil_theme
WITH t AS (SELECT tickers FROM mi_themes WHERE name='Oil Refining & Marketing'
           AND theme_date=(now() AT TIME ZONE 'America/New_York')::date LIMIT 1),
     s AS (SELECT ticker FROM mi_validation_cooldowns
           WHERE theme_name='Oil Refining & Marketing'
             AND (removed_at AT TIME ZONE 'America/New_York')::date=(now() AT TIME ZONE 'America/New_York')::date)
SELECT s.ticker, (s.ticker = ANY((SELECT tickers FROM t)))::text AS still_in_today_snapshot
FROM s ORDER BY 1;

\echo ===R5_cooldowns_by_dow_45d
SELECT to_char(removed_at AT TIME ZONE 'America/New_York','Dy') AS dow,
       (removed_at AT TIME ZONE 'America/New_York')::date AS d, count(*) AS n
FROM mi_validation_cooldowns WHERE removed_at > now() - interval '45 days'
GROUP BY 1,2 ORDER BY 2 DESC;

\echo ===R6_ticker_pruned_ever_in_audit
SELECT event_type, count(*) AS n, min(created_at)::date AS first, max(created_at)::date AS last
FROM mi_audit_log WHERE event_type IN ('ticker_pruned','ticker_prune_held_rising','theme_constituent_churn','theme_composition_churn')
GROUP BY 1 ORDER BY 1;

\echo ===R7_constituent_churn_detail_8d
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') AS t_et, event_type,
       left(coalesce(summary,''),300) AS summary, left(coalesce(detail,''),600) AS detail
FROM mi_audit_log WHERE event_type IN ('theme_constituent_churn','theme_composition_churn','theme_cap_drop','theme_sector_cap_dropped')
  AND created_at > now() - interval '8 days' ORDER BY created_at DESC;

\echo ===R8_r4_bonus_set_membership_of_stripped
WITH tk AS (SELECT DISTINCT ticker FROM mi_validation_cooldowns
            WHERE (removed_at AT TIME ZONE 'America/New_York')::date=(now() AT TIME ZONE 'America/New_York')::date),
     latest AS (SELECT DISTINCT ON (name) name, stage, tickers, theme_date FROM mi_themes
                WHERE theme_date >= (now() AT TIME ZONE 'America/New_York')::date - 7 ORDER BY name, theme_date DESC),
     prev AS (SELECT DISTINCT ON (name) name, stage, tickers FROM mi_themes
              WHERE theme_date BETWEEN (now() AT TIME ZONE 'America/New_York')::date - 8 AND (now() AT TIME ZONE 'America/New_York')::date - 1
              ORDER BY name, theme_date DESC)
SELECT tk.ticker,
  EXISTS (SELECT 1 FROM prev p WHERE p.stage IN ('Accelerating','Mainstream') AND tk.ticker = ANY(p.tickers)) AS had_r4_bonus_yday,
  EXISTS (SELECT 1 FROM latest l WHERE l.stage IN ('Accelerating','Mainstream') AND tk.ticker = ANY(l.tickers)) AS has_r4_bonus_today
FROM tk ORDER BY 1;

\echo ===R9_ep_alerts_last_10d
SELECT alert_date, ticker, score_tier, round(ep_score::numeric,1) AS score, in_active_theme,
       coalesce(theme_gated_tier,'-') AS gated_tier, coalesce(source,'live') AS src
FROM mi_ep_alerts WHERE alert_date >= (now() AT TIME ZONE 'America/New_York')::date - 10
ORDER BY alert_date DESC, ticker;

\echo ===R10_theme_engine_run_timeline_today
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') AS t_et, event_type,
       left(coalesce(summary,''),200) AS summary
FROM mi_audit_log
WHERE (created_at AT TIME ZONE 'America/New_York')::date=(now() AT TIME ZONE 'America/New_York')::date
  AND (event_type LIKE 'theme%' OR event_type LIKE 'validation%' OR event_type LIKE 'assignment%'
       OR event_type IN ('ticker_revalidated_out','shadow_themes_promoted','description_generated'))
ORDER BY created_at;

\echo ===R11_theme_funnel_8d
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, left(coalesce(summary,''),260) AS summary
FROM mi_audit_log WHERE event_type='theme_engine_funnel' AND created_at > now() - interval '10 days'
ORDER BY created_at DESC;

\echo ===R12_END
SELECT 1;
