-- #539 evidence pull (read-only). Capture-once: output lands in _539_evidence.tsv.
-- Q1: full row history for the two lineages.
\pset format unaligned
\pset fieldsep '\t'
\pset null 'NULL'
\echo === Q1 mi_themes history: crypto + AI lineages ===
SELECT theme_date, name, source, stage, round(score::numeric,1) AS score, rs_avg,
       days_active, consecutive_accelerating, parent_theme,
       array_to_string(tickers, ',') AS tickers,
       left(replace(coalesce(description,''), E'\n', ' '), 220) AS descr
FROM mi_themes
WHERE name IN ('Bitcoin Mining & Crypto Infrastructure Operators',
               'AI Data Center Infrastructure Buildout')
  AND theme_date >= DATE '2026-07-18'
ORDER BY name, theme_date;

\echo === Q2 audit rows 08-03..08-07 naming the lineages or the five tickers ===
SELECT (created_at AT TIME ZONE 'America/New_York')::timestamp(0) AS et_ts,
       event_type,
       left(replace(coalesce(summary,''), E'\n', ' | '), 240) AS summary,
       left(replace(coalesce(detail,''), E'\n', ' | '), 900) AS detail
FROM mi_audit_log
WHERE created_at >= TIMESTAMPTZ '2026-08-03 00:00:00-04'
  AND created_at <  TIMESTAMPTZ '2026-08-08 00:00:00-04'
  AND (summary ILIKE '%Bitcoin Mining%' OR detail ILIKE '%Bitcoin Mining%'
    OR summary ILIKE '%AI Data Center Infrastructure Buildout%'
    OR detail  ILIKE '%AI Data Center Infrastructure Buildout%'
    OR summary ~ '\mHUT\M' OR detail ~ '\mHUT\M'
    OR summary ~ '\mCIFR\M' OR detail ~ '\mCIFR\M'
    OR summary ~ '\mBTDR\M' OR detail ~ '\mBTDR\M')
ORDER BY created_at;

\echo === Q3 which themes hold the five tickers, 08-01..08-07 ===
SELECT theme_date, name, source, stage,
       array_to_string(ARRAY(SELECT t FROM unnest(tickers) t
                             WHERE t IN ('HUT','CIFR','BTDR','AMRC','BLZE')), ',') AS held,
       array_to_string(tickers, ',') AS tickers
FROM mi_themes
WHERE theme_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-07'
  AND tickers && ARRAY['HUT','CIFR','BTDR','AMRC','BLZE']
ORDER BY theme_date, name;

\echo === Q4 funnel + engine-drop + rename events 08-04..08-06 ===
SELECT (created_at AT TIME ZONE 'America/New_York')::timestamp(0) AS et_ts,
       event_type,
       left(replace(coalesce(summary,''), E'\n', ' | '), 240) AS summary,
       left(replace(coalesce(detail,''), E'\n', ' | '), 1200) AS detail
FROM mi_audit_log
WHERE created_at >= TIMESTAMPTZ '2026-08-04 00:00:00-04'
  AND created_at <  TIMESTAMPTZ '2026-08-07 00:00:00-04'
  AND event_type IN ('theme_engine_funnel','theme_auto_retired','theme_retired',
                     'theme_renamed_for_continuity','name_inheritance_blocked',
                     'theme_discovered','shadow_themes_promoted',
                     'theme_pass1_protect_strip','theme_pass1_5_absorption',
                     'theme_sector_cap_dropped','theme_dissolved_flagged_pair')
ORDER BY created_at;

\echo === Q5 board snapshots 08-04 and 08-05 (fixture input) ===
SELECT theme_date, name, source, stage, round(score::numeric,1) AS score,
       array_to_string(tickers, ',') AS tickers, parent_theme
FROM mi_themes
WHERE theme_date IN (DATE '2026-08-04', DATE '2026-08-05')
ORDER BY theme_date, score DESC NULLS LAST, name;
