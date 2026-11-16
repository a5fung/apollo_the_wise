-- COT FAMILY — read-only export for portfolio-app2's "COT" page: the newest weekly COT index per market, the 12
-- weeks before it (sparklines + the exit watch), and the last 60 alerts. ONE SELECT, one JSON object on stdout, run
-- guarded by scripts/auto_export_snapshots.sh (a failure here never blocks the other snapshots):
--   docker exec -i apollo-postgres psql -U apollo -d apollo -A -t -X -v ON_ERROR_STOP=1 \
--     -f - < export_cot_snapshot.sql > apollo_cot_snapshot.json
-- SSoT: docs/architecture/cot_snapshot.md. READ-ONLY, display only: no money path, no order, no alert input.
-- Weeks are the distinct report_dates in mi_cot_index_weekly (rank 1 = newest), never calendar arithmetic, so a
-- holiday-shifted week is one week. Display names + sectors: the VALUES list below mirrors cot_family.MARKETS
-- (a test fails if they drift).
WITH wk AS (
    SELECT report_date, (dense_rank() OVER (ORDER BY report_date DESC))::int AS rk
      FROM (SELECT DISTINCT report_date FROM mi_cot_index_weekly) d
),
latest AS (
    SELECT report_date FROM wk WHERE rk = 1
),
meta(market, name, sector) AS (
    VALUES
        ('sp500', 'S&P 500', 'equities'),
        ('nasdaq', 'NASDAQ', 'equities'),
        ('dow', 'DOW', 'equities'),
        ('russell', 'RUSSELL', 'equities'),
        ('bonds_30y', '30-YEAR BONDS', 'fixed_income'),
        ('notes_10y', '10-YEAR NOTES', 'fixed_income'),
        ('notes_5y', '5-YEAR NOTES', 'fixed_income'),
        ('notes_2y', '2-YEAR NOTES', 'fixed_income'),
        ('australian_dollar', 'AUSTRALIAN DOLLAR', 'currencies'),
        ('british_pound', 'BRITISH POUND', 'currencies'),
        ('canadian_dollar', 'CANADIAN DOLLAR', 'currencies'),
        ('euro', 'EURO', 'currencies'),
        ('japanese_yen', 'JAPANESE YEN', 'currencies'),
        ('swiss_franc', 'SWISS FRANC', 'currencies'),
        ('new_zealand_dollar', 'NEW ZEALAND DOLLAR', 'currencies'),
        ('dollar_index', 'DOLLAR INDEX', 'currencies'),
        ('crude_oil', 'CRUDE OIL', 'energies'),
        ('heating_oil', 'HEATING OIL', 'energies'),
        ('unleaded_gas', 'UNLEADED GAS', 'energies'),
        ('natural_gas', 'NATURAL GAS', 'energies'),
        ('corn', 'CORN', 'grains'),
        ('soybean_meal', 'SOYBEAN MEAL', 'grains'),
        ('soybean_oil', 'SOYBEAN OIL', 'grains'),
        ('soybeans', 'SOYBEANS', 'grains'),
        ('wheat', 'WHEAT', 'grains'),
        ('lean_hogs', 'LEAN HOGS', 'livestock'),
        ('live_cattle', 'LIVE CATTLE', 'livestock'),
        ('copper', 'COPPER', 'metals'),
        ('gold', 'GOLD', 'metals'),
        ('palladium', 'PALLADIUM', 'metals'),
        ('platinum', 'PLATINUM', 'metals'),
        ('silver', 'SILVER', 'metals'),
        ('cocoa', 'COCOA', 'softs'),
        ('coffee', 'COFFEE', 'softs'),
        ('cotton', 'COTTON', 'softs'),
        ('lumber', 'LUMBER', 'softs'),
        ('orange_juice', 'ORANGE JUICE', 'softs'),
        ('sugar', 'SUGAR', 'softs'),
        ('bitcoin', 'BITCOIN', 'crypto'),
        ('ethereum', 'ETHEREUM', 'crypto')
),
ix AS (
    SELECT i.market, w.rk, i.report_date, i.comm, i.lspec, i.sspec, i.setup, i.close_setup
      FROM mi_cot_index_weekly i
      JOIN wk w ON w.report_date = i.report_date
     WHERE w.rk <= 13
),
per_market AS (
    SELECT m.market,
           json_build_object(
               'market', m.market, 'name', m.name, 'sector', m.sector,
               'comm', cur.comm, 'lspec', cur.lspec, 'sspec', cur.sspec,
               'setup', cur.setup, 'close_setup', cur.close_setup,
               'prev', CASE WHEN pv.market IS NULL THEN NULL ELSE json_build_object(
                   'report_date', pv.report_date, 'comm', pv.comm, 'lspec', pv.lspec, 'sspec', pv.sspec,
                   'setup', pv.setup, 'close_setup', pv.close_setup) END,
               'history', COALESCE((SELECT json_agg(json_build_object(
                                'report_date', h.report_date, 'comm', h.comm, 'lspec', h.lspec, 'sspec', h.sspec,
                                'setup', h.setup, 'close_setup', h.close_setup) ORDER BY h.report_date)
                              FROM ix h WHERE h.market = m.market AND h.rk BETWEEN 2 AND 13), '[]'::json)
           ) AS j
      FROM meta m
      JOIN ix cur ON cur.market = m.market AND cur.rk = 1
      LEFT JOIN ix pv ON pv.market = m.market AND pv.rk = 2
),
al AS (
    SELECT * FROM mi_cot_alerts ORDER BY alert_date DESC, id DESC LIMIT 60
)
SELECT json_build_object(
    'version', 1,
    'generated_at', to_char(now() AT TIME ZONE 'America/New_York', 'YYYY-MM-DD"T"HH24:MI:SS') || ' ET',
    'report_date', (SELECT report_date FROM latest),
    'known_from', (SELECT known_from FROM mi_cot_weeks WHERE report_date = (SELECT report_date FROM latest)),
    'markets', COALESCE((SELECT json_agg(j ORDER BY market) FROM per_market), '[]'::json),
    'alerts', COALESCE((SELECT json_agg(json_build_object(
                  'alert_date', a.alert_date, 'market', a.market, 'direction', a.direction, 'kind', a.kind,
                  'level', a.level, 'report_date', a.report_date, 'events', a.events,
                  'entry_price', a.entry_price, 'stop_price', a.stop_price,
                  'first_minute', a.first_minute, 'first_minute_big', a.first_minute_big,
                  'news_class', a.news_class) ORDER BY a.alert_date DESC, a.id DESC) FROM al a), '[]'::json),
    'definitions', json_build_object(
        'index', 'Each group''s net position as a 0 to 100 index of its own lookback window: 0 is its most short, 100 its most long. comm = commercials, lspec = large speculators, sspec = small speculators.',
        'setup', 'The main rule: the crowd is at an extreme, the direction shown is the way to fade into. close_setup is the looser close list.',
        'exit_watch', 'A market that was in a set up the week before and is not now; the distance to 50 is how far each group still is from neutral.',
        'alerts', 'The newest 60 alerts: news = a failure on a scheduled release, correlation = the peers moved with the crowd, friday = the weekly confirmation. Labels only; nothing here places an order.',
        'not_claimed', 'Display only. Nothing here feeds a trade, a grade, an alert or any sizing.'
    )
)
  FROM latest
 WHERE (SELECT report_date FROM latest) IS NOT NULL;
