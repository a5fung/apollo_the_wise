-- #490 delayed-screen-cost funnel — ONE capture (read-only), 2026-08-18.
-- Consumed by scripts/probes/_490_delayed_cost_funnel.py. Never re-run to re-read.

-- q1: every ep_rt_universe_catch shadow event (one per ticker/day by dedupe)
\copy (SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, detail::json->>'ticker' AS ticker, detail::json->>'tick_et' AS tick_et, detail::json->>'rt_gap' AS rt_gap, detail::json->>'delayed_gap' AS delayed_gap, detail::json->>'basis' AS basis, detail::json->>'q1_pass' AS q1_pass, detail::json->>'prev_close_verified' AS pcv FROM mi_audit_log WHERE event_type='ep_rt_universe_catch' ORDER BY created_at) TO '/tmp/_490cost_events.tsv' WITH (FORMAT csv, DELIMITER E'\t', HEADER true)

-- q2: live alerts over the window (the comparison population)
\copy (SELECT ticker, alert_date, gap_pct, ep_score, score_tier FROM mi_ep_alerts WHERE COALESCE(source,'live')='live' AND alert_date BETWEEN '2026-07-27' AND '2026-08-18' ORDER BY alert_date, ticker) TO '/tmp/_490cost_alerts.tsv' WITH (FORMAT csv, DELIMITER E'\t', HEADER true)

-- q3: daily bars for catch + window-alert tickers, 2026-06-01..today
\copy (WITH tk AS (SELECT DISTINCT detail::json->>'ticker' AS t FROM mi_audit_log WHERE event_type='ep_rt_universe_catch' UNION SELECT DISTINCT ticker FROM mi_ep_alerts WHERE COALESCE(source,'live')='live' AND alert_date BETWEEN '2026-07-27' AND '2026-08-18') SELECT ticker, trade_date, open_price, high_price, low_price, close, volume FROM mi_daily_closes WHERE ticker IN (SELECT t FROM tk) AND trade_date >= '2026-06-01' ORDER BY ticker, trade_date) TO '/tmp/_490cost_daily.tsv' WITH (FORMAT csv, DELIMITER E'\t', HEADER true)

-- q4: market caps for the same tickers
\copy (WITH tk AS (SELECT DISTINCT detail::json->>'ticker' AS t FROM mi_audit_log WHERE event_type='ep_rt_universe_catch') SELECT ticker, market_cap FROM mi_market_caps WHERE ticker IN (SELECT t FROM tk)) TO '/tmp/_490cost_mcaps.tsv' WITH (FORMAT csv, DELIMITER E'\t', HEADER true)

-- q5: did the delayed scan log ever see the catch ticker that day (attribution)
\copy (WITH ev AS (SELECT DISTINCT detail::json->>'ticker' AS t, (created_at AT TIME ZONE 'America/New_York')::date AS d FROM mi_audit_log WHERE event_type='ep_rt_universe_catch') SELECT ev.t AS ticker, ev.d, COALESCE(s.n,0) AS scan_n, COALESCE(s.reasons,'') AS reasons, COALESCE(s.max_score::text,'') AS max_score FROM ev LEFT JOIN LATERAL (SELECT count(*) n, string_agg(DISTINCT COALESCE(filter_reason,'<none>'),' ;; ') reasons, max(ep_score) max_score FROM mi_ep_scan_log s WHERE s.ticker=ev.t AND s.scan_date=ev.d) s ON true ORDER BY ev.d, ev.t) TO '/tmp/_490cost_scanlog.tsv' WITH (FORMAT csv, DELIMITER E'\t', HEADER true)
