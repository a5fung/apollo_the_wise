-- #593 — verify the standing predicate wired into data_gated_reviews.yaml
-- (review_id: sustain_reject_tradeable_miss_rate_593). READ-ONLY, $0, run ONCE.
--
-- Purpose: (1) run the exact predicate and confirm it returns 0 (not ready — expected,
-- both prior signed reads found the rate well under 10%); (2) run an expanded version of
-- the same funnel that also reports the settled-close basis and raw breach counts, to
-- confirm the wired SQL reproduces the hand-derived 2026-09-01 numbers
-- (docs/analysis/593_sustain_revert_2026-09-01.md: n=87, MFE tradeable-miss 4/87=4.6%,
-- SETTLED tradeable-miss 1/87=1.1%) before trusting it to self-evaluate going forward.
--
-- Run:
--   ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|~|' -P pager=off" \
--     < scripts/probes/_593_predicate_verify_2026-09-03.sql > scripts/probes/_593_predicate_verify_2026-09-03_out.psv

\echo ===Q1_PREDICATE_AS_WIRED===
WITH window_days AS (
  SELECT DISTINCT trade_date FROM mi_daily_closes
  ORDER BY trade_date DESC LIMIT 30
),
win AS (
  SELECT MIN(trade_date) AS floor_date FROM window_days
),
raw_rejects AS (
  SELECT detail::jsonb->>'ticker' AS ticker,
         (created_at AT TIME ZONE 'America/New_York')::date AS decline_date,
         (detail::jsonb->>'rt_gap')::numeric AS rt_gap,
         created_at
  FROM mi_audit_log
  WHERE event_type = 'ep_rt_sustain_reject'
    AND detail::jsonb->>'ticker' IS NOT NULL
    AND created_at AT TIME ZONE 'America/New_York' >= (SELECT floor_date FROM win)
),
rejects AS (
  SELECT DISTINCT ON (ticker, decline_date) ticker, decline_date, rt_gap
  FROM raw_rejects
  ORDER BY ticker, decline_date, created_at ASC
),
catches AS (
  SELECT DISTINCT detail::jsonb->>'ticker' AS ticker,
         (created_at AT TIME ZONE 'America/New_York')::date AS catch_date
  FROM mi_audit_log
  WHERE event_type = 'ep_rt_universe_catch'
    AND created_at AT TIME ZONE 'America/New_York' >= (SELECT floor_date FROM win)
),
net_declined AS (
  SELECT r.ticker, r.decline_date, r.rt_gap
  FROM rejects r
  WHERE NOT EXISTS (
    SELECT 1 FROM catches c
    WHERE c.ticker = r.ticker AND c.catch_date = r.decline_date
  )
),
bars AS (
  SELECT ticker, trade_date, high_price, close, volume,
         LAG(close) OVER (PARTITION BY ticker ORDER BY trade_date) AS prev_close
  FROM mi_daily_closes
  WHERE ticker IN (SELECT DISTINCT ticker FROM rejects)
    AND trade_date >= (SELECT floor_date FROM win) - INTERVAL '10 days'
),
scored AS (
  SELECT nd.ticker, nd.decline_date,
         b0.prev_close, b0.close AS close_d0, b0.high_price AS high_d0,
         b0.volume AS volume_d0,
         b0.prev_close * (1 + nd.rt_gap / 100.0) AS declined_level
  FROM net_declined nd
  JOIN bars b0 ON b0.ticker = nd.ticker AND b0.trade_date = nd.decline_date
  WHERE b0.prev_close IS NOT NULL AND b0.prev_close > 0
),
fwd AS (
  SELECT sc.ticker, sc.decline_date, MAX(fb.high_price) AS mfe_high
  FROM scored sc
  JOIN LATERAL (
    SELECT b.high_price
    FROM mi_daily_closes b
    WHERE b.ticker = sc.ticker AND b.trade_date >= sc.decline_date
    ORDER BY b.trade_date
    LIMIT 6
  ) fb ON TRUE
  GROUP BY sc.ticker, sc.decline_date
),
funnel AS (
  SELECT
    (sc.close_d0 - sc.prev_close) / sc.prev_close >= 0.09 AS held_floor_d0,
    (sc.volume_d0 * sc.close_d0) >= 50000000 AS cleared_dollar_vol,
    sc.high_d0 >= sc.declined_level AS entry_reachable,
    (fw.mfe_high IS NOT NULL AND fw.mfe_high >= sc.declined_level * 1.20) AS breach_mfe
  FROM scored sc
  LEFT JOIN fwd fw ON fw.ticker = sc.ticker AND fw.decline_date = sc.decline_date
)
SELECT CASE
         WHEN scoreable < 30 THEN 0
         WHEN 10 * tradeable_misses > scoreable THEN 1
         ELSE 0
       END AS ready
