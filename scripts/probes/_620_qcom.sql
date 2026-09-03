-- #620 fixture fix -- QCOM's actual 2026-04-24 mi_ep_scan_log row + its stored minute bars.
-- READ-ONLY, $0. Run once, read many:
--   ssh apollo@87.99.134.162 'docker exec -i apollo-postgres psql -U apollo -d apollo -A -F "|"' \
--       < scripts/probes/_620_qcom.sql > scripts/probes/_620_qcom_out.txt
--
-- Why: the fixture (tests/fixtures/must_not_miss_eps.py) recorded QCOM 2026-04-24 as excluded by
-- MIN_GAP_PCT on an 8.70% SESSION-OPEN gap (_552_cohort.psv basis). QCOM has full mi_intraday_bars
-- coverage for that day (retention starts 2026-04-13), and mi_ep_scan_log has a REAL row for it --
-- both queried here to settle what actually excluded it.

\echo === QCOM_SCAN_LOG_ROW ===
SELECT * FROM mi_ep_scan_log WHERE ticker='QCOM' AND scan_date='2026-04-24';

\echo === QCOM_MIN_BARS ===
SELECT (bar_time AT TIME ZONE 'America/New_York') AS et_time, open, high, low, close, volume
FROM mi_intraday_bars
WHERE ticker='QCOM' AND (bar_time AT TIME ZONE 'America/New_York')::date = '2026-04-24'
  AND (bar_time AT TIME ZONE 'America/New_York')::time BETWEEN '09:29:00' AND '10:00:00'
ORDER BY bar_time;
