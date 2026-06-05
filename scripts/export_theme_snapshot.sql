-- Read-only export of the Theme-Dashboard snapshot (mi_themes + bounded mi_stock_scores).
--
-- Feeds portfolio-app2's "Apollo Themes" page, which runs on Streamlit Cloud and
-- CANNOT reach the private Postgres directly. Mirrors the apollo_trades_paper.json
-- snapshot-adapter pattern: a point-in-time export the cloud app reads as its SoT.
--
-- Emits ONE JSON object on stdout. Run read-only:
--   docker exec -i apollo-postgres psql -U apollo -d apollo -A -t -X -f - < export_theme_snapshot.sql
-- or pipe the file in (see scripts/ usage / the daily auto-export job, #193).
--
-- Window = 24 weeks (matches the grid view's max "weeks of history" slider). The
-- mi_stock_scores slice is bounded to the UNION of theme tickers across the FULL
-- window (not just the latest week) — the detail view can reference older members.
SELECT json_build_object(
    'generated_at', now(),
    'window_weeks', 24,
    'score_date', (SELECT max(score_date) FROM mi_stock_scores),
    'themes', (
        SELECT COALESCE(json_agg(t), '[]'::json) FROM (
            SELECT theme_date, name, stage, rs_avg, pct_above_20sma,
                   tickers, days_active, consecutive_accelerating, score, description
            FROM mi_themes
            WHERE theme_date >= current_date - interval '24 weeks'
        ) t
    ),
    'stock_scores', (
        SELECT COALESCE(json_agg(s), '[]'::json) FROM (
            SELECT ticker, rs_composite, rs_rank, sector, close, sma_50
            FROM mi_stock_scores
            WHERE score_date = (SELECT max(score_date) FROM mi_stock_scores)
              AND ticker = ANY(ARRAY(
                  SELECT DISTINCT unnest(tickers)
                  FROM mi_themes
                  WHERE theme_date >= current_date - interval '24 weeks'
              ))
        ) s
    )
);