FROM (
  SELECT
    COUNT(*) AS scoreable,
    COUNT(*) FILTER (
      WHERE held_floor_d0 AND cleared_dollar_vol AND entry_reachable AND breach_mfe
    ) AS tradeable_misses
  FROM funnel
) agg;

\echo ===Q2_BOTH_BASES_BREAKDOWN===
WITH window_days AS (
  SELECT DISTINCT trade_date FROM mi_daily_closes
  ORDER BY trade_date DESC LIMIT 30
),
win AS (
  SELECT MIN(trade_date) AS floor_date FROM window_days
),
raw_rejects AS (
  SELECT detail::jsonb->>'ticker' AS ticker,
         (created_at AT TIME ZONE 'America/New_York')::date AS decline_date,
         (detail::jsonb->>'rt_gap')::numeric AS rt_gap,
         created_at
  FROM mi_audit_log
  WHERE event_type = 'ep_rt_sustain_reject'
    AND detail::jsonb->>'ticker' IS NOT NULL
    AND created_at AT TIME ZONE 'America/New_York' >= (SELECT floor_date FROM win)
),
rejects AS (
  SELECT DISTINCT ON (ticker, decline_date) ticker, decline_date, rt_gap
  FROM raw_rejects
  ORDER BY ticker, decline_date, created_at ASC
),
catches AS (
  SELECT DISTINCT detail::jsonb->>'ticker' AS ticker,
         (created_at AT TIME ZONE 'America/New_York')::date AS catch_date
  FROM mi_audit_log
  WHERE event_type = 'ep_rt_universe_catch'
    AND created_at AT TIME ZONE 'America/New_York' >= (SELECT floor_date FROM win)
),
net_declined AS (
  SELECT r.ticker, r.decline_date, r.rt_gap
  FROM rejects r
  WHERE NOT EXISTS (
    SELECT 1 FROM catches c
    WHERE c.ticker = r.ticker AND c.catch_date = r.decline_date
  )
),
bars AS (
  SELECT ticker, trade_date, high_price, close, volume,
         LAG(close) OVER (PARTITION BY ticker ORDER BY trade_date) AS prev_close
  FROM mi_daily_closes
  WHERE ticker IN (SELECT DISTINCT ticker FROM rejects)
    AND trade_date >= (SELECT floor_date FROM win) - INTERVAL '10 days'
),
scored AS (
  SELECT nd.ticker, nd.decline_date,
         b0.prev_close, b0.close AS close_d0, b0.high_price AS high_d0,
         b0.volume AS volume_d0,
         b0.prev_close * (1 + nd.rt_gap / 100.0) AS declined_level
  FROM net_declined nd
  JOIN bars b0 ON b0.ticker = nd.ticker AND b0.trade_date = nd.decline_date
  WHERE b0.prev_close IS NOT NULL AND b0.prev_close > 0
),
fwd AS (
  SELECT sc.ticker, sc.decline_date,
         MAX(fb.high_price) AS mfe_high,
         MAX(fb.close) FILTER (WHERE fb.rn = 6) AS close_d5,
         COUNT(*) AS n_fwd_bars
  FROM scored sc
  JOIN LATERAL (
    SELECT b.high_price, b.close, ROW_NUMBER() OVER (ORDER BY b.trade_date) AS rn
    FROM mi_daily_closes b
    WHERE b.ticker = sc.ticker AND b.trade_date >= sc.decline_date
    ORDER BY b.trade_date
    LIMIT 6
  ) fb ON TRUE
  GROUP BY sc.ticker, sc.decline_date
),
funnel AS (
  SELECT sc.ticker, sc.decline_date,
    (sc.close_d0 - sc.prev_close) / sc.prev_close >= 0.09 AS held_floor_d0,
    (sc.volume_d0 * sc.close_d0) >= 50000000 AS cleared_dollar_vol,
    sc.high_d0 >= sc.declined_level AS entry_reachable,
    (fw.mfe_high IS NOT NULL AND fw.mfe_high >= sc.declined_level * 1.20) AS breach_mfe,
    (fw.n_fwd_bars >= 6 AND fw.close_d5 >= sc.declined_level * 1.20) AS breach_settled
  FROM scored sc
  LEFT JOIN fwd fw ON fw.ticker = sc.ticker AND fw.decline_date = sc.decline_date
)
SELECT
  COUNT(*) AS scoreable_n,
  COUNT(*) FILTER (WHERE breach_mfe) AS raw_breach_mfe,
  COUNT(*) FILTER (WHERE breach_settled) AS raw_breach_settled,
  COUNT(*) FILTER (WHERE held_floor_d0 AND cleared_dollar_vol AND entry_reachable AND breach_mfe) AS tradeable_miss_mfe,
  COUNT(*) FILTER (WHERE held_floor_d0 AND cleared_dollar_vol AND entry_reachable AND breach_settled) AS tradeable_miss_settled,
  ROUND(100.0 * COUNT(*) FILTER (WHERE held_floor_d0 AND cleared_dollar_vol AND entry_reachable AND breach_mfe) / COUNT(*), 1) AS mfe_rate_pct,
  ROUND(100.0 * COUNT(*) FILTER (WHERE held_floor_d0 AND cleared_dollar_vol AND entry_reachable AND breach_settled) / COUNT(*), 1) AS settled_rate_pct
