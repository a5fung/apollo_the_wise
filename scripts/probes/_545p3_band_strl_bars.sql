-- #545 Phase 3, prerequisite 3 — READ-ONLY. Are BAND 2026-04-30 and STRL 2026-05-05 replayable
-- at all? Both carried `stop_too_wide` once, both now sit in mi_ep_missed_outcomes under
-- scan_filter reasons (BAND: session_rvol_low; STRL: duplicate_scan), neither was ever a
-- live-source mi_ep_alerts row, and neither is in any ep_replay capture (alerts / daily /
-- minute). The day-1 bracket cannot be walked on them unless mi_intraday_bars holds their
-- session (the path recorder only stores alert ticker-days, so the expectation is ZERO rows).
-- Run:
--   ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|'" \
--     < scripts/probes/_545p3_band_strl_bars.sql > scripts/probes/_545p3_band_strl_out.psv
\echo === MINUTE_BARS ===
SELECT ticker, (bar_time AT TIME ZONE 'America/New_York')::date AS d, COUNT(*) AS n_bars,
       MIN(bar_time AT TIME ZONE 'America/New_York')::time AS first_bar,
       MAX(bar_time AT TIME ZONE 'America/New_York')::time AS last_bar
FROM mi_intraday_bars
WHERE (ticker, (bar_time AT TIME ZONE 'America/New_York')::date)
      IN (('BAND', DATE '2026-04-30'), ('STRL', DATE '2026-05-05'))
GROUP BY 1, 2 ORDER BY 1, 2;
\echo === DAILY_OPEN_GAP ===
-- did they gap at the open (the #595 `setup_at_open` question), from daily bars
SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close,
       LAG(d.close) OVER (PARTITION BY d.ticker ORDER BY d.trade_date) AS prev_close,
       ROUND(100.0 * (d.open_price / NULLIF(LAG(d.close) OVER (PARTITION BY d.ticker ORDER BY d.trade_date), 0) - 1), 2) AS open_gap_pct
FROM mi_daily_closes d
WHERE (d.ticker = 'BAND' AND d.trade_date BETWEEN '2026-04-28' AND '2026-05-29')
   OR (d.ticker = 'STRL' AND d.trade_date BETWEEN '2026-05-01' AND '2026-06-03')
ORDER BY 1, 2;
\echo === ALERT_ROWS ===
SELECT id, ticker, alert_date, source, score_tier, ep_score, detected_at AT TIME ZONE 'America/New_York' AS detected_et
FROM mi_ep_alerts WHERE (ticker, alert_date) IN (('BAND', DATE '2026-04-30'), ('STRL', DATE '2026-05-05'));
\echo === MISSED_ROWS ===
SELECT ticker, scan_date, skip_stage, skip_reason, setup_at_open, ret_5d, ret_20d, max_high_20d
FROM mi_ep_missed_outcomes WHERE (ticker, scan_date) IN (('BAND', DATE '2026-04-30'), ('STRL', DATE '2026-05-05'));
