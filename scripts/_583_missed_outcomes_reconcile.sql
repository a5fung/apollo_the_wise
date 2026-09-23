-- #583 one-shot reconciliation for mi_ep_missed_outcomes.
--
-- WHAT THIS DOES: exactly what agents/market_intelligence/missed_outcomes.py's
-- new `reconcile_missed_outcomes_categories()` does on its first nightly run —
-- this script just applies it to prod NOW instead of waiting for a deploy.
-- Read-only verification already run against prod 2026-08-22 (see PR/session
-- notes) confirms these three counts:
--   - 375 orphaned rows pruned (no longer reproducible from current
--     mi_ep_alerts / mi_ep_scan_log — their source row aged out of
--     retention, or #268's `source='live'` filter now excludes them).
--     high_unentered 279, window_missed 19, moderate_tier 47,
--     breaker_blocked 9, cap_blocked 8, stop_too_wide 6, infra_skip 4,
--     faded_from_orb 2, setup_other 1.
--   - 0 miscategorized rows (every still-reproducible row's stored
--     skip_category already matches a fresh recompute — Step 2 below is a
--     no-op today, kept for completeness/future-proofing).
--   - 58 missing rows backfilled: 27 `high_unentered` (all
--     status='cancelled' HIGHs from 2026-05-11..2026-07-15, silently
--     miscounted as TRADED until the 2026-08-15 cancelled/order_failed fix,
--     by which point they'd aged past the 30-day refresh window), plus 31
--     scan_filter-lineage rows (27 duplicate_scan, 2 outside_top20,
--     2 session_rvol_low) never captured by any single 30-day window.
--
-- SAFE TO RUN MULTIPLE TIMES (idempotent) — re-running finds nothing left
-- to prune/fix/backfill and is a no-op. Wrapped in one transaction so a
-- failure partway through rolls back cleanly.
--
-- Prod runs UTC; CURRENT_DATE can read tomorrow's date after ~20:00 ET.
-- Not a correctness issue for a one-off historical cleanup (it can only
-- ever admit MORE of today's just-in-window rows, never touch the
-- historical orphans/backfill this script exists for) but if running near
-- that boundary, prefer substituting an explicit ET date literal for
-- CURRENT_DATE below.
--
-- Per #583's CARE constraint: this changes what a raw
-- `SELECT skip_category, COUNT(*) FROM mi_ep_missed_outcomes GROUP BY 1`
-- returns for `high_unentered` (298→46), `window_missed` (57→38),
-- `moderate_tier` (113→66), `breaker_blocked` (21→12), `cap_blocked`
-- (16→8), `stop_too_wide` (14→8), `infra_skip` (18→14),
-- `faded_from_orb` (2→0), `setup_other` (16→15), `duplicate_scan`
-- (162→189), `outside_top20` (789→791), `session_rvol_low` (314→316).
-- Every OTHER skip_category is untouched (verified: zero orphans, zero
-- missing rows for adv_low/atr_high/catalyst_downgrade/cooldown/
-- extension_gate/ma_filter/mcap_low/pm_rvol_low/score_below_50 — the
-- populations `adv_floor_556`, `577` Card A, and `577B`'s atr_high citation
-- read all reproduce exactly).

BEGIN;

-- ── Step 1: prune orphans ────────────────────────────────────────────────
-- A stored row whose (ticker, alert_date, source) the CURRENT
-- categorisation/inclusion logic no longer produces at all.
WITH traded AS (
    SELECT ticker, alert_date FROM mi_live_trades
    WHERE status NOT IN ('skipped', 'cancelled', 'order_failed')
    UNION
    SELECT ticker, alert_date FROM mi_paper_trades
),
scan_filtered AS (
    SELECT DISTINCT ON (s.ticker, s.scan_date)
        s.ticker, s.scan_date AS alert_date, 'scan_filter'::TEXT AS source
    FROM mi_ep_scan_log s
    WHERE s.scan_date <= CURRENT_DATE
      AND s.filter_reason IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM traded t WHERE t.ticker = s.ticker AND t.alert_date = s.scan_date)
    ORDER BY s.ticker, s.scan_date, s.created_at DESC
),
moderate AS (
    SELECT DISTINCT ON (a.ticker, a.alert_date)
        a.ticker, a.alert_date, 'moderate_alert'::TEXT AS source
    FROM mi_ep_alerts a
    WHERE a.alert_date <= CURRENT_DATE
      AND a.score_tier = 'MODERATE'
      AND COALESCE(a.source, 'live') = 'live'
      AND NOT EXISTS (SELECT 1 FROM traded t WHERE t.ticker = a.ticker AND t.alert_date = a.alert_date)
    ORDER BY a.ticker, a.alert_date, a.created_at DESC
),
high_unentered AS (
    SELECT DISTINCT ON (a.ticker, a.alert_date)
        a.ticker, a.alert_date, 'high_unentered'::TEXT AS source
    FROM mi_ep_alerts a
    WHERE a.alert_date <= CURRENT_DATE
      AND a.score_tier = 'HIGH'
      AND COALESCE(a.source, 'live') = 'live'
      AND NOT EXISTS (SELECT 1 FROM traded t WHERE t.ticker = a.ticker AND t.alert_date = a.alert_date)
    ORDER BY a.ticker, a.alert_date, a.created_at DESC
),
truth AS (
    SELECT * FROM scan_filtered
    UNION ALL SELECT * FROM moderate
    UNION ALL SELECT * FROM high_unentered
)
DELETE FROM mi_ep_missed_outcomes m
WHERE m.alert_date <= CURRENT_DATE
  AND NOT EXISTS (
      SELECT 1 FROM truth t
      WHERE t.ticker = m.ticker AND t.alert_date = m.alert_date AND t.source = m.source
  );

-- ── Step 2: fix miscategorized rows (verified no-op today, kept for safety) ─
WITH traded AS (
    SELECT ticker, alert_date FROM mi_live_trades
    WHERE status NOT IN ('skipped', 'cancelled', 'order_failed')
    UNION
    SELECT ticker, alert_date FROM mi_paper_trades
),
scan_filtered AS (
    SELECT DISTINCT ON (s.ticker, s.scan_date)
        s.ticker, s.scan_date AS alert_date, 'scan_filter'::TEXT AS source,
        s.filter_reason AS skip_reason
    FROM mi_ep_scan_log s
    WHERE s.scan_date <= CURRENT_DATE
      AND s.filter_reason IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM traded t WHERE t.ticker = s.ticker AND t.alert_date = s.scan_date)
    ORDER BY s.ticker, s.scan_date, s.created_at DESC
),
moderate AS (
    SELECT DISTINCT ON (a.ticker, a.alert_date)
        a.ticker, a.alert_date, 'moderate_alert'::TEXT AS source, NULL::TEXT AS skip_reason
    FROM mi_ep_alerts a
    WHERE a.alert_date <= CURRENT_DATE
      AND a.score_tier = 'MODERATE'
      AND COALESCE(a.source, 'live') = 'live'
      AND NOT EXISTS (SELECT 1 FROM traded t WHERE t.ticker = a.ticker AND t.alert_date = a.alert_date)
    ORDER BY a.ticker, a.alert_date, a.created_at DESC
),
high_unentered AS (
    SELECT DISTINCT ON (a.ticker, a.alert_date)
        a.ticker, a.alert_date, 'high_unentered'::TEXT AS source, sk.skip_reason
    FROM mi_ep_alerts a
    LEFT JOIN LATERAL (
        SELECT skip_reason FROM mi_live_trades lt
        WHERE lt.ticker = a.ticker AND lt.alert_date = a.alert_date
          AND lt.status IN ('skipped', 'cancelled', 'order_failed')
        ORDER BY lt.id DESC LIMIT 1
    ) sk ON TRUE
    WHERE a.alert_date <= CURRENT_DATE
      AND a.score_tier = 'HIGH'
      AND COALESCE(a.source, 'live') = 'live'
      AND NOT EXISTS (SELECT 1 FROM traded t WHERE t.ticker = a.ticker AND t.alert_date = a.alert_date)
    ORDER BY a.ticker, a.alert_date, a.created_at DESC
),
truth AS (
    SELECT ticker, alert_date, source, skip_reason,
        CASE
            WHEN source = 'moderate_alert' THEN 'moderate_tier'
            WHEN skip_reason ILIKE 'block:max_positions%' THEN 'cap_blocked'
            WHEN skip_reason ILIKE 'block:circuit_breaker%' THEN 'breaker_blocked'
            WHEN skip_reason ILIKE 'block:%' THEN 'block_other'
            WHEN skip_reason ILIKE 'window:%' THEN 'window_missed'
            WHEN skip_reason ILIKE 'setup:stop_too_wide%' THEN 'stop_too_wide'
            WHEN skip_reason ILIKE 'setup:faded%' THEN 'faded_from_orb'
            WHEN skip_reason ILIKE 'setup:account_fetch%' OR skip_reason ILIKE 'infra:%' THEN 'infra_skip'
            WHEN skip_reason ILIKE 'setup:%' THEN 'setup_other'
            WHEN source = 'high_unentered' THEN 'high_unentered'
            WHEN skip_reason IS NULL THEN 'filter_other'
            WHEN skip_reason ILIKE '%cooldown%' THEN 'cooldown'
            WHEN skip_reason ILIKE '%m&a%' OR skip_reason ILIKE '%buyout%' OR skip_reason ILIKE '%merger%' THEN 'ma_filter'
            WHEN skip_reason ILIKE '%already scored%' OR skip_reason ILIKE '%duplicate%' THEN 'duplicate_scan'
            WHEN skip_reason ILIKE '%outside top-20%' OR skip_reason ILIKE '%top-20 gap cap%' THEN 'outside_top20'
            WHEN skip_reason ILIKE '%score%' AND skip_reason ILIKE '%< 50%' THEN 'score_below_50'
            WHEN skip_reason ILIKE '%pm_rvol%' OR skip_reason ILIKE '%pre-market rvol%' OR skip_reason ILIKE '%pre-mkt volume%' OR skip_reason ILIKE '%pm volume%' THEN 'pm_rvol_low'
            WHEN skip_reason ILIKE '%session_rvol%' OR skip_reason ILIKE '%session rvol%' OR skip_reason ILIKE '%rel volume%' OR skip_reason ILIKE '%rel_vol%' OR skip_reason ILIKE '%low volume%' OR skip_reason ILIKE '%projected%' THEN 'session_rvol_low'
            WHEN skip_reason ILIKE '%adv%' THEN 'adv_low'
            WHEN skip_reason ILIKE '%atr%' THEN 'atr_high'
            WHEN skip_reason ILIKE '%mcap%' OR skip_reason ILIKE '%market cap%' THEN 'mcap_low'
            WHEN skip_reason ILIKE '%catalyst%' AND (skip_reason ILIKE '%downgrade%' OR skip_reason ILIKE '%routine%') THEN 'catalyst_downgrade'
            WHEN skip_reason ILIKE '%extension%' OR skip_reason ILIKE '%extended%' THEN 'extension_gate'
            ELSE 'filter_other'
        END AS skip_category
    FROM (SELECT * FROM scan_filtered UNION ALL SELECT * FROM moderate UNION ALL SELECT * FROM high_unentered) x
)
UPDATE mi_ep_missed_outcomes m
SET skip_category = t.skip_category,
    skip_reason = t.skip_reason,
    last_refreshed_at = NOW()