FROM funnel;

-- Q2b pins the window to the EXACT population the 2026-09-01 doc reported (floor 2026-07-22,
-- decline_date <= 2026-09-01) rather than "last 30 trading days as of whenever this runs" —
-- today's live window has already rolled 2 days forward, so Q2 alone will NOT reproduce
-- n=87/4/1 exactly even if the logic is right. Q2b is the apples-to-apples check.
-- If Q2b does NOT reproduce n=87, MFE=4 (4.6%), SETTLED=1 (1.1%): the FIRST suspect is
-- prev_close source — this predicate takes prev_close from mi_daily_closes (LAG(close)),
-- while the live gate's own rt_gap was computed against Polygon prevDay.c at catch time;
-- the two can differ on adjusted/unadjusted or late-revised closes. Q3 below gives the
-- per-name rows needed to trace any such mismatch.
\echo ===Q2b_PINNED_TO_09-01_POPULATION===
WITH win AS (
  SELECT DATE '2026-07-22' AS floor_date
),
raw_rejects AS (
  SELECT detail::jsonb->>'ticker' AS ticker,
         (created_at AT TIME ZONE 'America/New_York')::date AS decline_date,
         (detail::jsonb->>'rt_gap')::numeric AS rt_gap,
         created_at
  FROM mi_audit_log
  WHERE event_type = 'ep_rt_sustain_reject'
    AND detail::jsonb->>'ticker' IS NOT NULL
    AND created_at AT TIME ZONE 'America/New_York' >= (SELECT floor_date FROM win)
    AND created_at AT TIME ZONE 'America/New_York' < DATE '2026-09-02'
),
rejects AS (
  SELECT DISTINCT ON (ticker, decline_date) ticker, decline_date, rt_gap
  FROM raw_rejects
  ORDER BY ticker, decline_date, created_at ASC
),
catches AS (
  SELECT DISTINCT detail::jsonb->>'ticker' AS ticker,
         (created_at AT TIME ZONE 'America/New_York')::date AS catch_date
  FROM mi_audit_log
  WHERE event_type = 'ep_rt_universe_catch'
    AND created_at AT TIME ZONE 'America/New_York' >= (SELECT floor_date FROM win)
    AND created_at AT TIME ZONE 'America/New_York' < DATE '2026-09-02'
),
net_declined AS (
  SELECT r.ticker, r.decline_date, r.rt_gap
  FROM rejects r
  WHERE NOT EXISTS (
    SELECT 1 FROM catches c
    WHERE c.ticker = r.ticker AND c.catch_date = r.decline_date
  )
),
bars AS (
  SELECT ticker, trade_date, high_price, close, volume,
         LAG(close) OVER (PARTITION BY ticker ORDER BY trade_date) AS prev_close
  FROM mi_daily_closes
  WHERE ticker IN (SELECT DISTINCT ticker FROM rejects)
    AND trade_date >= (SELECT floor_date FROM win) - INTERVAL '10 days'
),
scored AS (
  SELECT nd.ticker, nd.decline_date,
         b0.prev_close, b0.close AS close_d0, b0.high_price AS high_d0,
         b0.volume AS volume_d0,
         b0.prev_close * (1 + nd.rt_gap / 100.0) AS declined_level
  FROM net_declined nd
  JOIN bars b0 ON b0.ticker = nd.ticker AND b0.trade_date = nd.decline_date
  WHERE b0.prev_close IS NOT NULL AND b0.prev_close > 0
),
fwd AS (
  SELECT sc.ticker, sc.decline_date,
         MAX(fb.high_price) AS mfe_high,
         MAX(fb.close) FILTER (WHERE fb.rn = 6) AS close_d5,
         COUNT(*) AS n_fwd_bars
  FROM scored sc
  JOIN LATERAL (
    SELECT b.high_price, b.close, ROW_NUMBER() OVER (ORDER BY b.trade_date) AS rn
    FROM mi_daily_closes b
    WHERE b.ticker = sc.ticker AND b.trade_date >= sc.decline_date
    ORDER BY b.trade_date
    LIMIT 6
  ) fb ON TRUE
  GROUP BY sc.ticker, sc.decline_date
),
funnel AS (
  SELECT
    (sc.close_d0 - sc.prev_close) / sc.prev_close >= 0.09 AS held_floor_d0,
    (sc.volume_d0 * sc.close_d0) >= 50000000 AS cleared_dollar_vol,
    sc.high_d0 >= sc.declined_level AS entry_reachable,
    (fw.mfe_high IS NOT NULL AND fw.mfe_high >= sc.declined_level * 1.20) AS breach_mfe,
    (fw.n_fwd_bars >= 6 AND fw.close_d5 >= sc.declined_level * 1.20) AS breach_settled
  FROM scored sc
  LEFT JOIN fwd fw ON fw.ticker = sc.ticker AND fw.decline_date = sc.decline_date
)
SELECT
  COUNT(*) AS scoreable_n_expect_87,
  COUNT(*) FILTER (WHERE held_floor_d0 AND cleared_dollar_vol AND entry_reachable AND breach_mfe) AS tradeable_miss_mfe_expect_4,
  COUNT(*) FILTER (WHERE held_floor_d0 AND cleared_dollar_vol AND entry_reachable AND breach_settled) AS tradeable_miss_settled_expect_1
