-- RS LEADERS — read-only export of the strongest stocks by price return over 1 week / 1 month /
-- 3 months / 6 months (5 / 21 / 63 / 126 sessions) for portfolio-app2's "RS Leaders" page.
-- Same shape as the market-breadth export: ONE SELECT, one JSON object on stdout, run guarded by
-- scripts/auto_export_snapshots.sh (a failure here never blocks the other snapshots):
--   docker exec -i apollo-postgres psql -U apollo -d apollo -A -t -X -v ON_ERROR_STOP=1 \
--     -f - < export_rs_leaders_snapshot.sql > apollo_rs_leaders_snapshot.json
-- SSoT: docs/architecture/rs_leaders_snapshot.md (every rule below, the JSON contract).
-- READ-ONLY, display only: no money path, no grade, no alert input.
--
-- Session / as_of / universe rules are the breadth export's, verbatim: dates come from the DATA
-- (a session = a trade_date with >= 3,000 CS/ADRC rows), never the clock; the universe is CS/ADRC
-- closing >= 1.00 on as_of; a NaN price never counts (Postgres orders NaN above every number).
-- Windows count SESSIONS by index (0 = as_of), never calendar days.
--
-- LIQUIDITY FLOOR: 20-session MEDIAN dollar volume (close x volume) >= 5,000,000, on at least 15
-- of the 20 sessions. Why $5M: a leaderboard without a floor fills with thin names that tripled on
-- a few thousand shares a day, which nobody can trade at size; the median (not the mean) so one
-- huge-volume day cannot lift an otherwise dead stock over the bar. Change it here AND in the SSoT.
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
-- as_of + 251 prior sessions: the 126-session return base and the 252-session high.
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
-- Active themes: the same rule the theme export and the breadth export use (newest row per name in
-- the 7-day window FIRST, then drop Retired; never filter Retired inside the DISTINCT ON).
theme_latest AS (
    SELECT DISTINCT ON (name) id, name, stage, tickers, theme_date
      FROM mi_themes
     WHERE theme_date >= (SELECT as_of FROM k) - 7
     ORDER BY name, theme_date DESC, id DESC
),
members AS (
    SELECT DISTINCT l.name AS theme, m.ticker
      FROM theme_latest l
     CROSS JOIN LATERAL unnest(l.tickers) AS m(ticker)
     WHERE l.stage <> 'Retired' AND m.ticker IS NOT NULL AND m.ticker <> ''
),
member_of AS (
    SELECT ticker, array_agg(theme ORDER BY theme) AS themes
      FROM members
     GROUP BY ticker
),
-- One pass over the price window for the universe only. ADR20 = 100 x (mean of high/low over the
-- last 20 sessions - 1); a bar with a missing, zero or NaN high/low is left out of that mean.
px AS (
    SELECT d.ticker,
           max(d.close) FILTER (WHERE w.idx = 0)   AS c0,
           max(d.close) FILTER (WHERE w.idx = 5)   AS c5,
           max(d.close) FILTER (WHERE w.idx = 21)  AS c21,
           max(d.close) FILTER (WHERE w.idx = 63)  AS c63,
           max(d.close) FILTER (WHERE w.idx = 126) AS c126,
           max(d.high_price) FILTER (WHERE d.high_price > 0 AND d.high_price <> 'NaN') AS hi_252,
           count(*) FILTER (WHERE d.high_price > 0 AND d.high_price <> 'NaN')          AS n_hi,
           100 * (avg(d.high_price / d.low_price) FILTER (
                    WHERE w.idx <= 19 AND d.high_price > 0 AND d.low_price > 0
                      AND d.high_price <> 'NaN' AND d.low_price <> 'NaN') - 1) AS adr20,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY d.close * d.volume)
               FILTER (WHERE w.idx <= 19 AND d.volume > 0)                      AS dv20,
           count(*) FILTER (WHERE w.idx <= 19 AND d.volume > 0)                 AS n_dv
      FROM mi_daily_closes d
      JOIN win w ON w.trade_date = d.trade_date
      CROSS JOIN k
     WHERE d.trade_date BETWEEN k.win_start AND k.as_of
       AND d.close > 0 AND d.close <> 'NaN'
       AND d.ticker IN (SELECT ticker FROM universe)
     GROUP BY d.ticker
),
-- DEAL-PINNED: a stock whose price is held by an announced buyout leaves the board (operator
-- 2026-11-16, BRZE: "looks like a buy out? Do we filter m&a?"). The SAME free two-leg rule as
-- db.get_deal_pinned_tickers, which every RS pool already applies (keep the two in step):
--   1. the pin: each of the last 4 sessions trades inside 2% of its close;
--   2. the announcement: within 180 calendar days, one day up >= 15% on >= 10x its own trailing
--      21-day average volume.
-- Both legs, because a low range alone is just a sleepy stock.
pin_recent AS (
    SELECT d.ticker, d.trade_date, d.close, d.high_price, d.low_price, d.volume,
           row_number() OVER (PARTITION BY d.ticker ORDER BY d.trade_date DESC) AS rn
      FROM mi_daily_closes d
     CROSS JOIN k
     WHERE d.trade_date <= k.as_of AND d.trade_date > k.as_of - 180
       AND d.ticker IN (SELECT ticker FROM universe)
),
pin_leg AS (
    SELECT ticker FROM pin_recent WHERE rn <= 4
     GROUP BY ticker
    HAVING count(*) = 4
       AND bool_and((high_price - low_price) / NULLIF(close, 0) < 0.02)
),
pin_chg AS (
    SELECT ticker,
           100.0 * (close / NULLIF(lag(close) OVER (PARTITION BY ticker ORDER BY trade_date), 0) - 1) AS pct,
           volume::numeric / NULLIF(avg(volume) OVER (PARTITION BY ticker ORDER BY trade_date
                                     ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING), 0) AS rvol
      FROM pin_recent
     WHERE ticker IN (SELECT ticker FROM pin_leg)
),
deal_pinned AS (
    SELECT DISTINCT ticker FROM pin_chg WHERE pct >= 15 AND rvol >= 10
),
liquid AS (
    SELECT p.*
      FROM px p
     WHERE p.c0 IS NOT NULL AND p.n_dv >= 15 AND p.dv20 >= 5000000
       AND p.ticker NOT IN (SELECT ticker FROM deal_pinned)
),
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
-- Sector: the nightly RS run's sector (top ~300 names only) first, else the persistent override cache.
sectors AS (
    SELECT l.ticker, COALESCE(NULLIF(s.sector, ''), NULLIF(o.sector, '')) AS sector
      FROM liquid l
      LEFT JOIN mi_stock_scores s ON s.ticker = l.ticker
                                 AND s.score_date = (SELECT score_date FROM usable_score_date)
      LEFT JOIN mi_ticker_overrides o ON o.ticker = l.ticker
),
-- One row per (period, stock) with a return, ranked within the period.
per AS (
    SELECT v.period, v.sessions, l.ticker,
           (l.c0 / v.base - 1) * 100 AS ret,
           row_number() OVER (PARTITION BY v.period
                              ORDER BY (l.c0 / v.base) DESC, l.ticker) AS rnk,
           count(*) OVER (PARTITION BY v.period) AS n_ranked
      FROM liquid l
     CROSS JOIN LATERAL (VALUES ('1w', 5, l.c5), ('1m', 21, l.c21),
                                ('3m', 63, l.c63), ('6m', 126, l.c126)) AS v(period, sessions, base)
     WHERE v.base IS NOT NULL
),
top AS (
    SELECT * FROM per WHERE rnk <= 50
),
rows_json AS (
    SELECT t.period,
           json_agg(json_build_object(
               'rank', t.rnk,
               'ticker', t.ticker,
               'name', COALESCE(NULLIF(st.name, ''), NULLIF(o.company_name, '')),
               'close', round(l.c0::numeric, 2),
               'ret', round(t.ret::numeric, 1),
               'pct_from_high', round(((l.c0 / l.hi_252 - 1) * 100)::numeric, 1),
               'adr20', round(l.adr20::numeric, 1),
               'dollar_volume', round(l.dv20::numeric, 0),
               'sector', sc.sector,
               'themes', COALESCE(to_json(mo.themes), '[]'::json)
           ) ORDER BY t.rnk) AS rows
      FROM top t
      JOIN liquid l ON l.ticker = t.ticker
      LEFT JOIN sectors sc ON sc.ticker = t.ticker
      LEFT JOIN mi_security_types st ON st.ticker = t.ticker
      LEFT JOIN mi_ticker_overrides o ON o.ticker = t.ticker
      LEFT JOIN member_of mo ON mo.ticker = t.ticker
     GROUP BY t.period
)
SELECT json_build_object(
    'version', 1,
    'generated_at', to_char(now() AT TIME ZONE 'America/New_York',
                            'YYYY-MM-DD"T"HH24:MI:SS') || ' ET',
    'as_of', (SELECT as_of FROM k),
    'universe', json_build_object('n', (SELECT count(*) FROM universe),
                                  'n_liquid', (SELECT count(*) FROM liquid),
                                  'min_dollar_volume', 5000000,
                                  'n_deal_pinned', (SELECT count(*) FROM deal_pinned)),
    'periods', json_build_object(
        '1w', json_build_object('sessions', 5,   'n_ranked', (SELECT max(n_ranked) FROM per WHERE period = '1w'),
                                'rows', COALESCE((SELECT rows FROM rows_json WHERE period = '1w'), '[]'::json)),
        '1m', json_build_object('sessions', 21,  'n_ranked', (SELECT max(n_ranked) FROM per WHERE period = '1m'),
                                'rows', COALESCE((SELECT rows FROM rows_json WHERE period = '1m'), '[]'::json)),
        '3m', json_build_object('sessions', 63,  'n_ranked', (SELECT max(n_ranked) FROM per WHERE period = '3m'),
                                'rows', COALESCE((SELECT rows FROM rows_json WHERE period = '3m'), '[]'::json)),
        '6m', json_build_object('sessions', 126, 'n_ranked', (SELECT max(n_ranked) FROM per WHERE period = '6m'),
                                'rows', COALESCE((SELECT rows FROM rows_json WHERE period = '6m'), '[]'::json))),
    'definitions', json_build_object(
        'session',
            'A trading session is a date on which at least 3,000 common stocks or ADRs have a daily bar. Dates come from the data, never the clock.',
        'universe',
            'Common stocks and ADRs that closed at 1.00 dollar or more on the newest session, with a 20-session median dollar volume of at least 5 million dollars (on at least 15 of the 20 sessions).',
        'return',
            'Percent change of the close from 5, 21, 63 or 126 sessions before the newest session (1 week, 1 month, 3 months, 6 months) to the newest close. A stock without a bar on the base session is not ranked for that period.',
        'pct_from_high',
            'The newest close against the highest daily high of the last 252 sessions, in percent (0 = at the high, negative = below it).',
        'adr20',
            'Average daily range: the mean of high divided by low over the last 20 sessions, as a percent above 1.',
        'dollar_volume',
            'Median of close times volume over the last 20 sessions.',
        'deal_pinned',
            'Left out: a stock held at a buyout price. Each of the last 4 sessions traded inside 2 percent of the close, and within 180 days one day rose 15 percent or more on at least 10 times its 21-day average volume.',
        'sector',
            'The nightly RS run''s sector when the stock is in it, else the cached sector; empty when neither has one.',
        'themes',
            'The active themes that hold the stock today (newest row per theme in the last 7 days, not Retired).',
        'not_claimed',
            'Display only. Nothing here feeds a trade, a grade, an alert or any sizing.'
    )
)
  FROM k
 WHERE k.as_of IS NOT NULL;
