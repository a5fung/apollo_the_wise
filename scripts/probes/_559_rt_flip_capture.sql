-- #559 rt-flip readiness — ONE read-only capture, 2026-08-25. Never re-run to re-read.
-- Consumed by scripts/probes/_559_rt_flip_analysis.py. Prod READ-ONLY, $0.

-- q1: every ep_rt_universe_catch shadow event (one per ticker/day by dedupe), ALL TIME
\copy (SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, detail::json->>'ticker' AS ticker, detail::json->>'tick_et' AS tick_et, detail::json->>'rt_gap' AS rt_gap, detail::json->>'delayed_gap' AS delayed_gap, detail::json->>'basis' AS basis, detail::json->>'q1_pass' AS q1_pass, detail::json->>'quote_state' AS quote_state, detail::json->>'prev_close_verified' AS pcv, detail::json->>'authoritative' AS auth FROM mi_audit_log WHERE event_type='ep_rt_universe_catch' ORDER BY created_at) TO '/tmp/_559_catches.tsv' WITH (FORMAT csv, DELIMITER E'\t', HEADER true)

-- q2: per-day coverage health (continuity of the shadow recording)
\copy (SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, count(*) AS ticks, min((detail::json->>'returned')::int) AS min_returned, min((detail::json->>'universe')::int) AS min_universe, max((detail::json->>'missing_count')::int) AS max_missing, round(avg((detail::json->>'returned')::numeric / NULLIF((detail::json->>'universe')::numeric,0))*100,1) AS avg_cov_pct FROM mi_audit_log WHERE event_type='ep_rt_universe_coverage' GROUP BY 1 ORDER BY 1) TO '/tmp/_559_coverage.tsv' WITH (FORMAT csv, DELIMITER E'\t', HEADER true)

-- q2b: other rt event daily counts (sustain rejects, degrades, quality rejects, retreats, no-price)
\copy (SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, event_type, count(*) AS n FROM mi_audit_log WHERE event_type LIKE 'ep_rt_%' AND event_type <> 'ep_rt_universe_coverage' GROUP BY 1,2 ORDER BY 1,2) TO '/tmp/_559_rtevents.tsv' WITH (FORMAT csv, DELIMITER E'\t', HEADER true)

-- q3: every live EP alert since 2026-05-01 (comparison population + cooldown source)
\copy (SELECT ticker, alert_date, gap_pct, ep_score, score_tier, catalyst_quality, in_active_theme, rel_volume, pm_rvol FROM mi_ep_alerts WHERE COALESCE(source,'live')='live' AND alert_date >= '2026-05-01' ORDER BY alert_date, ticker) TO '/tmp/_559_alerts.tsv' WITH (FORMAT csv, DELIMITER E'\t', HEADER true)

-- q4: EVERY scan-log row (all ticks) for catch tickers on their catch dates
\copy (WITH ev AS (SELECT DISTINCT detail::json->>'ticker' AS t, (created_at AT TIME ZONE 'America/New_York')::date AS d FROM mi_audit_log WHERE event_type='ep_rt_universe_catch') SELECT s.scan_date, s.ticker, s.scan_time_et AT TIME ZONE 'America/New_York' AS scan_et, s.gap_pct, s.prev_close, s.rel_volume, s.filter_reason, s.ep_score, s.score_tier, s.catalyst_quality, s.rank_by_gap, s.projected_vol_multiple, s.pm_rvol, s.adv, s.adv_source, s.minutes_since_open, s.price_source FROM mi_ep_scan_log s JOIN ev ON ev.t=s.ticker AND ev.d=s.scan_date ORDER BY s.scan_date, s.ticker, s.scan_time_et) TO '/tmp/_559_scanlog.tsv' WITH (FORMAT csv, DELIMITER E'\t', HEADER true)

-- q5: daily OHLC bars for catch tickers, 2026-05-01 onward (open-hold test, ATR14, ADR, tail)
\copy (WITH tk AS (SELECT DISTINCT detail::json->>'ticker' AS t FROM mi_audit_log WHERE event_type='ep_rt_universe_catch') SELECT ticker, trade_date, open_price, high_price, low_price, close, volume FROM mi_daily_closes WHERE ticker IN (SELECT t FROM tk) AND trade_date >= '2026-05-01' ORDER BY ticker, trade_date) TO '/tmp/_559_daily.tsv' WITH (FORMAT csv, DELIMITER E'\t', HEADER true)