FROM funnel;

\echo ===Q3_TRADEABLE_MISS_NAMES===
WITH window_days AS (
  SELECT DISTINCT trade_date FROM mi_daily_closes
  ORDER BY trade_date DESC LIMIT 30
),
win AS (
  SELECT MIN(trade_date) AS floor_date FROM window_days
),
raw_rejects AS (
  SELECT detail::jsonb->>'ticker' AS ticker,
         (created_at AT TIME ZONE 'America/New_York')::date AS decline_date,
         (detail::jsonb->>'rt_gap')::numeric AS rt_gap,
         created_at
  FROM mi_audit_log
  WHERE event_type = 'ep_rt_sustain_reject'
    AND detail::jsonb->>'ticker' IS NOT NULL
    AND created_at AT TIME ZONE 'America/New_York' >= (SELECT floor_date FROM win)
),
rejects AS (
  SELECT DISTINCT ON (ticker, decline_date) ticker, decline_date, rt_gap
  FROM raw_rejects
  ORDER BY ticker, decline_date, created_at ASC
),
catches AS (
  SELECT DISTINCT detail::jsonb->>'ticker' AS ticker,
         (created_at AT TIME ZONE 'America/New_York')::date AS catch_date
  FROM mi_audit_log
  WHERE event_type = 'ep_rt_universe_catch'
    AND created_at AT TIME ZONE 'America/New_York' >= (SELECT floor_date FROM win)
),
net_declined AS (
  SELECT r.ticker, r.decline_date, r.rt_gap
  FROM rejects r
  WHERE NOT EXISTS (
    SELECT 1 FROM catches c
    WHERE c.ticker = r.ticker AND c.catch_date = r.decline_date
  )
),
bars AS (
  SELECT ticker, trade_date, high_price, close, volume,
         LAG(close) OVER (PARTITION BY ticker ORDER BY trade_date) AS prev_close
  FROM mi_daily_closes
  WHERE ticker IN (SELECT DISTINCT ticker FROM rejects)
    AND trade_date >= (SELECT floor_date FROM win) - INTERVAL '10 days'
),
scored AS (
  SELECT nd.ticker, nd.decline_date,
         b0.prev_close, b0.close AS close_d0, b0.high_price AS high_d0,
         b0.volume AS volume_d0,
         b0.prev_close * (1 + nd.rt_gap / 100.0) AS declined_level
  FROM net_declined nd
  JOIN bars b0 ON b0.ticker = nd.ticker AND b0.trade_date = nd.decline_date
  WHERE b0.prev_close IS NOT NULL AND b0.prev_close > 0
),
fwd AS (
  SELECT sc.ticker, sc.decline_date,
         MAX(fb.high_price) AS mfe_high,
         MAX(fb.close) FILTER (WHERE fb.rn = 6) AS close_d5,
         COUNT(*) AS n_fwd_bars
  FROM scored sc
  JOIN LATERAL (
    SELECT b.high_price, b.close, ROW_NUMBER() OVER (ORDER BY b.trade_date) AS rn
    FROM mi_daily_closes b
    WHERE b.ticker = sc.ticker AND b.trade_date >= sc.decline_date
    ORDER BY b.trade_date
    LIMIT 6
  ) fb ON TRUE
  GROUP BY sc.ticker, sc.decline_date
)
SELECT sc.ticker, sc.decline_date, sc.prev_close, sc.declined_level, sc.close_d0, sc.high_d0,
       sc.volume_d0, fw.mfe_high, fw.close_d5, fw.n_fwd_bars
FROM scored sc
JOIN fwd fw ON fw.ticker = sc.ticker AND fw.decline_date = sc.decline_date
WHERE (sc.close_d0 - sc.prev_close) / sc.prev_close >= 0.09
  AND (sc.volume_d0 * sc.close_d0) >= 50000000
  AND sc.high_d0 >= sc.declined_level
  AND fw.mfe_high >= sc.declined_level * 1.20
ORDER BY sc.decline_date;

\echo ===Q4_NOW===
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS now_et;
