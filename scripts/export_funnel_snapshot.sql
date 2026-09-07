-- #589 — read-only export of the EP SCAN FUNNEL snapshot for portfolio-app2's
-- "Apollo Funnel" page (funnel-over-time + the rejection scorecard).
--
-- WHY THIS FILE EXISTS. The first funnel snapshot was generated ad hoc and never
-- committed as a query — the exact failure export_trades_snapshot.sql was written
-- to end ("the 2026-06-03 original export was ad-hoc and unsaved — the snapshot
-- then silently went stale for a week"). This is the durable regeneration path,
-- run daily by scripts/auto_export_snapshots.sh on the prod host.
--
--   ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo \
--     -d apollo -A -t -X" < scripts/export_funnel_snapshot.sql \
--     > ../portfolio-app2/apollo_funnel_snapshot.json
--
-- CONTRACT — consumed by portfolio-app2/funnel_data.py `_load_raw`: five row
-- lists keyed scan/graded/alerts/trades/outcomes, plus generated_at.
--
-- ⚠ THE ONE COLLAPSE THAT MATTERS, PORTED NOT INVENTED. mi_ep_scan_log repeats a
-- ticker per scan tick, so the funnel counts TICKER-DAYS, not rows. The live
-- /scanned surface collapses with `DISTINCT ON (ticker) ... ORDER BY ticker,
-- scan_time_et DESC NULLS LAST, id DESC` (db.get_ep_scanned_day, ~:10031) — the
-- LAST state a ticker reached that day. This export uses that exact ordering, so
-- the dashboard and /scanned cannot disagree about a day. If that query changes,
-- change this in the same commit; a silent drift would put two contradicting
-- numbers in front of the operator, which is worse than not shipping the page.
--
-- READ-ONLY: SELECT only. No writes, no money path, no grade or alert input.
--
-- ⚠ COVERAGE CLIFFS funnel_data.py already documents and must keep being told
-- the truth about — do NOT trim a window here to make a chart look smoother:
--   · mi_ep_scan_log's first row is 2026-04-13 (not March).
--   · 2026-08-24 is a CAPTURE regime change: universe-floor rows begin then and
--     daily ticker counts jump ~10x. Shares and totals are NOT comparable across it.
--   · mi_catalyst_tier_shadow begins 2026-08-24; `graded_cut` cannot resolve before.
--   · mi_ep_alerts begins 2026-05-11, and 86 scored HIGH/MODERATE names before
--     2026-05-08 have no alerts row at all (#486, 2026-09-07) — an alerts join
--     undercounts early; scan_row.score_tier is the fallback funnel_data.py uses.
-- Every row from 2026-04-13 ships and the dashboard draws the boundaries.
SELECT json_build_object(
  'generated_at', to_char(now() AT TIME ZONE 'America/New_York',
                          'YYYY-MM-DD"T"HH24:MI:SS') || ' ET',
  'scan', COALESCE((SELECT json_agg(s) FROM (
      SELECT DISTINCT ON (scan_date, ticker)
             ticker, scan_date, filter_reason, score_tier, ep_score, gap_pct,
             pm_rvol, rel_volume, adv, prev_close, catalyst_quality, rank_by_gap
        FROM mi_ep_scan_log
       WHERE scan_date >= DATE '2026-04-13'
       ORDER BY scan_date, ticker, scan_time_et DESC NULLS LAST, id DESC) s),
    '[]'::json),
  'graded', COALESCE((SELECT json_agg(g) FROM (
      SELECT ticker, scan_date, live_ep_score, live_tier, live_quality_last,
             live_side, gap_pct_last, adv_dollar
        FROM mi_catalyst_tier_shadow
       WHERE scan_date >= DATE '2026-04-13'
       ORDER BY scan_date, ticker) g), '[]'::json),
  'alerts', COALESCE((SELECT json_agg(a) FROM (
      SELECT DISTINCT ON (alert_date, ticker)
             ticker, alert_date, score_tier, ep_score, gap_pct, catalyst_quality
        FROM mi_ep_alerts
       WHERE alert_date >= DATE '2026-04-13'
       ORDER BY alert_date, ticker, id DESC) a), '[]'::json),
  'trades', COALESCE((SELECT json_agg(t) FROM (
      SELECT ticker, alert_date, status, account_mode, skip_reason, total_pnl
        FROM mi_live_trades
       WHERE alert_date >= DATE '2026-04-13'
       ORDER BY alert_date, ticker) t), '[]'::json),
  'outcomes', COALESCE((SELECT json_agg(o) FROM (
      SELECT DISTINCT ON (alert_date, ticker)
             ticker, alert_date, max_high_5d, ret_1d, ret_5d,
             setup_at_open, open_gap_pct, last_refreshed_at
        FROM mi_ep_missed_outcomes
       WHERE alert_date >= DATE '2026-04-13'
       ORDER BY alert_date, ticker, last_refreshed_at DESC NULLS LAST) o),
    '[]'::json)
);
