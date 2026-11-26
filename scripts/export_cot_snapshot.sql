-- COT FAMILY — read-only export for portfolio-app2's "COT" page: the newest weekly COT index per market, the 12
-- weeks before it (sparklines + the exit watch), and the last 60 alerts. ONE SELECT, one JSON object on stdout, run
-- guarded by scripts/auto_export_snapshots.sh (a failure here never blocks the other snapshots):
--   docker exec -i apollo-postgres psql -U apollo -d apollo -A -t -X -v ON_ERROR_STOP=1 \
--     -f - < export_cot_snapshot.sql > apollo_cot_snapshot.json
-- SSoT: docs/architecture/cot_snapshot.md. READ-ONLY, display only: no money path, no order, no alert input.
-- Weeks are the distinct report_dates in mi_cot_index_weekly (rank 1 = newest), never calendar arithmetic, so a
-- holiday-shifted week is one week. Display names + sectors: the VALUES list below mirrors cot_family.MARKETS
-- (a test fails if they drift). news_watch / news_watch_asof come from mi_cot_news_watch (added 2026-11-25). peerdef mirrors cot_family.PEERS the same way ('-x' = an inverse peer); it lets each
-- alert carry the NAMES of the peers its correlation reading was taken over.
WITH wk AS (
    SELECT report_date, (dense_rank() OVER (ORDER BY report_date DESC))::int AS rk
      FROM (SELECT DISTINCT report_date FROM mi_cot_index_weekly) d
),
latest AS (
    SELECT report_date FROM wk WHERE rk = 1
),
-- the news watch shows the events of the last 7 days and the next 7 (ET today, never the container's UTC date)
today_et AS (
    SELECT (now() AT TIME ZONE 'America/New_York')::date AS d
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
peerdef(market, peer_list) AS (
    VALUES
        ('australian_dollar', 'british_pound,canadian_dollar,euro,japanese_yen,swiss_franc,new_zealand_dollar,-dollar_index'),
        ('bonds_30y', 'notes_10y,notes_5y,notes_2y'),
        ('british_pound', 'australian_dollar,canadian_dollar,euro,japanese_yen,swiss_franc,new_zealand_dollar,-dollar_index'),
        ('canadian_dollar', 'australian_dollar,british_pound,euro,japanese_yen,swiss_franc,new_zealand_dollar,-dollar_index'),
        ('copper', 'sp500,silver,platinum'),
        ('corn', 'soybeans,soybean_meal,wheat'),
        ('cotton', 'crude_oil'),
        ('crude_oil', 'heating_oil,unleaded_gas'),
        ('dollar_index', '-australian_dollar,-british_pound,-canadian_dollar,-euro,-japanese_yen,-swiss_franc,-new_zealand_dollar'),
        ('dow', 'nasdaq,russell,sp500'),
        ('euro', 'australian_dollar,british_pound,canadian_dollar,japanese_yen,swiss_franc,new_zealand_dollar,-dollar_index'),
        ('gold', 'silver,platinum,palladium'),
        ('heating_oil', 'crude_oil,unleaded_gas'),
        ('japanese_yen', 'australian_dollar,british_pound,canadian_dollar,euro,swiss_franc,new_zealand_dollar,-dollar_index'),
        ('nasdaq', 'dow,russell,sp500'),
        ('new_zealand_dollar', 'australian_dollar,british_pound,canadian_dollar,euro,japanese_yen,swiss_franc,-dollar_index'),
        ('notes_10y', 'bonds_30y,notes_5y,notes_2y'),
        ('notes_2y', 'bonds_30y,notes_10y,notes_5y'),
        ('notes_5y', 'bonds_30y,notes_10y,notes_2y'),
        ('palladium', 'gold,silver,platinum'),
        ('platinum', 'gold,silver,palladium'),
        ('russell', 'dow,nasdaq,sp500'),
        ('silver', 'gold,platinum,palladium'),
        ('soybean_meal', 'soybeans,corn,wheat'),
        ('soybean_oil', 'crude_oil,soybeans'),
        ('soybeans', 'soybean_meal,corn,wheat'),
        ('sp500', 'dow,nasdaq,russell'),
        ('sugar', 'crude_oil'),
        ('swiss_franc', 'australian_dollar,british_pound,canadian_dollar,euro,japanese_yen,new_zealand_dollar,-dollar_index'),
        ('unleaded_gas', 'crude_oil,heating_oil'),
        ('wheat', 'soybeans,soybean_meal,corn')
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
                              FROM ix h WHERE h.market = m.market AND h.rk BETWEEN 2 AND 13), '[]'::json),
               'news_watch', COALESCE((SELECT json_agg(json_build_object(
                                'event', nw.event_type, 'event_date', nw.event_date,
                                'release_et', to_char(nw.release_et AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI') || ' ET',
                                'direction', nw.direction, 'level', nw.level, 'read', nw.read,
                                'crowd_outcome', nw.crowd_outcome, 'series', nw.series,
                                'forecast_seen_at', to_char(nw.forecast_seen_at AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI') || ' ET',
                                'news_class', nw.news_class, 'surprise_z', nw.surprise_z, 'first_minute', nw.first_minute,
                                'close_z', nw.close_z, 'close_against', nw.close_against, 'verdict', nw.verdict,
                                'strict', nw.strict, 'alerted', nw.alerted)
                                ORDER BY nw.event_date, nw.release_et, nw.event_type)
                              FROM mi_cot_news_watch nw
                             WHERE nw.market = m.market
                               AND nw.event_date BETWEEN (SELECT d FROM today_et) - 7 AND (SELECT d FROM today_et) + 7), '[]'::json)
           ) AS j
      FROM meta m
      JOIN ix cur ON cur.market = m.market AND cur.rk = 1
      LEFT JOIN ix pv ON pv.market = m.market AND pv.rk = 2
),
peers_of AS (
    SELECT d.market,
           json_agg(json_build_object('market', q.peer, 'name', COALESCE(pm.name, q.peer), 'inverse', q.inv)
                    ORDER BY q.ord) AS peers
      FROM peerdef d
     CROSS JOIN LATERAL (SELECT ltrim(t.x, '-') AS peer, left(t.x, 1) = '-' AS inv, t.ord
                           FROM unnest(string_to_array(d.peer_list, ',')) WITH ORDINALITY AS t(x, ord)) q
      LEFT JOIN meta pm ON pm.market = q.peer
     GROUP BY d.market
),
-- detail is jsonb, but some rows hold a JSON STRING that itself contains the JSON (double-encoded): unwrap those; a
-- string that is not an object is read as no detail rather than failing the whole export.
al AS (
    SELECT a.*,
           CASE WHEN jsonb_typeof(a.detail) = 'string' THEN
                    CASE WHEN left(a.detail #>> '{}', 1) = '{' THEN (a.detail #>> '{}')::jsonb END
                ELSE a.detail END AS det
      FROM mi_cot_alerts a ORDER BY a.alert_date DESC, a.id DESC LIMIT 60
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
                  'news_class', a.news_class,
                  'z', a.z, 'peer_z', a.peer_z, 'comm', a.comm, 'lspec', a.lspec, 'sspec', a.sspec,
                  'entry_note', a.entry_note, 'stop_rule', a.stop_rule, 'failure_day', a.failure_day,
                  'atr', a.det -> 'atr', 'news', a.det -> 'news',
                  'peers', (SELECT po.peers FROM peers_of po WHERE po.market = a.market)) ORDER BY a.alert_date DESC, a.id DESC) FROM al a), '[]'::json),
    'news_watch_asof', (SELECT to_char(max(updated_at) AT TIME ZONE 'America/New_York', 'YYYY-MM-DD"T"HH24:MI:SS') || ' ET'
                          FROM mi_cot_news_watch),
    'definitions', json_build_object(
        'index', 'Each group''s net position as a 0 to 100 index of its own lookback window: 0 is its most short, 100 its most long. comm = commercials, lspec = large speculators, sspec = small speculators.',
        'setup', 'The main rule: the crowd is at an extreme, the direction shown is the way to fade into. close_setup is the looser close list.',
        'exit_watch', 'A market that was in a set up the week before and is not now; the distance to 50 is how far each group still is from neutral.',
        'alerts', 'The newest 60 alerts: news = a failure on a scheduled release, correlation = the peers closed the opposite way to the market, friday = the weekly confirmation. Labels only; nothing here places an order. Each alert also carries the readings behind it: z (the market''s own day move in 20-day ranges, up = positive), peer_z (the peers'' median move, stored positive = the way the set up''s crowd was leaning: UP for a short set up, DOWN for a long one; multiply by +1 for a short set up and -1 for a long one to get the peers'' move in price terms), the index at alert, entry_note, stop_rule, failure_day, atr, news[] and peers[]. Each news[] item also carries fact (the plain words for that release, e.g. inflation hotter than forecast; empty if none) and read (bullish, bearish, in line or no clear read, for THIS market), ready to print; first_minute.move in it is stored the same crowd-signed way as peer_z.',
        'news_watch', 'Per market, the scheduled events of the last 7 and next 7 days. Before a release: the forecast as last read, and the news to watch for (crowd_outcome, already in plain bullish / bearish words for the market). After: the news against forecast (news_class WITH / AGAINST is the stored crowd-relative class; read it as bullish / bearish for the market with the set up direction: a short set up WITH = bullish, AGAINST = bearish; a long set up the reverse), the first minute, the close, and a verdict. verdict: failure_full = the news pointed one way, the first minute went that way, the close went the other; failure = the news pointed one way, the close went the other; followed_news / shrugged / no_failure = no failure; against_unread = closed against the set up on a news day with no clear news read; pending = no close yet. strict = the three-step rule; alerted = a news alert was sent that day (the looser live rule). Labels only.',
        'not_claimed', 'Display only. Nothing here feeds a trade, a grade, an alert or any sizing.'
    )
)
  FROM latest
 WHERE (SELECT report_date FROM latest) IS NOT NULL;
