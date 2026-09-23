-- Theme mass-eviction probe, 2026-08-26. READ-ONLY. ONE capture, read many.
\pset pager off
\set QUIET on

\echo ===Q0_now
SELECT now() AS utc_now, (now() AT TIME ZONE 'America/New_York')::date AS et_today;

\echo ===Q1_cooldowns_by_theme_today
SELECT theme_name, count(*) AS n, string_agg(ticker, ',' ORDER BY ticker) AS tickers
FROM mi_validation_cooldowns
WHERE (removed_at AT TIME ZONE 'America/New_York')::date = (now() AT TIME ZONE 'America/New_York')::date
GROUP BY 1 ORDER BY 2 DESC, 1;

\echo ===Q2_cooldown_rows_today
SELECT ticker, theme_name, removal_count, bypassed,
       to_char(removed_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS removed_et,
       (cooldown_until AT TIME ZONE 'America/New_York')::date AS cd_until_et,
       left(coalesce(removal_reason,''),160) AS reason
FROM mi_validation_cooldowns
WHERE (removed_at AT TIME ZONE 'America/New_York')::date = (now() AT TIME ZONE 'America/New_York')::date
ORDER BY theme_name, ticker;

\echo ===Q3_mass_removal_tripwire_14d
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d,
       to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') AS t_et,
       summary, left(coalesce(detail,''),400) AS detail
FROM mi_audit_log
WHERE event_type='validation_mass_removal_name_suspect'
  AND created_at > now() - interval '14 days'
ORDER BY created_at;

\echo ===Q4_theme_event_daily_counts_14d
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, event_type, count(*) AS n
FROM mi_audit_log
WHERE created_at > now() - interval '14 days'
  AND event_type IN ('ticker_revalidated_out','validation_cooldown_triggered','ticker_pruned',
                     'ticker_prune_held_rising','split_applied','theme_retired','theme_auto_retired',
                     'validation_mass_removal_name_suspect','validation_removal_shielded',
                     'validation_rate_limited','anthropic_rate_limited','validation_error',
                     'assignment_error','discovery_error','theme_merged','theme_canonicalized',
                     'theme_engine_run','theme_created','theme_birth_validated','theme_birth_rejected')
GROUP BY 1,2 ORDER BY 1 DESC, 3 DESC;

\echo ===Q5_all_event_types_today
SELECT event_type, count(*) AS n
FROM mi_audit_log
WHERE (created_at AT TIME ZONE 'America/New_York')::date = (now() AT TIME ZONE 'America/New_York')::date
GROUP BY 1 ORDER BY 2 DESC;

\echo ===Q6_revalidated_out_rows_today
SELECT to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') AS t_et,
       summary, left(coalesce(detail,''),220) AS detail
FROM mi_audit_log
WHERE event_type='ticker_revalidated_out'
  AND (created_at AT TIME ZONE 'America/New_York')::date = (now() AT TIME ZONE 'America/New_York')::date
ORDER BY created_at;

\echo ===Q7_theme_counts_by_day_20d
SELECT theme_date, count(*) AS n_themes,
       count(*) FILTER (WHERE stage='Accelerating') AS accel,
       count(*) FILTER (WHERE stage='Mainstream') AS mainstream,
       count(*) FILTER (WHERE stage='Nascent') AS nascent,
       count(*) FILTER (WHERE stage='Fading') AS fading,
       count(*) FILTER (WHERE stage='Retired') AS retired,
       round(avg(cardinality(tickers))::numeric,2) AS avg_members
FROM mi_themes
WHERE theme_date > (now() AT TIME ZONE 'America/New_York')::date - 20
GROUP BY 1 ORDER BY 1 DESC;

\echo ===Q8_stripped_theme_membership_prev_vs_today
WITH strip AS (
  SELECT theme_name, count(*) AS n_removed
  FROM mi_validation_cooldowns
  WHERE (removed_at AT TIME ZONE 'America/New_York')::date = (now() AT TIME ZONE 'America/New_York')::date
  GROUP BY 1
), latest AS (
  SELECT DISTINCT ON (name) name, theme_date, stage, score, cardinality(tickers) AS n_members, tickers
  FROM mi_themes
  WHERE theme_date >= (now() AT TIME ZONE 'America/New_York')::date - 14
  ORDER BY name, theme_date DESC
), prev AS (
  SELECT DISTINCT ON (name) name, theme_date AS prev_date, stage AS prev_stage,
         cardinality(tickers) AS prev_members
  FROM mi_themes
  WHERE theme_date < (now() AT TIME ZONE 'America/New_York')::date
    AND theme_date >= (now() AT TIME ZONE 'America/New_York')::date - 14
  ORDER BY name, theme_date DESC
)
SELECT s.theme_name, s.n_removed, p.prev_date, p.prev_stage, p.prev_members,
       l.theme_date AS latest_date, l.stage AS latest_stage, l.n_members AS latest_members,
       CASE WHEN p.prev_members IS NULL THEN NULL
            ELSE round(100.0*s.n_removed/p.prev_members,1) END AS pct_of_prev
FROM strip s
LEFT JOIN prev p ON p.name = s.theme_name
LEFT JOIN latest l ON l.name = s.theme_name
ORDER BY s.n_removed DESC, s.theme_name;

\echo ===Q9_rs_history_stripped_tickers
WITH tk AS (
  SELECT DISTINCT ticker FROM mi_validation_cooldowns
  WHERE (removed_at AT TIME ZONE 'America/New_York')::date = (now() AT TIME ZONE 'America/New_York')::date
)
SELECT s.ticker, s.score_date, round(s.rs_composite::numeric,1) AS rs
FROM mi_stock_scores s JOIN tk ON tk.ticker = s.ticker
WHERE s.score_date >= (now() AT TIME ZONE 'America/New_York')::date - 10
  AND s.rs_composite IS NOT NULL
ORDER BY s.ticker, s.score_date DESC;

\echo ===Q10_stripped_tickers_in_ep_surfaces_30d
WITH tk AS (
  SELECT DISTINCT ticker FROM mi_validation_cooldowns
  WHERE (removed_at AT TIME ZONE 'America/New_York')::date = (now() AT TIME ZONE 'America/New_York')::date
)
SELECT 'alert' AS surface, a.ticker, a.alert_date::text AS d, a.score_tier,
       round(a.ep_score::numeric,1) AS score, a.in_active_theme::text AS in_theme
FROM mi_ep_alerts a JOIN tk ON tk.ticker=a.ticker
WHERE a.alert_date >= (now() AT TIME ZONE 'America/New_York')::date - 30
UNION ALL
SELECT 'scan', l.ticker, l.scan_date::text, coalesce(l.score_tier,'-'),
       round(coalesce(l.ep_score,0)::numeric,1), coalesce(l.filter_reason,'-')
FROM mi_ep_scan_log l JOIN tk ON tk.ticker=l.ticker
WHERE l.scan_date >= (now() AT TIME ZONE 'America/New_York')::date - 30
ORDER BY 1,2,3;

\echo ===Q11_stripped_tickers_theme_coverage_now
WITH tk AS (
  SELECT DISTINCT ticker FROM mi_validation_cooldowns
  WHERE (removed_at AT TIME ZONE 'America/New_York')::date = (now() AT TIME ZONE 'America/New_York')::date
), latest AS (
  SELECT DISTINCT ON (name) name, theme_date, stage, tickers
  FROM mi_themes
  WHERE theme_date >= (now() AT TIME ZONE 'America/New_York')::date - 7
  ORDER BY name, theme_date DESC
)
SELECT tk.ticker,
       coalesce(string_agg(l.name || ' [' || l.stage || ']', ' | ' ORDER BY l.name), '<none>') AS still_in
FROM tk LEFT JOIN latest l ON tk.ticker = ANY(l.tickers) AND l.stage <> 'Retired'
GROUP BY 1 ORDER BY 1;

\echo ===Q12_audit_window_tonight
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') AS t_et,
       event_type, left(coalesce(summary,''),150) AS summary
FROM mi_audit_log
WHERE created_at > now() - interval '30 hours'
  AND event_type NOT IN ('ticker_revalidated_out','validation_cooldown_triggered')
ORDER BY created_at;

\echo ===Q13_split_and_lifecycle_detail_08_20_onwards
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, event_type,
       left(coalesce(summary,''),200) AS summary, left(coalesce(detail,''),240) AS detail
FROM mi_audit_log
WHERE (created_at AT TIME ZONE 'America/New_York')::date >= DATE '2026-08-20'
  AND event_type IN ('split_applied','theme_merged','theme_canonicalized','theme_retired',
                     'theme_auto_retired','validation_mass_removal_name_suspect','theme_created')
ORDER BY created_at;

\echo ===Q14_cooldown_history_30d_by_day
SELECT (removed_at AT TIME ZONE 'America/New_York')::date AS d, count(*) AS n,
       count(DISTINCT theme_name) AS n_themes
FROM mi_validation_cooldowns
WHERE removed_at > now() - interval '45 days'
GROUP BY 1 ORDER BY 1 DESC;

\echo ===Q15_active_theme_ticker_set_size
WITH latest AS (
  SELECT DISTINCT ON (name) name, theme_date, stage, tickers
  FROM mi_themes WHERE theme_date >= (now() AT TIME ZONE 'America/New_York')::date - 7
  ORDER BY name, theme_date DESC
)
SELECT count(*) FILTER (WHERE stage<>'Retired') AS active_themes,
       count(*) FILTER (WHERE stage IN ('Accelerating','Mainstream')) AS accel_main_themes,
       (SELECT count(DISTINCT t) FROM latest, unnest(tickers) t WHERE stage IN ('Accelerating','Mainstream')) AS r4_bonus_tickers
FROM latest;

\echo ===Q16_prune_events_today_detail
SELECT to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') AS t_et, event_type,
       left(coalesce(summary,''),180) AS summary
FROM mi_audit_log
WHERE event_type IN ('ticker_pruned','ticker_prune_held_rising')
  AND created_at > now() - interval '8 days'
ORDER BY created_at DESC;

\echo ===Q17_END
SELECT 1;