FROM truth t
WHERE t.ticker = m.ticker AND t.alert_date = m.alert_date AND t.source = m.source
  AND (m.skip_category IS DISTINCT FROM t.skip_category OR m.skip_reason IS DISTINCT FROM t.skip_reason);

-- ── Step 3: backfill missing rows (with forward returns) ────────────────────
WITH traded AS (
    SELECT ticker, alert_date FROM mi_live_trades
    WHERE status NOT IN ('skipped', 'cancelled', 'order_failed')
    UNION
    SELECT ticker, alert_date FROM mi_paper_trades
),
scan_filtered AS (
    SELECT DISTINCT ON (s.ticker, s.scan_date)
        s.ticker, s.scan_date AS alert_date, 'scan_filter'::TEXT AS source,
        s.filter_reason AS skip_reason, s.ep_score, s.gap_pct, s.rel_volume, s.catalyst_quality
    FROM mi_ep_scan_log s
    WHERE s.scan_date <= CURRENT_DATE
      AND s.filter_reason IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM traded t WHERE t.ticker = s.ticker AND t.alert_date = s.scan_date)
      AND NOT EXISTS (
          SELECT 1 FROM mi_ep_missed_outcomes e
          WHERE e.ticker = s.ticker AND e.alert_date = s.scan_date AND e.source = 'scan_filter'
      )
    ORDER BY s.ticker, s.scan_date, s.created_at DESC
),
moderate AS (
    SELECT DISTINCT ON (a.ticker, a.alert_date)
        a.ticker, a.alert_date, 'moderate_alert'::TEXT AS source, NULL::TEXT AS skip_reason,
        a.ep_score, a.gap_pct, NULL::FLOAT AS rel_volume, a.catalyst_quality
    FROM mi_ep_alerts a
    WHERE a.alert_date <= CURRENT_DATE
      AND a.score_tier = 'MODERATE'
      AND COALESCE(a.source, 'live') = 'live'
      AND NOT EXISTS (SELECT 1 FROM traded t WHERE t.ticker = a.ticker AND t.alert_date = a.alert_date)
      AND NOT EXISTS (
          SELECT 1 FROM mi_ep_missed_outcomes e
          WHERE e.ticker = a.ticker AND e.alert_date = a.alert_date AND e.source = 'moderate_alert'
      )
    ORDER BY a.ticker, a.alert_date, a.created_at DESC
),
high_unentered AS (
    SELECT DISTINCT ON (a.ticker, a.alert_date)
        a.ticker, a.alert_date, 'high_unentered'::TEXT AS source, sk.skip_reason,
        a.ep_score, a.gap_pct, NULL::FLOAT AS rel_volume, a.catalyst_quality
    FROM mi_ep_alerts a
    LEFT JOIN LATERAL (
        SELECT skip_reason FROM mi_live_trades lt
        WHERE lt.ticker = a.ticker AND lt.alert_date = a.alert_date
          AND lt.status IN ('skipped', 'cancelled', 'order_failed')
        ORDER BY lt.id DESC LIMIT 1
    ) sk ON TRUE
    WHERE a.alert_date <= CURRENT_DATE
      AND a.score_tier = 'HIGH'
      AND COALESCE(a.source, 'live') = 'live'
      AND NOT EXISTS (SELECT 1 FROM traded t WHERE t.ticker = a.ticker AND t.alert_date = a.alert_date)
      AND NOT EXISTS (
          SELECT 1 FROM mi_ep_missed_outcomes e
          WHERE e.ticker = a.ticker AND e.alert_date = a.alert_date AND e.source = 'high_unentered'
      )
    ORDER BY a.ticker, a.alert_date, a.created_at DESC
),
base AS (
    SELECT * FROM scan_filtered
    UNION ALL SELECT * FROM moderate
    UNION ALL SELECT * FROM high_unentered
),
with_returns AS (
    SELECT
        b.*,
        d0.open_price AS open_d0, d0.close AS close_d0,
        d1.close AS close_d1, d5.close AS close_d5, d20.close AS close_d20,
        h5.h AS max_high_5d, h20.h AS max_high_20d
    FROM base b
    LEFT JOIN LATERAL (
        SELECT open_price, close FROM mi_daily_closes
        WHERE ticker = b.ticker AND trade_date = b.alert_date
    ) d0 ON TRUE
    LEFT JOIN LATERAL (
        SELECT close FROM mi_daily_closes
        WHERE ticker = b.ticker AND trade_date > b.alert_date
        ORDER BY trade_date ASC LIMIT 1
    ) d1 ON TRUE
    LEFT JOIN LATERAL (
        SELECT close FROM mi_daily_closes
        WHERE ticker = b.ticker AND trade_date > b.alert_date
        ORDER BY trade_date ASC OFFSET 4 LIMIT 1
    ) d5 ON TRUE
    LEFT JOIN LATERAL (
        SELECT close FROM mi_daily_closes
        WHERE ticker = b.ticker AND trade_date > b.alert_date
        ORDER BY trade_date ASC OFFSET 19 LIMIT 1
    ) d20 ON TRUE
    LEFT JOIN LATERAL (
        SELECT MAX(high_price) AS h FROM (
            SELECT high_price FROM mi_daily_closes
            WHERE ticker = b.ticker AND trade_date >= b.alert_date
            ORDER BY trade_date ASC LIMIT 6
        ) x
    ) h5 ON TRUE
    LEFT JOIN LATERAL (
        SELECT MAX(high_price) AS h FROM (
            SELECT high_price FROM mi_daily_closes
            WHERE ticker = b.ticker AND trade_date >= b.alert_date
            ORDER BY trade_date ASC LIMIT 21
        ) x
    ) h20 ON TRUE
)
INSERT INTO mi_ep_missed_outcomes (
    ticker, alert_date, source, skip_reason, skip_category,
    ep_score, gap_pct, rel_volume, catalyst_quality,
    open_d0, close_d0,
    ret_1d, ret_5d, ret_20d, max_high_5d, max_high_20d,
    last_refreshed_at
)
SELECT
    ticker, alert_date, source, skip_reason,
    CASE
        WHEN source = 'moderate_alert' THEN 'moderate_tier'
        WHEN skip_reason ILIKE 'block:max_positions%' THEN 'cap_blocked'
        WHEN skip_reason ILIKE 'block:circuit_breaker%' THEN 'breaker_blocked'
        WHEN skip_reason ILIKE 'block:%' THEN 'block_other'
        WHEN skip_reason ILIKE 'window:%' THEN 'window_missed'
        WHEN skip_reason ILIKE 'setup:stop_too_wide%' THEN 'stop_too_wide'
        WHEN skip_reason ILIKE 'setup:faded%' THEN 'faded_from_orb'
        WHEN skip_reason ILIKE 'setup:account_fetch%' OR skip_reason ILIKE 'infra:%' THEN 'infra_skip'
        WHEN skip_reason ILIKE 'setup:%' THEN 'setup_other'
        WHEN source = 'high_unentered' THEN 'high_unentered'
        WHEN skip_reason IS NULL THEN 'filter_other'
        WHEN skip_reason ILIKE '%cooldown%' THEN 'cooldown'
        WHEN skip_reason ILIKE '%m&a%' OR skip_reason ILIKE '%buyout%' OR skip_reason ILIKE '%merger%' THEN 'ma_filter'
        WHEN skip_reason ILIKE '%already scored%' OR skip_reason ILIKE '%duplicate%' THEN 'duplicate_scan'
        WHEN skip_reason ILIKE '%outside top-20%' OR skip_reason ILIKE '%top-20 gap cap%' THEN 'outside_top20'
        WHEN skip_reason ILIKE '%score%' AND skip_reason ILIKE '%< 50%' THEN 'score_below_50'
        WHEN skip_reason ILIKE '%pm_rvol%' OR skip_reason ILIKE '%pre-market rvol%' OR skip_reason ILIKE '%pre-mkt volume%' OR skip_reason ILIKE '%pm volume%' THEN 'pm_rvol_low'
        WHEN skip_reason ILIKE '%session_rvol%' OR skip_reason ILIKE '%session rvol%' OR skip_reason ILIKE '%rel volume%' OR skip_reason ILIKE '%rel_vol%' OR skip_reason ILIKE '%low volume%' OR skip_reason ILIKE '%projected%' THEN 'session_rvol_low'
        WHEN skip_reason ILIKE '%adv%' THEN 'adv_low'
        WHEN skip_reason ILIKE '%atr%' THEN 'atr_high'
        WHEN skip_reason ILIKE '%mcap%' OR skip_reason ILIKE '%market cap%' THEN 'mcap_low'
        WHEN skip_reason ILIKE '%catalyst%' AND (skip_reason ILIKE '%downgrade%' OR skip_reason ILIKE '%routine%') THEN 'catalyst_downgrade'
        WHEN skip_reason ILIKE '%extension%' OR skip_reason ILIKE '%extended%' THEN 'extension_gate'
        ELSE 'filter_other'
    END AS skip_category,
    ep_score, gap_pct, rel_volume, catalyst_quality,
    open_d0, close_d0,
    CASE WHEN open_d0 > 0 AND close_d1 IS NOT NULL THEN (close_d1 - open_d0) / open_d0 ELSE NULL END AS ret_1d,
    CASE WHEN open_d0 > 0 AND close_d5 IS NOT NULL THEN (close_d5 - open_d0) / open_d0 ELSE NULL END AS ret_5d,
    CASE WHEN open_d0 > 0 AND close_d20 IS NOT NULL THEN (close_d20 - open_d0) / open_d0 ELSE NULL END AS ret_20d,
    CASE WHEN open_d0 > 0 AND max_high_5d IS NOT NULL THEN (max_high_5d - open_d0) / open_d0 ELSE NULL END AS max_high_5d,
    CASE WHEN open_d0 > 0 AND max_high_20d IS NOT NULL THEN (max_high_20d - open_d0) / open_d0 ELSE NULL END AS max_high_20d,
    NOW() AS last_refreshed_at
FROM with_returns
ON CONFLICT (ticker, alert_date, source) DO NOTHING;

-- Sanity check before COMMIT — eyeball this, then COMMIT or ROLLBACK by hand.
SELECT skip_category, COUNT(*) AS n
FROM mi_ep_missed_outcomes
GROUP BY skip_category
ORDER BY skip_category;

COMMIT;
