SET default_transaction_read_only = on;
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
newsdef(event_type, country, release, family, cause_up, cause_down) AS (
    VALUES
        ('AU_CPI', 'Australia', 'CPI inflation', NULL, NULL, NULL),
        ('AU_JOBS', 'Australia', 'jobs report', NULL, NULL, NULL),
        ('AU_WAGES', 'Australia', 'wage price index', NULL, NULL, NULL),
        ('BOC', 'Canada', 'Bank of Canada rate decision', NULL, NULL, NULL),
        ('BOE', 'UK', 'Bank of England rate decision', NULL, NULL, NULL),
        ('BOJ', 'Japan', 'Bank of Japan rate decision', NULL, NULL, NULL),
        ('CPI', 'US', 'CPI inflation', 'inflation', 'hotter US inflation', 'cooler US inflation'),
        ('EARN', 'US', '{tk} earnings', 'earnings', '{tk} earnings beating forecast', '{tk} earnings missing forecast'),
        ('ECB', 'Euro area', 'ECB rate decision', NULL, NULL, NULL),
        ('EIA_NATGAS', 'US', 'EIA weekly gas storage', 'gas_stocks', 'a bigger US gas storage build (or smaller draw) than expected', 'a smaller US gas storage build (or bigger draw) than expected'),
        ('EIA_PETRO', 'US', 'EIA weekly oil stocks', 'oil_stocks', 'a bigger US stock build (or smaller draw) than expected', 'a smaller US stock build (or bigger draw) than expected'),
        ('FED_MINUTES', 'US', 'Fed meeting minutes', NULL, NULL, NULL),
        ('FOMC', 'US', 'Fed rate decision', 'fed', 'a higher Fed rate than expected', 'a lower Fed rate than expected'),
        ('GDP', 'US', 'GDP', 'growth', 'stronger US growth', 'weaker US growth'),
        ('NFP', 'US', 'jobs report', 'growth', 'a stronger US jobs market', 'a weaker US jobs market'),
        ('OPEC', 'OPEC+', 'meeting', NULL, NULL, NULL),
        ('PCE', 'US', 'PCE inflation', 'inflation', 'hotter US inflation', 'cooler US inflation'),
        ('PPI', 'US', 'PPI producer prices', 'inflation', 'hotter US producer-price inflation', 'cooler US producer-price inflation'),
        ('RBA', 'Australia', 'RBA rate decision', NULL, NULL, NULL),
        ('RBA_MINUTES', 'Australia', 'RBA meeting minutes', NULL, NULL, NULL),
        ('RETAIL', 'US', 'retail sales', 'growth', 'stronger US consumer spending', 'weaker US consumer spending'),
        ('SNB', 'Switzerland', 'SNB rate decision', NULL, NULL, NULL),
        ('USDA_EXPORTS', 'US', 'USDA weekly export sales', NULL, NULL, NULL),
        ('WASDE', 'US', 'USDA WASDE crop report', NULL, NULL, NULL)
),
whygrp(market, grp) AS (
    VALUES
        ('australian_dollar', 'usd_fx'),
        ('bitcoin', 'crypto'),
        ('bonds_30y', 'bonds'),
        ('british_pound', 'usd_fx'),
        ('canadian_dollar', 'usd_fx'),
        ('copper', 'copper'),
        ('crude_oil', 'oil'),
        ('dollar_index', 'dollar'),
        ('dow', 'equities'),
        ('ethereum', 'crypto'),
        ('euro', 'usd_fx'),
        ('gold', 'precious'),
        ('heating_oil', 'oil'),
        ('japanese_yen', 'usd_fx'),
        ('nasdaq', 'equities'),
        ('natural_gas', 'natgas'),
        ('new_zealand_dollar', 'usd_fx'),
        ('notes_10y', 'bonds'),
        ('notes_2y', 'bonds'),
        ('notes_5y', 'bonds'),
        ('russell', 'small_caps'),
        ('silver', 'precious'),
        ('sp500', 'equities'),
        ('swiss_franc', 'usd_fx'),
        ('unleaded_gas', 'oil')
),
whydef(family, grp, sign, effect_up, effect_down) AS (
    VALUES
        ('earnings', 'equities', 1, 'lifts large US stocks broadly', 'weighs on large US stocks broadly'),
        ('fed', 'bonds', -1, 'lifts US interest rates, and bond prices fall as yields rise', 'lowers US interest rates, and bond prices rise as yields fall'),
        ('fed', 'crypto', -1, 'lifts US interest rates and the dollar, which weighs on risky assets', 'lowers US interest rates and the dollar, which supports risky assets'),
        ('fed', 'dollar', 1, 'lifts US interest rates and the US dollar', 'lowers US interest rates and the US dollar'),
        ('fed', 'equities', -1, 'lifts US interest rates, which weighs on stock prices', 'lowers US interest rates, which supports stock prices'),
        ('fed', 'precious', -1, 'lifts US interest rates and the dollar; {mk} pays no interest and is priced in dollars', 'lowers US interest rates and the dollar; {mk} pays no interest and is priced in dollars'),
        ('fed', 'small_caps', -1, 'lifts US interest rates, which weighs on stock prices', 'lowers US interest rates, which supports stock prices'),
        ('fed', 'usd_fx', -1, 'lifts US interest rates and the US dollar against the {mk}', 'lowers US interest rates and the US dollar against the {mk}'),
        ('gas_stocks', 'natgas', -1, 'means more gas supply on hand', 'means less gas supply on hand'),
        ('growth', 'bonds', -1, 'lifts US interest rates, and bond prices fall as yields rise', 'lowers US interest rates, and bond prices rise as yields fall'),
        ('growth', 'copper', 1, 'means more demand for industrial metals', 'means less demand for industrial metals'),
        ('growth', 'dollar', 1, 'lifts US interest rates and the US dollar', 'lowers US interest rates and the US dollar'),
        ('growth', 'precious', -1, 'lifts US interest rates and the dollar; {mk} pays no interest and is priced in dollars', 'lowers US interest rates and the dollar; {mk} pays no interest and is priced in dollars'),
        ('growth', 'usd_fx', -1, 'lifts US interest rates and the US dollar against the {mk}', 'lowers US interest rates and the US dollar against the {mk}'),
        ('inflation', 'bonds', -1, 'lifts US interest rates, and bond prices fall as yields rise', 'lowers US interest rates, and bond prices rise as yields fall'),
        ('inflation', 'crypto', -1, 'lifts US interest rates and the dollar, which weighs on risky assets', 'lowers US interest rates and the dollar, which supports risky assets'),
        ('inflation', 'dollar', 1, 'lifts US interest rates and the US dollar', 'lowers US interest rates and the US dollar'),
        ('inflation', 'equities', -1, 'lifts US interest rates, which weighs on stock prices', 'lowers US interest rates, which supports stock prices'),
        ('inflation', 'precious', -1, 'lifts US interest rates and the dollar; {mk} pays no interest and is priced in dollars', 'lowers US interest rates and the dollar; {mk} pays no interest and is priced in dollars'),
        ('inflation', 'small_caps', -1, 'lifts US interest rates, which weighs on stock prices', 'lowers US interest rates, which supports stock prices'),
        ('inflation', 'usd_fx', -1, 'lifts US interest rates and the US dollar against the {mk}', 'lowers US interest rates and the US dollar against the {mk}'),
        ('oil_stocks', 'oil', -1, 'means more {mk} supply on hand', 'means less {mk} supply on hand')
),
-- News in plain words (2026-11-27). newsdef / whygrp / whydef mirror cot_family.RELEASE_NAMES + WHY_FAMILY + WHY_CAUSE,
-- WHY_GROUP and WHY (a test keeps them equal). They give an alert news item / a news-watch entry that the job stored
-- BEFORE these words existed its country, release and why chain ({mk} = the market's name, {tk} = the company ticker).
-- A stored key always wins; nothing here invents a figure.
words AS (
    SELECT nd.event_type AS ekey, m.market, nd.country,
           CASE WHEN nd.event_type = 'EARN' THEN nd.release ELSE nd.country || ' ' || nd.release END AS head,
           CASE WHEN wd.sign IS NULL THEN NULL ELSE
               nd.cause_up || ' ' || replace(wd.effect_up, '{mk}', initcap(m.name)) || ' → '
               || CASE WHEN wd.sign > 0 THEN 'bullish' ELSE 'bearish' END || ' ' || initcap(m.name) END AS why_up,
           CASE WHEN wd.sign IS NULL THEN NULL ELSE
               nd.cause_down || ' ' || replace(wd.effect_down, '{mk}', initcap(m.name)) || ' → '
               || CASE WHEN wd.sign > 0 THEN 'bearish' ELSE 'bullish' END || ' ' || initcap(m.name) END AS why_down
      FROM newsdef nd
     CROSS JOIN meta m
      LEFT JOIN whygrp wg ON wg.market = m.market
      LEFT JOIN whydef wd ON wd.family = nd.family AND wd.grp = wg.grp
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
                                'strict', nw.strict, 'alerted', nw.alerted,
                                -- 2026-11-27: whose release and which (with the period a stored figure carries), and
                                -- the why chain of a judged bullish / bearish row (NULL when there is none)
                                'country', wds.country,
                                'release', replace(wds.head, '{tk}', substr(nw.event_type, 6))
                                           || COALESCE(' (' || (SELECT x.s ->> 'period'
                                                                  FROM jsonb_array_elements(CASE WHEN jsonb_typeof(nw.series) = 'array'
                                                                                                 THEN nw.series ELSE '[]'::jsonb END)
                                                                       WITH ORDINALITY AS x(s, ord)
                                                                 WHERE COALESCE(x.s ->> 'period', '') <> ''
                                                                 ORDER BY x.ord LIMIT 1) || ')', ''),
                                'why', CASE WHEN nw.news_class IN ('WITH', 'AGAINST') AND nw.surprise_z <> 0
                                            THEN replace(CASE WHEN nw.surprise_z > 0 THEN wds.why_up ELSE wds.why_down END,
                                                         '{tk}', substr(nw.event_type, 6)) END)
                                ORDER BY nw.event_date, nw.release_et, nw.event_type)
                              FROM mi_cot_news_watch nw
                              LEFT JOIN words wds
                                ON wds.ekey = CASE WHEN left(nw.event_type, 5) = 'EARN_' THEN 'EARN' ELSE nw.event_type END
                               AND wds.market = nw.market
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
),
-- Each alert's news[] with the 2026-11-27 words filled where the stored item lacks them (alerts stored before then):
-- country, release, why (from `words`), and the released figures from that day's news-watch row of the same market and
-- event when one exists (forecast = the figure listed on the release-day read, which the alert was scored on). The
-- stored keys always win. Old alerts whose day has no news-watch row get NO figures: the job never stored them.
al_news AS (
    SELECT a.id,
           jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
                   'country', wds.country,
                   'release', replace(wds.head, '{tk}', substr(n.item ->> 'event', 6)) || COALESCE(' (' || ws.per || ')', ''),
                   'series', ws.series,
                   'why', CASE WHEN n.item ->> 'class' IN ('WITH', 'AGAINST') AND jsonb_typeof(n.item -> 'z') = 'number'
                                    AND (n.item ->> 'z')::float8 <> 0
                               THEN replace(CASE WHEN (n.item ->> 'z')::float8 > 0 THEN wds.why_up ELSE wds.why_down END,
                                            '{tk}', substr(n.item ->> 'event', 6)) END))
                     || n.item ORDER BY n.ord) AS news
      FROM al a
     CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(a.det -> 'news') = 'array' THEN a.det -> 'news'
                                                  ELSE '[]'::jsonb END) WITH ORDINALITY AS n(item, ord)
      LEFT JOIN words wds
        ON wds.ekey = CASE WHEN left(n.item ->> 'event', 5) = 'EARN_' THEN 'EARN' ELSE n.item ->> 'event' END
       AND wds.market = a.market
      LEFT JOIN LATERAL (
          SELECT jsonb_agg(jsonb_build_object('name', x.s ->> 'name', 'label', COALESCE(x.s ->> 'label', x.s ->> 'name'),
                                              'period', x.s ->> 'period', 'actual', x.s ->> 'actual',
                                              'forecast', COALESCE(x.s ->> 'forecast_after', x.s ->> 'forecast'),
                                              'previous', x.s ->> 'previous') ORDER BY x.ord) AS series,
                 (array_agg(x.s ->> 'period' ORDER BY x.ord) FILTER (WHERE COALESCE(x.s ->> 'period', '') <> ''))[1] AS per
            FROM mi_cot_news_watch nw
           CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(nw.series) = 'array' THEN nw.series
                                                        ELSE '[]'::jsonb END) WITH ORDINALITY AS x(s, ord)
           WHERE nw.event_date = a.alert_date AND nw.event_type = n.item ->> 'event' AND nw.market = a.market
             AND x.s ->> 'actual' IS NOT NULL
      ) ws ON true
     WHERE jsonb_typeof(n.item) = 'object'
     GROUP BY a.id
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
                  'atr', a.det -> 'atr', 'news', COALESCE((SELECT an.news FROM al_news an WHERE an.id = a.id), a.det -> 'news'),
                  'peers', (SELECT po.peers FROM peers_of po WHERE po.market = a.market)) ORDER BY a.alert_date DESC, a.id DESC) FROM al a), '[]'::json),
    'news_watch_asof', (SELECT to_char(max(updated_at) AT TIME ZONE 'America/New_York', 'YYYY-MM-DD"T"HH24:MI:SS') || ' ET'
                          FROM mi_cot_news_watch),
    'definitions', json_build_object(
        'index', 'Each group''s net position as a 0 to 100 index of its own lookback window: 0 is its most short, 100 its most long. comm = commercials, lspec = large speculators, sspec = small speculators.',
        'setup', 'The main rule: the crowd is at an extreme, the direction shown is the way to fade into. close_setup is the looser close list.',
        'exit_watch', 'A market that was in a set up the week before and is not now; the distance to 50 is how far each group still is from neutral.',
        'alerts', 'The newest 60 alerts: news = a failure on a scheduled release, correlation = the peers closed the opposite way to the market, friday = the weekly confirmation. Labels only; nothing here places an order. Each alert also carries the readings behind it: z (the market''s own day move in 20-day ranges, up = positive), peer_z (the peers'' median move, stored positive = the way the set up''s crowd was leaning: UP for a short set up, DOWN for a long one; multiply by +1 for a short set up and -1 for a long one to get the peers'' move in price terms), the index at alert, entry_note, stop_rule, failure_day, atr, news[] and peers[]. Each news[] item also carries fact (the plain words for that release, e.g. inflation hotter than forecast; empty if none) and read (bullish, bearish, in line or no clear read, for THIS market), ready to print; first_minute.move in it is stored the same crowd-signed way as peer_z. Since 2026-11-27 each news[] item also carries country (whose release: US, Australia ...), release (which one, with its period when the source gave it, e.g. US GDP (Q3, second estimate)), series[] (the released figures: label, period, actual, forecast, previous, vs = which way it came out, e.g. stronger / hotter / as forecast), surprise and why (the one-line reason the news is bullish / bearish for THIS market, ending in that same word; empty when there is no read) and text (the whole line). Alerts stored before then get country, release and why filled here, and figures only when that day''s news-watch row holds them.',
        'news_watch', 'Per market, the scheduled events of the last 7 and next 7 days. Before a release: the forecast as last read, and the news to watch for (crowd_outcome, already in plain bullish / bearish words for the market). After: the news against forecast (news_class WITH / AGAINST is the stored crowd-relative class; read it as bullish / bearish for the market with the set up direction: a short set up WITH = bullish, AGAINST = bearish; a long set up the reverse), the first minute, the close, and a verdict. verdict: failure_full = the news pointed one way, the first minute went that way, the close went the other; failure = the news pointed one way, the close went the other; followed_news / shrugged / no_failure = no failure; against_unread = closed against the set up on a news day with no clear news read; pending = no close yet. strict = the three-step rule; alerted = a news alert was sent that day (the looser live rule). Since 2026-11-27 each entry also carries country, release (with its period) and, for a judged bullish / bearish row, why; series[] items carry label and period. Labels only.',
        'not_claimed', 'Display only. Nothing here feeds a trade, a grade, an alert or any sizing.'
    )
)
  FROM latest
 WHERE (SELECT report_date FROM latest) IS NOT NULL;
