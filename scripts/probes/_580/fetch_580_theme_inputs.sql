-- READ-ONLY. Capture the exact inputs /themes reads on 2026-09-30 (theme_date falls back to max(theme_date)).
\pset tuples_only on
\pset format unaligned
SELECT json_build_object(
  'today_et', '2026-09-30',
  'themes_date', (SELECT max(theme_date) FROM mi_themes WHERE theme_date <= DATE '2026-09-30'),
  'score_date', (SELECT counts.score_date FROM (
        SELECT score_date, COUNT(*) AS n FROM mi_stock_scores WHERE score_date <= DATE '2026-09-29' GROUP BY score_date) counts
      WHERE counts.n >= 0.5 * (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY n) FROM (
        SELECT COUNT(*) AS n FROM mi_stock_scores WHERE score_date <= DATE '2026-09-29' GROUP BY score_date ORDER BY score_date DESC LIMIT 10) recent)
      ORDER BY counts.score_date DESC LIMIT 1),
  'prior_date', (SELECT MAX(theme_date) FROM mi_themes WHERE theme_date < DATE '2026-09-30')
);
SELECT json_agg(t) FROM (SELECT id, theme_date, name, stage, score, rs_avg, tickers, parent_theme, days_active, consecutive_accelerating, pct_above_20sma, source FROM mi_themes WHERE theme_date = (SELECT max(theme_date) FROM mi_themes WHERE theme_date <= DATE '2026-09-30') ORDER BY score DESC) t;
SELECT json_agg(t) FROM (SELECT name, rs_avg FROM mi_themes WHERE theme_date = (SELECT MAX(theme_date) FROM mi_themes WHERE theme_date < DATE '2026-09-30') AND rs_avg IS NOT NULL) t;
SELECT json_agg(t) FROM (SELECT ticker, rs_composite, rs_1m, rs_3m, rs_6m, rs_rank FROM mi_stock_scores WHERE score_date = (SELECT counts.score_date FROM (
        SELECT score_date, COUNT(*) AS n FROM mi_stock_scores WHERE score_date <= DATE '2026-09-29' GROUP BY score_date) counts
      WHERE counts.n >= 0.5 * (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY n) FROM (
        SELECT COUNT(*) AS n FROM mi_stock_scores WHERE score_date <= DATE '2026-09-29' GROUP BY score_date ORDER BY score_date DESC LIMIT 10) recent)
      ORDER BY counts.score_date DESC LIMIT 1)
    AND ticker = ANY(ARRAY(SELECT DISTINCT unnest(tickers) FROM mi_themes WHERE theme_date = (SELECT max(theme_date) FROM mi_themes WHERE theme_date <= DATE '2026-09-30')))) t;
SELECT json_agg(t) FROM (SELECT theme_name, e_code FROM mi_theme_ecosystems) t;
SELECT json_agg(t) FROM (SELECT e_code, name, description, keyword_stems, exemplars, created_at FROM mi_theme_ecosystems_dynamic WHERE status='active' ORDER BY created_at) t;