-- q6: market caps for catch tickers
\copy (WITH tk AS (SELECT DISTINCT detail::json->>'ticker' AS t FROM mi_audit_log WHERE event_type='ep_rt_universe_catch') SELECT ticker, market_cap FROM mi_market_caps WHERE ticker IN (SELECT t FROM tk)) TO '/tmp/_559_mcaps.tsv' WITH (FORMAT csv, DELIMITER E'\t', HEADER true)

-- q7: ADV$ replayed EXACTLY as backtester.filters._check_adv_dollar_volume does, per ticker/catch-date
\copy (WITH ev AS (SELECT DISTINCT detail::json->>'ticker' AS t, (created_at AT TIME ZONE 'America/New_York')::date AS d FROM mi_audit_log WHERE event_type='ep_rt_universe_catch') SELECT ev.t AS ticker, ev.d AS scan_date, x.adv_dollar, x.n FROM ev LEFT JOIN LATERAL (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY close*volume) AS adv_dollar, count(*) AS n FROM mi_daily_closes m WHERE m.ticker=ev.t AND m.trade_date <= ev.d AND m.trade_date >= ev.d - INTERVAL '30 days' AND m.volume > 0) x ON true ORDER BY 1,2) TO '/tmp/_559_advdollar.tsv' WITH (FORMAT csv, DELIMITER E'\t', HEADER true)

-- q8: 20-day ADV in SHARES ending the day BEFORE the catch (ex-ante liquidity axis input)
\copy (WITH ev AS (SELECT DISTINCT detail::json->>'ticker' AS t, (created_at AT TIME ZONE 'America/New_York')::date AS d FROM mi_audit_log WHERE event_type='ep_rt_universe_catch') SELECT ev.t AS ticker, ev.d AS scan_date, x.adv_shares, x.n, x.last_close FROM ev LEFT JOIN LATERAL (SELECT avg(volume) AS adv_shares, count(*) AS n, (array_agg(close ORDER BY trade_date DESC))[1] AS last_close FROM (SELECT trade_date, volume, close FROM mi_daily_closes m WHERE m.ticker=ev.t AND m.trade_date < ev.d AND m.volume>0 ORDER BY trade_date DESC LIMIT 20) z) x ON true ORDER BY 1,2) TO '/tmp/_559_adv20.tsv' WITH (FORMAT csv, DELIMITER E'\t', HEADER true)

-- q9: active theme membership (Accelerating/Mainstream) per theme_date, for the theme axis
\copy (SELECT theme_date, name, stage, tickers FROM mi_themes WHERE theme_date >= '2026-07-20' AND stage IN ('Accelerating','Mainstream') ORDER BY theme_date, name) TO '/tmp/_559_themes.tsv' WITH (FORMAT csv, DELIMITER E'\t', HEADER true)

-- q10: HOW MANY names the delayed scan graded per day (the top-20 shortlist occupancy = is there room)
\copy (SELECT scan_date, count(DISTINCT ticker) FILTER (WHERE ep_score IS NOT NULL) AS graded_n, count(DISTINCT ticker) AS seen_n FROM mi_ep_scan_log WHERE scan_date >= '2026-07-27' GROUP BY 1 ORDER BY 1) TO '/tmp/_559_dailyfunnel.tsv' WITH (FORMAT csv, DELIMITER E'\t', HEADER true)

-- q11: security-type membership for catch tickers (universe pre-clearance sanity)
\copy (WITH tk AS (SELECT DISTINCT detail::json->>'ticker' AS t FROM mi_audit_log WHERE event_type='ep_rt_universe_catch') SELECT ticker, security_type FROM mi_security_types WHERE ticker IN (SELECT t FROM tk)) TO '/tmp/_559_sectypes.tsv' WITH (FORMAT csv, DELIMITER E'\t', HEADER true)
