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
-- ⚠ score_date is deliberately NOT `max(score_date)` — that published an EMPTY
-- stock_scores over good data roughly once a month (2026-05-30, 07-05, 07-12, and
-- 08-08 when it was finally caught).
--
-- HOW: `score_single_ticker` (rs_engine.py) writes ONE on-demand row stamped with the
-- CALENDAR date, so a single lookup of a held name on a Saturday — FIGS, 2026-08-08 —
-- creates a score_date whose entire population is that one row. A real nightly run
-- writes ~2,400. `max()` then picks the stray, the ticker filter below matches nothing,
-- and the dashboard loses every per-stock score until the next weekday export. Nothing
-- errors; the field just goes quietly empty.
--
-- FIX: take the newest date that actually looks like a RUN. The bar is derived from the
-- data (half the median of the last 10 populated days) rather than a hardcoded row
-- count, so it tracks universe growth and needs no maintenance. A stray 1-row day is ~3
-- orders of magnitude below it; a genuine run is at or above it. A partially-failed run
-- is correctly rejected too, which is the more valuable half of this.
WITH usable_score_date AS (
    SELECT score_date
      FROM mi_stock_scores
     GROUP BY score_date
    HAVING count(*) >= 0.5 * (
        SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY n)
          FROM (SELECT count(*) AS n FROM mi_stock_scores
                 GROUP BY score_date ORDER BY score_date DESC LIMIT 10) recent
    )
     ORDER BY score_date DESC
     LIMIT 1
)
SELECT json_build_object(
    'generated_at', now(),
    'window_weeks', 24,
    'score_date', (SELECT score_date FROM usable_score_date),
    'themes', (
        SELECT COALESCE(json_agg(t), '[]'::json) FROM (
            SELECT m.theme_date, m.name, m.stage, m.rs_avg, m.pct_above_20sma,
                   m.tickers, m.days_active, m.consecutive_accelerating, m.score, m.description,
                   e.e_code   -- #194: theme→ecosystem mapping so the dash can group/rank by ecosystem (ADR 0032)
            FROM mi_themes m
            LEFT JOIN mi_theme_ecosystems e ON e.theme_name = m.name
            WHERE m.theme_date >= current_date - interval '24 weeks'
        ) t
    ),
    'stock_scores', (
        SELECT COALESCE(json_agg(s), '[]'::json) FROM (
            SELECT ticker, rs_composite, rs_rank, sector, close, sma_50
            FROM mi_stock_scores
            WHERE score_date = (SELECT score_date FROM usable_score_date)
              AND ticker = ANY(ARRAY(
                  SELECT DISTINCT unnest(tickers)
                  FROM mi_themes
                  WHERE theme_date >= current_date - interval '24 weeks'
              ))
        ) s
    )
);
