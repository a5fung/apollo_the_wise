-- #719 — read-only export of the MARKET BREADTH snapshot (export_breadth_snapshot) for
-- portfolio-app2's daily "Market Breadth" page: new 52-week highs vs lows, advances vs
-- declines, the Weinstein stage 1-4 split, and a theme tracker (Today / 1W / 1M / YTD).
--
-- SSoT: docs/architecture/market_breadth_snapshot.md — every rule below, the JSON contract
-- field by field, and what this file does NOT claim. Change a rule here and there in the
-- same commit; the `definitions` object at the bottom is what the page prints, so it must
-- say exactly what the SQL does.
--
-- Emits ONE JSON object on stdout. Run read-only (the nightly job does this, guarded, in
-- scripts/auto_export_snapshots.sh — a failure here never blocks the other snapshots):
--   docker exec -i apollo-postgres psql -U apollo -d apollo -A -t -X -v ON_ERROR_STOP=1 \
--     -f - < export_breadth_snapshot.sql > apollo_breadth_snapshot.json
--
-- READ-ONLY: one SELECT. Display only — no money path, no grade, no alert input.
--
-- ⚠ DATES ARE TAKEN FROM THE DATA, NEVER FROM THE CLOCK. The cron also runs on Saturday and
-- Sunday, so the calendar date is not a trading day. A "session" is a trade_date carrying at
-- least 3,000 rows that join mi_security_types as CS/ADRC; as_of is the newest one. The
-- 3,000 bar guards a partial ingest (an on-demand fetch writes a handful of rows stamped with
-- the calendar date — the same stray-row failure the theme export's usable_score_date fixes).
-- Every window below is counted in those sessions by index (0 = as_of, 1 = the session
-- before it, ...), never by calendar arithmetic.
--
-- PERFORMANCE: mi_daily_closes is ~13.6M rows. Only two range reads touch it — the session
-- calendar (the last 500 calendar days, ~344 sessions) and the price window (the newest 273
-- sessions, restricted to the universe plus theme members) — both bounded on trade_date, the
-- leading column of its primary key. Every per-ticker number is one FILTERed aggregate over
-- that window: no per-row correlated subquery, no 252-row window frame.
WITH latest AS (
    SELECT max(trade_date) AS d FROM mi_daily_closes
),
cal AS (
    SELECT c.trade_date
      FROM mi_daily_closes c
      JOIN mi_security_types t ON t.ticker = c.ticker
     WHERE c.trade_date >= (SELECT d FROM latest) - 500
       AND t.security_type IN ('CS', 'ADRC')
     GROUP BY c.trade_date
    HAVING count(*) >= 3000
),
sess AS (
    SELECT trade_date, (row_number() OVER (ORDER BY trade_date DESC) - 1)::int AS idx
      FROM cal
),
-- as_of + 272 prior sessions: covers the 252-session high/low lookback, the 210-session
-- stage need, and the prior calendar year's last session (a year holds at most ~253).
win AS (
    SELECT trade_date, idx FROM sess WHERE idx <= 272
),
k AS (
    SELECT (SELECT trade_date FROM sess WHERE idx = 0) AS as_of,
           (SELECT trade_date FROM sess WHERE idx = 1) AS prev_session,
           (SELECT min(trade_date) FROM win)           AS win_start,
           (SELECT max(trade_date) FROM sess
             WHERE trade_date < make_date(extract(year FROM (SELECT trade_date FROM sess WHERE idx = 0))::int, 1, 1)
           ) AS prior_year_end,
           (SELECT min(idx) FROM sess
             WHERE trade_date < make_date(extract(year FROM (SELECT trade_date FROM sess WHERE idx = 0))::int, 1, 1)
           ) AS pye_idx
),
universe AS (
    SELECT d.ticker
      FROM mi_daily_closes d
      JOIN mi_security_types t ON t.ticker = d.ticker
     WHERE d.trade_date = (SELECT as_of FROM k)
       AND t.security_type IN ('CS', 'ADRC')
       AND d.close >= 1.00
),
-- Active themes exactly as db.get_active_themes defines them, anchored on as_of instead of
-- the clock: the LATEST row per name inside the 7-day window FIRST, then drop names whose
-- latest row is Retired. Filtering Retired inside the DISTINCT ON would resurrect a freshly
-- retired theme from an older row (the 2026-06-09 #214 bug that function's docstring records).
-- No upper bound on theme_date: a weekend run may hold a theme row dated after as_of, and the
-- membership is TODAY's by design (see theme_membership in the output).
theme_latest AS (
    SELECT DISTINCT ON (name) id, name, stage, tickers, theme_date
      FROM mi_themes
     WHERE theme_date >= (SELECT as_of FROM k) - 7
     ORDER BY name, theme_date DESC, id DESC
),
-- ONE ordering feeds BOTH the themes array and every stock's theme indexes — two orderings is
-- how the stocks map would silently point at the wrong theme.
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
-- Every per-ticker number in one pass. A bar = a row with close > 0 on a session; a bar
-- with a missing or zero high/low never enters a high/low test (missing OHLC must never
-- count as a new low).
px AS (
    SELECT d.ticker,
           max(d.close) FILTER (WHERE w.idx = 0)  AS c0,
           max(d.close) FILTER (WHERE w.idx = 1)  AS c1,
           max(d.close) FILTER (WHERE w.idx = 5)  AS c5,
           max(d.close) FILTER (WHERE w.idx = 21) AS c21,
           (array_agg(d.close ORDER BY w.idx) FILTER (WHERE w.idx >= k.pye_idx))[1] AS c_ytd,
           max(d.high_price) FILTER (WHERE w.idx = 0 AND d.high_price > 0) AS h0,
           max(d.low_price)  FILTER (WHERE w.idx = 0 AND d.low_price > 0)  AS l0,
           max(d.high_price) FILTER (WHERE w.idx BETWEEN 1 AND 252 AND d.high_price > 0) AS hmax_252,
           min(d.low_price)  FILTER (WHERE w.idx BETWEEN 1 AND 252 AND d.low_price > 0)  AS lmin_252,
           count(*) FILTER (WHERE w.idx BETWEEN 1 AND 252
                              AND d.high_price > 0 AND d.low_price > 0)                 AS n_hl_252,
           avg(d.close) FILTER (WHERE w.idx BETWEEN 0 AND 149)  AS sma_now,
           avg(d.close) FILTER (WHERE w.idx BETWEEN 20 AND 169) AS sma_20,
           avg(d.close) FILTER (WHERE w.idx BETWEEN 60 AND 209) AS sma_60,
           count(*) FILTER (WHERE w.idx BETWEEN 0 AND 209)      AS n_210
      FROM mi_daily_closes d
      JOIN win w ON w.trade_date = d.trade_date
     CROSS JOIN k
     WHERE d.trade_date BETWEEN k.win_start AND k.as_of
       AND d.close > 0
       AND d.ticker IN (SELECT ticker FROM interest)
     GROUP BY d.ticker
),
-- Weinstein stage on the 30-week (150-session) SMA of close. Needs a bar on every one of the
-- 210 sessions ending as_of (150 + the 60-session look-back), else unstaged.
st AS (
    SELECT p.*,
           (p.h0 IS NOT NULL AND p.l0 IS NOT NULL AND p.n_hl_252 >= 245) AS hl_eligible,
           CASE
             WHEN p.c0 IS NULL OR p.n_210 < 210 OR NULLIF(p.sma_20, 0) IS NULL THEN NULL
             WHEN p.sma_now / p.sma_20 - 1 > 0.01
               THEN CASE WHEN p.c0 >= p.sma_now THEN 2 ELSE 3 END
             WHEN p.sma_now / p.sma_20 - 1 < -0.01
               THEN CASE WHEN p.c0 <= p.sma_now THEN 4 ELSE 1 END
             WHEN p.sma_now > p.sma_60 THEN 3
             ELSE 1
           END AS stage
      FROM px p
),
uni AS (
    SELECT u.ticker, s.c0, s.c1, s.h0, s.l0, s.hmax_252, s.lmin_252,
           COALESCE(s.hl_eligible, false) AS hl_eligible, s.stage
      FROM universe u
      LEFT JOIN st s ON s.ticker = u.ticker
),
-- Equal-weighted member returns (strength_map._basket semantics): a member without the bar at
-- either end of a window drops out of that window, an empty basket is null, and the count of
-- members that had the data travels with every number.
theme_ret AS (
    SELECT m.idx,
           count(*) AS n_members,
           array_agg(m.ticker ORDER BY m.ticker) AS member_list,
           round(avg((p.c0 / p.c1    - 1) * 100)::numeric, 2) AS ret_1d,
           count(p.c0 / p.c1)                                 AS n_1d,
           round(avg((p.c0 / p.c5    - 1) * 100)::numeric, 2) AS ret_5d,
           count(p.c0 / p.c5)                                 AS n_5d,
           round(avg((p.c0 / p.c21   - 1) * 100)::numeric, 2) AS ret_21d,
           count(p.c0 / p.c21)                                AS n_21d,
           round(avg((p.c0 / p.c_ytd - 1) * 100)::numeric, 2) AS ret_ytd,
           count(p.c0 / p.c_ytd)                              AS n_ytd
      FROM members m
      LEFT JOIN px p ON p.ticker = m.ticker
     GROUP BY m.idx
),
member_of AS (
    SELECT ticker, array_agg(idx ORDER BY idx) AS idxs
      FROM members
     GROUP BY ticker
),
-- The theme export's rule, verbatim (export_theme_snapshot.sql): the newest score_date that
-- looks like a full RS run, never max(score_date) — a single on-demand lookup writes a
-- one-row day that max() would pick, emptying every rank.
usable_score_date AS (
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
),
ranks AS (
    SELECT ticker, rs_rank
      FROM mi_stock_scores
     WHERE score_date = (SELECT score_date FROM usable_score_date)
       AND ticker IN (SELECT ticker FROM interest)
)
SELECT json_build_object(
    'version', 1,
    'generated_at', to_char(now() AT TIME ZONE 'America/New_York',
                            'YYYY-MM-DD"T"HH24:MI:SS') || ' ET',
    'as_of', (SELECT as_of FROM k),
    'prev_session', (SELECT prev_session FROM k),
    'prior_year_end', (SELECT prior_year_end FROM k),
    'score_date', (SELECT score_date FROM usable_score_date),
    'theme_membership', 'today',
    'universe', json_build_object('n', (SELECT count(*) FROM uni)),
    'highs_lows', (
        SELECT json_build_object(
            'eligible_n', count(*) FILTER (WHERE hl_eligible),
            'new_highs',  count(*) FILTER (WHERE hl_eligible AND h0 >= hmax_252),
            'new_lows',   count(*) FILTER (WHERE hl_eligible AND l0 <= lmin_252))
          FROM uni),
    'adv_dec', (
        SELECT json_build_object(
            'advances',  count(*) FILTER (WHERE c1 IS NOT NULL AND c0 > c1),
            'declines',  count(*) FILTER (WHERE c1 IS NOT NULL AND c0 < c1),
            'unchanged', count(*) FILTER (WHERE c1 IS NOT NULL AND c0 = c1),
            'no_prior',  count(*) FILTER (WHERE c1 IS NULL))
          FROM uni),
    'stages', (
        SELECT json_build_object(
            '1', count(*) FILTER (WHERE stage = 1),
            '2', count(*) FILTER (WHERE stage = 2),
            '3', count(*) FILTER (WHERE stage = 3),
            '4', count(*) FILTER (WHERE stage = 4),
            'unstaged', count(*) FILTER (WHERE stage IS NULL))
          FROM uni),
    'themes', (
        SELECT COALESCE(json_agg(json_build_object(
                   'idx', ti.idx,
                   'name', ti.name,
                   'stage', ti.stage,
                   'e_code', ti.e_code,
                   'theme_date', ti.theme_date,
                   'n_members', COALESCE(tr.n_members, 0),
                   'members', COALESCE(to_json(tr.member_list), '[]'::json),
                   'ret_1d', tr.ret_1d,   'n_1d', COALESCE(tr.n_1d, 0),
                   'ret_5d', tr.ret_5d,   'n_5d', COALESCE(tr.n_5d, 0),
                   'ret_21d', tr.ret_21d, 'n_21d', COALESCE(tr.n_21d, 0),
                   'ret_ytd', tr.ret_ytd, 'n_ytd', COALESCE(tr.n_ytd, 0)
               ) ORDER BY ti.idx), '[]'::json)
          FROM themes_idx ti
          LEFT JOIN theme_ret tr ON tr.idx = ti.idx),
    'stocks', (
        SELECT COALESCE(json_object_agg(i.ticker, json_build_array(
                   s.stage, r.rs_rank, COALESCE(to_json(mo.idxs), '[]'::json)
               ) ORDER BY i.ticker), '{}'::json)
          FROM interest i
          LEFT JOIN st s         ON s.ticker = i.ticker
          LEFT JOIN ranks r      ON r.ticker = i.ticker
          LEFT JOIN member_of mo ON mo.ticker = i.ticker),
    'definitions', json_build_object(
        'session',
            'A trading session is a date on which at least 3,000 common stocks or ADRs (security type CS or ADRC) have a daily bar. Dates come from the data, never the clock, so a weekend run still reads the last real session and a partial ingest is skipped.',
        'as_of',
            'The newest session. Every number in this file is as of its close.',
        'universe',
            'Common stocks and ADRs (CS, ADRC) that closed at 1.00 dollar or more on the as_of session.',
        'new_highs_lows',
            'A new high: the as_of high is at or above the highest high of the 252 sessions before as_of (as_of itself excluded). A new low: the as_of low is at or below the lowest low of those 252 sessions. Only universe stocks with a usable bar (high and low above zero) on at least 245 of those 252 sessions, and on as_of, are eligible (eligible_n). A missing or zero high or low never counts.',
        'advances_declines',
            'A universe stock advances if its as_of close is above its close on the previous session, declines if below, unchanged if equal. A stock with no bar on the previous session is counted in no_prior, not in the three.',
        'stage',
            'Weinstein stage on the 30-week line: the average close of the 150 sessions ending as_of. Its slope compares it with the same average ending 20 sessions earlier: rising if more than 1% higher, falling if more than 1% lower, flat otherwise. Rising: stage 2 if the as_of close is at or above the line, else stage 3. Falling: stage 4 if the close is at or below the line, else stage 1. Flat: stage 3 if the line is above where it stood 60 sessions earlier (it came from an advance), else stage 1. A stock without a bar on every one of the 210 sessions ending as_of is unstaged. Stages 1-4 plus unstaged add up to the universe.',
        'themes',
            'The active themes: each name''s newest theme row dated no earlier than 7 days before as_of (a row dated after as_of counts), dropped if that newest row is Retired.',
        'theme_returns',
            'Equal-weighted average of member returns in percent, from the close 1, 5 or 21 sessions before as_of (Today, 1W, 1M) to the as_of close; YTD is from the last close on or before the prior calendar year''s last session. A member without both closes drops out of that window; n_ counts the members that had them; a window no member could fill is null.',
        'theme_membership',
            'Membership is TODAY''s list, applied to every window. Over 1M and YTD this flatters a theme: names often joined it because they had already run.',
        'stocks',
            'One entry per universe stock and per active-theme member: [stage 1-4 or null, RS rank or null, indexes into themes]. The RS rank is from the newest full nightly RS run (score_date) and ranks only the roughly 2,400 names that run keeps.',
        'not_claimed',
            'Display only. Nothing here feeds a trade, a grade, an alert or any sizing.'
    )
)
-- No session at all (an empty or broken calendar) => ZERO rows, so psql prints nothing and the
-- nightly guard's 200-byte floor rejects it. Without this the definitions text alone would carry
-- an all-null file past that floor and publish it.
  FROM k
 WHERE k.as_of IS NOT NULL;
