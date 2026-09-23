-- #620 fixture fix — bar coverage check for the 7 BASELINE_DEBT names before any admission
-- verdict is attempted (READ-ONLY, $0). Run once, read many:
--   ssh apollo@87.99.134.162 'docker exec -i apollo-postgres psql -U apollo -d apollo -A -F "|"' \
--       < scripts/probes/_620_bar_coverage.sql > scripts/probes/_620_bar_coverage_out.txt
--
-- Checks mi_intraday_bars retention coverage for the 7 fixture members (all March-April 2026,
-- >120 days before today 2026-09-03 -- the retention was 120d until 2026-08-15) plus their
-- mi_daily_closes rows (to see if a split rewrote the prior close, per #617's LGCL lesson).

\echo === COVERAGE ===
WITH pairs(ticker, alert_date) AS (
  VALUES ('STRL','2026-04-08'::date), ('ASX','2026-04-08'::date), ('NBIS','2026-04-08'::date),
         ('HUT','2026-04-08'::date), ('IREN','2026-04-08'::date), ('SMTC','2026-03-30'::date),
         ('QCOM','2026-04-24'::date)
)
SELECT p.ticker, p.alert_date,
       COUNT(b.bar_time) AS bar_count,
       MIN(b.bar_time AT TIME ZONE 'America/New_York') AS first_bar_et,
       MAX(b.bar_time AT TIME ZONE 'America/New_York') AS last_bar_et
FROM pairs p
LEFT JOIN mi_intraday_bars b
  ON b.ticker = p.ticker
 AND (b.bar_time AT TIME ZONE 'America/New_York')::date = p.alert_date
GROUP BY p.ticker, p.alert_date
ORDER BY p.alert_date, p.ticker;

\echo === OVERALL_MI_INTRADAY_BARS_RANGE ===
SELECT MIN(bar_time) AS earliest_bar, MAX(bar_time) AS latest_bar, COUNT(*) AS total_rows
FROM mi_intraday_bars;

\echo === DAILY_CLOSES ===
WITH pairs(ticker, alert_date) AS (
  VALUES ('STRL','2026-04-08'::date), ('ASX','2026-04-08'::date), ('NBIS','2026-04-08'::date),
         ('HUT','2026-04-08'::date), ('IREN','2026-04-08'::date), ('SMTC','2026-03-30'::date),
         ('QCOM','2026-04-24'::date)
)
SELECT dc.ticker, dc.trade_date, dc.open_price, dc.high_price, dc.low_price, dc.close, dc.volume
FROM mi_daily_closes dc
JOIN pairs p ON p.ticker = dc.ticker
WHERE dc.trade_date BETWEEN p.alert_date - INTERVAL '5 days' AND p.alert_date
ORDER BY dc.ticker, dc.trade_date;

\echo === SCAN_LOG_CHECK ===
-- Confirm these really left no mi_ep_scan_log row on their alert_date (the fixture's own claim).
WITH pairs(ticker, alert_date) AS (
  VALUES ('STRL','2026-04-08'::date), ('ASX','2026-04-08'::date), ('NBIS','2026-04-08'::date),
         ('HUT','2026-04-08'::date), ('IREN','2026-04-08'::date), ('SMTC','2026-03-30'::date),
         ('QCOM','2026-04-24'::date)
)
SELECT p.ticker, p.alert_date, COUNT(s.*) AS scan_log_rows
FROM pairs p
LEFT JOIN mi_ep_scan_log s ON s.ticker = p.ticker AND s.scan_date = p.alert_date
GROUP BY p.ticker, p.alert_date
ORDER BY p.alert_date, p.ticker;
