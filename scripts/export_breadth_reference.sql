-- #723 — read-only export of the LIVE-BREADTH REFERENCE (export_breadth_reference): what the
-- intraday job (agents/market_intelligence/breadth_live.py) compares today's Alpaca snapshots
-- against. One row per ticker of interest: the last close, the 252-session high and low ENDING at
-- that close, the high/low eligibility, whether the name is in the universe, and its theme
-- indexes; plus the active themes and their ecosystem groups, so the live job is pure arithmetic.
--
-- SSoT: docs/architecture/market_breadth_snapshot.md §"Live breadth (#723)". The session, universe,
-- NaN and usable-bar rules are the nightly snapshot's (export_breadth_snapshot.sql), copied — the
-- two files must keep saying the same thing. tests/test_723_breadth_live.py pins the copies.
--
-- Emits ONE JSON object on stdout. Run read-only by scripts/auto_export_snapshots.sh as a second
-- GUARDED step (a failure here never blocks the other snapshots):
--   docker exec -i apollo-postgres psql -U apollo -d apollo -A -t -X -v ON_ERROR_STOP=1 \
--     -f - < export_breadth_reference.sql > apollo_breadth_reference.json
--
-- READ-ONLY: one SELECT. Display only — no money path, no grade, no alert input.
--
-- ⚠ THE WINDOW DIFFERS FROM THE NIGHTLY'S ON PURPOSE. The nightly tests the as_of bar against the
-- 252 sessions BEFORE it (idx 1..252). The live job tests TODAY's bar (not yet in the table)
-- against the 252 sessions ending at the last close — idx 0..251 here — so as_of is INSIDE this
-- window. hl_eligible here = usable bars on >= 245 of those 252; the live job adds the nightly's
-- other half (a usable bar TODAY) from the snapshot itself.
--
-- ⚠ DATES ARE TAKEN FROM THE DATA, NEVER FROM THE CLOCK (the nightly's rule, same CTEs).
WITH latest AS (
    SELECT max(trade_date) AS d FROM mi_daily_closes
     WHERE trade_date <= (now() AT TIME ZONE 'America/New_York')::date
),
cal AS (
    SELECT c.trade_date
      FROM mi_daily_closes c
      JOIN mi_security_types t ON t.ticker = c.ticker
     WHERE c.trade_date >= (SELECT d FROM latest) - 500
       AND c.trade_date <= (SELECT d FROM latest)
       AND t.security_type IN ('CS', 'ADRC')
     GROUP BY c.trade_date
    HAVING count(*) >= 3000
),
sess AS (
    SELECT trade_date, (row_number() OVER (ORDER BY trade_date DESC) - 1)::int AS idx
      FROM cal
),
-- the 252 sessions ending at as_of: idx 0..251
win AS (
    SELECT trade_date, idx FROM sess WHERE idx <= 251
),
k AS (
    SELECT (SELECT trade_date FROM sess WHERE idx = 0) AS as_of,
           (SELECT min(trade_date) FROM win)           AS win_start
),
universe AS (
    SELECT d.ticker
      FROM mi_daily_closes d
      JOIN mi_security_types t ON t.ticker = d.ticker
     WHERE d.trade_date = (SELECT as_of FROM k)
       AND t.security_type IN ('CS', 'ADRC')
       AND d.close >= 1.00 AND d.close <> 'NaN'
),
theme_latest AS (
    SELECT DISTINCT ON (name) id, name, stage, tickers, theme_date
      FROM mi_themes
     WHERE theme_date >= (SELECT as_of FROM k) - 7
     ORDER BY name, theme_date DESC, id DESC
),
themes_idx AS (
    SELECT (row_number() OVER (ORDER BY l.name) - 1)::int AS idx,
           l.name, l.stage, l.theme_date, l.tickers, e.e_code
      FROM theme_latest l
      LEFT JOIN mi_theme_ecosystems e ON e.theme_name = l.name
     WHERE l.stage <> 'Retired'
),
members AS (
    SELECT DISTINCT ti.idx, m.ticker
      FROM themes_idx ti
     CROSS JOIN LATERAL unnest(ti.tickers) AS m(ticker)
     WHERE m.ticker IS NOT NULL AND m.ticker <> ''
),
interest AS (
    SELECT ticker FROM universe
    UNION
    SELECT ticker FROM members
),
-- One pass over the window. A bar = a row with close > 0 on a session; a high/low enters a test
-- only when both are > 0 and not NaN (the nightly's usable-bar rule).
px AS (
    SELECT d.ticker,
           max(d.close) FILTER (WHERE w.idx = 0) AS c0,
           max(d.high_price) FILTER (WHERE w.idx BETWEEN 0 AND 251 AND d.high_price > 0 AND d.high_price <> 'NaN') AS hmax_252,
           min(d.low_price)  FILTER (WHERE w.idx BETWEEN 0 AND 251 AND d.low_price > 0 AND d.low_price <> 'NaN')  AS lmin_252,
           count(*) FILTER (WHERE w.idx BETWEEN 0 AND 251
                              AND d.high_price > 0 AND d.low_price > 0
                              AND d.high_price <> 'NaN' AND d.low_price <> 'NaN')       AS n_hl_252
      FROM mi_daily_closes d
      JOIN win w ON w.trade_date = d.trade_date
     CROSS JOIN k
     WHERE d.trade_date BETWEEN k.win_start AND k.as_of
       AND d.close > 0 AND d.close <> 'NaN'
       AND d.ticker IN (SELECT ticker FROM interest)
     GROUP BY d.ticker
),
member_of AS (
    SELECT ticker, array_agg(idx ORDER BY idx) AS idxs
      FROM members
     GROUP BY ticker
),
-- Copied VERBATIM from export_breadth_snapshot.sql (itself a copy of theme_ecosystems.yaml, test-guarded).
eco_names AS (
    SELECT v.e_code, v.name
      FROM (VALUES
        ('E-CYBR', 'Cybersecurity'),
        ('E-AISEMI', 'AI silicon & semiconductors'),
        ('E-AIINFRA', 'AI cloud & datacenter'),
        ('E-SAAS', 'Enterprise software'),
        ('E-BIO', 'Biotech & therapeutics'),
        ('E-MEDTECH', 'Devices & diagnostics'),
        ('E-INS', 'Insurance'),
        ('E-BANKFIN', 'Banks / fintech / brokers'),
        ('E-REIT', 'Real estate / REITs'),
        ('E-ENER', 'Energy'),
        ('E-METAL', 'Metals & mining'),
        ('E-DEF', 'Defense & space'),
        ('E-TRANS', 'Transport & logistics'),
        ('E-CONS', 'Consumer / retail / dining'),
        ('E-INDL', 'Industrials / power'),
        ('E-CRYPTO', 'Crypto infrastructure'),
        ('E-COMM', 'Communications & media'),
        ('E-HLTH', 'Healthcare services'),
        ('E-QUANTUM', 'Quantum computing'),
        ('E-ROBOT', 'Robotics & automation'),
        ('E-UNASSIGNED', 'Unassigned')
      ) AS v(e_code, name)
),
eco_themes AS (
    SELECT COALESCE(ti.e_code, 'E-UNASSIGNED') AS code,
           array_agg(ti.idx ORDER BY ti.idx) AS theme_idx
      FROM themes_idx ti
     GROUP BY COALESCE(ti.e_code, 'E-UNASSIGNED')
)
SELECT json_build_object(
    'version', 1,
    'generated_at', to_char(now() AT TIME ZONE 'America/New_York',
                            'YYYY-MM-DD"T"HH24:MI:SS') || ' ET',
    'as_of', (SELECT as_of FROM k),
    'universe', json_build_object('n', (SELECT count(*) FROM universe)),
    'themes', (
        SELECT COALESCE(json_agg(json_build_object(
                   'idx', ti.idx,
                   'name', ti.name,
                   'e_code', ti.e_code
               ) ORDER BY ti.idx), '[]'::json)
          FROM themes_idx ti),
    'ecosystems', (
        SELECT COALESCE(json_agg(json_build_object(
                   'code', et.code,
                   'name', CASE WHEN et.code = 'E-UNASSIGNED' THEN 'Other' ELSE COALESCE(en.name, et.code) END,
                   'theme_idx', to_json(et.theme_idx)
               ) ORDER BY et.code), '[]'::json)
          FROM eco_themes et
          LEFT JOIN eco_names en ON en.e_code = et.code),
    -- [prev_close, hi252, lo252, hl_eligible, in_universe, theme indexes]
    'stocks', (
        SELECT COALESCE(json_object_agg(i.ticker, json_build_array(
                   p.c0, p.hmax_252, p.lmin_252,
                   COALESCE(p.n_hl_252 >= 245, false),
                   (u.ticker IS NOT NULL),
                   COALESCE(to_json(mo.idxs), '[]'::json)
               ) ORDER BY i.ticker), '{}'::json)
          FROM interest i
          LEFT JOIN px p         ON p.ticker = i.ticker
          LEFT JOIN universe u   ON u.ticker = i.ticker
          LEFT JOIN member_of mo ON mo.ticker = i.ticker),
    'definitions', json_build_object(
        'as_of',
            'The newest session (the nightly rule: a date with at least 3,000 common-stock or ADR bars, taken from the data, never the clock). prev_close is the close of that session.',
        'hi252_lo252',
            'The highest high and lowest low over the 252 sessions ENDING at as_of (as_of included) — what today''s intraday high and low are tested against. Only bars with a high and a low above zero count.',
        'hl_eligible',
            'True when the name has a usable bar on at least 245 of those 252 sessions. The live job also requires a usable bar today, as the nightly requires one on as_of.',
        'in_universe',
            'Common stocks and ADRs that closed at 1.00 dollar or more on as_of. Advances, declines and new highs/lows are counted over these; a theme member outside it is listed only for the theme returns.',
        'stocks',
            'One entry per universe stock and per active-theme member: [prev_close, hi252, lo252, hl_eligible, in_universe, indexes into themes].',
        'not_claimed',
            'Display only. Nothing here feeds a trade, a grade, an alert or any sizing.'
    )
)
-- No session => ZERO rows, so psql prints nothing and the guard's size floor rejects it.
  FROM k
 WHERE k.as_of IS NOT NULL;
