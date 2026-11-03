-- Read-only export of the Apollo Trades dashboard snapshot — the LIVE book only
-- (mi_live_trades WHERE account_mode='live'; #480). Output file is still the legacy
-- name apollo_trades_paper.json (rename to apollo_trades.json is the remaining #480 step).
--
-- Feeds portfolio-app2's "Apollo Trades" page (Streamlit Cloud — CANNOT reach
-- the private Postgres; reads the committed apollo_trades_paper.json as SoT
-- until the 7/15 db-flip over Tailscale). Sibling of export_theme_snapshot.sql.
-- The 2026-06-03 original export was ad-hoc and unsaved — the snapshot then
-- silently went stale for a week (operator caught it 6/10). This file is the
-- durable regeneration path:
--
--   ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo \
--     -d apollo -A -t -X" < scripts/export_trades_snapshot.sql \
--     > ../portfolio-app2/apollo_trades_paper.json
--   (then commit+push portfolio-app2 — Streamlit Cloud redeploys on push)
--
-- Schema mirrors apollo_data._load_from_snapshot: status 'filled' maps to
-- 'open'; exit_price = last exit leg's price. `exits` is currently
-- DOUBLE-ENCODED jsonb (a jsonb string containing the array — the #179/#216
-- codec class), so parse defensively: handle both string and array forms.
--
-- Open-position inputs (#706): side, current_price (+ _date), market_value, account_equity (+ _date). The names are
-- the optional columns portfolio-app2's apollo_data._load_from_snapshot documents; the dashboard turns them into
-- Size % and Stop % and prints a dash for any that is NULL (it never estimates one).
-- export_day = the ET calendar date this export runs on: the upper bound for the close, so a price is always
-- "the latest close on or before the export's ET date", whatever UTC date the container clock shows.
WITH export_day AS (SELECT (now() AT TIME ZONE 'America/New_York')::date AS et_date)
SELECT COALESCE(json_agg(t), '[]'::json) FROM (
    SELECT ticker,
           signal_type AS entry_strategy,
           alert_date,
           filled_at,
           closed_at,
           CASE WHEN status = 'filled' THEN 'open' ELSE status END AS status,
           entry_price::float8 AS entry_price,
           stop_price::float8 AS stop_price,
           -- Original entry risk (2026-10-15): the dashboard's R used the CURRENT stop, which trails above entry on
           -- every winner, so all 10 winners were dropped as 'corrupt stop' and avg R read -1.00. These two feed
           -- the same original-risk frame as sell_discipline.trade_risk_per_share (entry - hard_stop, else entry - orb_low).
           hard_stop::float8 AS hard_stop,
           orb_low::float8 AS orb_low,
           entry_shares::float8 AS entry_shares,
           COALESCE(total_pnl, 0)::float8 AS total_pnl,
           regime,
           gap_pct::float8 AS gap_pct,
           catalyst_quality,
           COALESCE(ep_score, 0)::float8 AS ep_score,
           account_mode,
           lowest_price_seen::float8 AS lowest_price_seen,
           highest_price_seen::float8 AS highest_price_seen,
           (CASE WHEN jsonb_typeof(exits) = 'string'
                 THEN (exits #>> '{}')::jsonb
                 ELSE exits END -> -1 ->> 'price')::float8 AS exit_price,
           -- #706 (his 2026-10-21 stats; the repo went PRIVATE 2026-10-22, so the account figures may be exported):
           -- side. mi_live_trades stores NO side column, and the broker position's side (what /trades reads at render time,
           -- trade_stats.read_open_position_stats) cannot be reached from this export, so the ORIGINAL stop's geometry is
           -- the only source: a stop below the entry = long, above = short. NULL, never a guess, when hard_stop and orb_low
           -- are both missing or the stop equals the entry; the dashboard then shows a dash for Stop %.
           CASE WHEN COALESCE(hard_stop, orb_low) < entry_price THEN 'long'
                WHEN COALESCE(hard_stop, orb_low) > entry_price THEN 'short' END AS side,
           -- open rows only: the latest stored close on or before the export's ET date (NULL when the ticker has none) and
           -- the shares still held (entry minus every exit leg's shares), so a sold third does not inflate the size.
           -- market_value is that unsigned magnitude (remaining shares x close), for a short too; the dashboard takes abs().
           CASE WHEN status = 'filled' THEN (SELECT d.close FROM mi_daily_closes d
                                             WHERE d.ticker = mi_live_trades.ticker AND d.trade_date <= (SELECT et_date FROM export_day)
                                             ORDER BY d.trade_date DESC LIMIT 1)::float8 END AS current_price,
           CASE WHEN status = 'filled' THEN (SELECT d.trade_date FROM mi_daily_closes d
                                             WHERE d.ticker = mi_live_trades.ticker AND d.trade_date <= (SELECT et_date FROM export_day)
                                             ORDER BY d.trade_date DESC LIMIT 1) END AS current_price_date,
           CASE WHEN status = 'filled' THEN (
               (SELECT d.close FROM mi_daily_closes d
                 WHERE d.ticker = mi_live_trades.ticker AND d.trade_date <= (SELECT et_date FROM export_day)
                 ORDER BY d.trade_date DESC LIMIT 1)
               * (entry_shares - COALESCE((SELECT sum((x ->> 'shares')::float8)
                                           FROM jsonb_array_elements(CASE WHEN jsonb_typeof(exits) = 'string'
                                                                          THEN (exits #>> '{}')::jsonb ELSE exits END) x), 0))
           )::float8 END AS market_value,
           -- the account's latest equity snapshot (per account_mode), the denominator /trades uses for its own book, and
           -- that snapshot's own date (account_equity_date) so a stale equity shows on the page instead of being assumed.
           -- WHEN the row is written: scheduler._account_equity_snapshot_job, CronTrigger hour=16 minute=12 Mon-Fri ET
           -- (after eod_cleanup 16:05), one row per (snapshot_date, account_mode), first write wins (ON CONFLICT DO NOTHING).
           -- No row is written when LIVE_TRADING_ENABLED is off or Alpaca get_account fails. This export runs daily at
           -- ~23:30 UTC (18:30 ET in EST, 19:30 in EDT), 2-3 hours AFTER that job: on a trading day it reads TODAY's equity;
           -- on Sat/Sun/holidays the latest row is the prior trading day's, the same day as the latest close, so not stale.
           -- The one stale case is a missed 16:12 run (yesterday's equity beside today's close); the dashboard flags it by
           -- comparing account_equity_date with current_price_date on the same row.
           (SELECT e.equity FROM mi_account_equity_snapshots e WHERE e.account_mode = mi_live_trades.account_mode
             ORDER BY e.snapshot_date DESC, e.created_at DESC LIMIT 1)::float8 AS account_equity,
           (SELECT e.snapshot_date FROM mi_account_equity_snapshots e WHERE e.account_mode = mi_live_trades.account_mode
             ORDER BY e.snapshot_date DESC, e.created_at DESC LIMIT 1) AS account_equity_date
    FROM mi_live_trades
    WHERE status IN ('filled', 'closed', 'stopped')
      AND account_mode = 'live'   -- #480: LIVE book only. Without this, dual-account
                                  -- paper/staged rows leak onto the operator-facing live
                                  -- Trades dash (flagged 7/17, now that real money is live).
    ORDER BY filled_at NULLS LAST, closed_at
) t;
