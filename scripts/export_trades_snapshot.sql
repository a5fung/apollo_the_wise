-- Read-only export of the Apollo Trades dashboard snapshot (mi_live_trades).
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
SELECT COALESCE(json_agg(t), '[]'::json) FROM (
    SELECT ticker,
           signal_type AS entry_strategy,
           alert_date,
           filled_at,
           closed_at,
           CASE WHEN status = 'filled' THEN 'open' ELSE status END AS status,
           entry_price::float8 AS entry_price,
           stop_price::float8 AS stop_price,
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
                 ELSE exits END -> -1 ->> 'price')::float8 AS exit_price
    FROM mi_live_trades
    WHERE status IN ('filled', 'closed', 'stopped')
    ORDER BY filled_at NULLS LAST, closed_at
) t;
