-- #545 Phase 2 capture 2 — the missed-EP tail read, the half capture 1 could not answer.
-- READ-ONLY. Run ONCE, quote from the file (capture once, read many):
--
--   ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|'" \
--     < scripts/probes/_545p2_capture2.sql > scripts/probes/_545p2_capture2_out.psv
--
-- then:  python3 scripts/probes/_545p2_read.py   (ingests the .psv if present)
--
-- WHY A SECOND CAPTURE (each is a population trap capture 1 cannot resolve):
--   1. ERA / SECURITY TYPE. The table opens 2026-04-13; the security-type (ETF/warrant) filter
--      landed 2026-04-20 (commit 171b03d0) and the leveraged-ETF fail-safe 2026-05-17. Capture 1's
--      Q4 top tails (IONL, IONX, CRDU, APLX, QPUX, QBTX, GLXU, LABX, BEX, BEG, MVLL, DLLL — all
--      04-13/14) are leveraged single-stock ETFs today's scan never sees. Pooled tail shares are
--      therefore PRE-FILTER numbers. Every row here carries security_type + a pre-04-20 flag.
--   2. RIGHT-CENSORING. 507 of 1,419 gapped rows have no ret_20d (382 are August). ret_5d is
--      readable on nearly all of them — reported beside ret_20d, never substituted for it.
--   3. ALERT-LEVEL ROWS need their bucket label to join to campaigns_era_c.tsv (the live-bracket
--      replay); the local _ladder_missed.tsv stops at 08-14.
--   4. A prod-side recompute of the traded cohort's own daily-grain proxy, as a cross-check on the
--      local one (_545p2_read.py computes it from _pull2_out.txt).
--
-- 🛑 UNITS: ret_1d/5d/20d, max_high_*, open_gap_pct are FRACTIONS (0.20 = +20%). max_high_* is
--    MFE — positive by construction — NEVER a return. open_gap_pct > 1.0 (= +100%) marks a bad
--    prior close (DLLL 7.1 = "+710%"), not a gap.

\echo === SECTYPE_COVERAGE ===
SELECT security_type, COUNT(*) AS n, MIN(updated_at)::date AS first_seen, MAX(updated_at)::date AS last_seen
FROM mi_security_types GROUP BY 1 ORDER BY 2 DESC;

\echo === BUCKET_MONTH ===
WITH sectored AS (
  SELECT DISTINCT ticker FROM mi_stock_scores WHERE sector IS NOT NULL
), r AS (
  SELECT m.skip_category, m.alert_date, m.ticker,
         date_trunc('month', m.alert_date)::date AS mon,
         (m.alert_date < DATE '2026-04-20') AS pre_sectype_filter,
         CASE WHEN st.security_type IN ('CS','ADRC') THEN 'CS'
              WHEN st.security_type IS NOT NULL THEN 'nonCS'
              WHEN sc.ticker IS NOT NULL THEN 'CS_by_sector'
              ELSE 'unknown' END AS cls,
         m.ret_5d, m.ret_20d,
         (m.close_d0 < m.open_d0) AS day0_red,
         (m.open_gap_pct > 1.0) AS gap_gt100
  FROM mi_ep_missed_outcomes m
  LEFT JOIN mi_security_types st USING (ticker)
  LEFT JOIN sectored sc ON sc.ticker = m.ticker
  WHERE m.setup_at_open IS TRUE
)
SELECT skip_category, mon, pre_sectype_filter, cls,
       COUNT(*)                                        AS n,
       COUNT(DISTINCT alert_date)                      AS sessions,
       COUNT(ret_20d)                                  AS n20,
       COUNT(*) FILTER (WHERE ret_20d >= 0.20)         AS tail20,
       COUNT(*) FILTER (WHERE ret_20d < 0)             AS lose20,
       COUNT(ret_5d)                                   AS n5,
       COUNT(*) FILTER (WHERE ret_5d >= 0.20)          AS tail5_20,
       COUNT(*) FILTER (WHERE ret_5d >= 0.10)          AS tail5_10,
       COUNT(*) FILTER (WHERE ret_5d < 0)              AS lose5,
       COUNT(*) FILTER (WHERE day0_red)                AS day0_red,
       COUNT(*) FILTER (WHERE ret_20d >= 0.20 AND day0_red) AS tail20_day0red,
       COUNT(*) FILTER (WHERE ret_5d  >= 0.20 AND day0_red) AS tail5_day0red,
       COUNT(*) FILTER (WHERE gap_gt100)               AS gap_gt100
FROM r GROUP BY 1,2,3,4 ORDER BY 1,2,3,4;

\echo === TAIL_ROWS ===
-- every gapped row that reached ≥+20% at 5 or 20 sessions — so each tail name can be classified
WITH sectored AS (SELECT DISTINCT ticker FROM mi_stock_scores WHERE sector IS NOT NULL)
SELECT m.ticker, m.alert_date, m.source, m.skip_category, m.skip_reason, m.ep_score,
       st.security_type,
       CASE WHEN st.security_type IN ('CS','ADRC') THEN 'CS'
            WHEN st.security_type IS NOT NULL THEN 'nonCS'
            WHEN sc.ticker IS NOT NULL THEN 'CS_by_sector' ELSE 'unknown' END AS cls,
       m.open_gap_pct, m.open_d0, m.close_d0, m.ret_1d, m.ret_5d, m.ret_20d, m.max_high_20d
FROM mi_ep_missed_outcomes m
LEFT JOIN mi_security_types st USING (ticker)
LEFT JOIN sectored sc ON sc.ticker = m.ticker
WHERE m.setup_at_open IS TRUE AND (m.ret_20d >= 0.20 OR m.ret_5d >= 0.20)
ORDER BY m.skip_category, m.alert_date, m.ticker;

\echo === ALERT_LEVEL_ROWS ===
-- every alert-sourced row (HIGH never traded + MODERATE), gapped or not, for the campaign join
SELECT m.ticker, m.alert_date, m.source, m.skip_category, m.skip_reason, m.ep_score,
       m.open_gap_pct, m.setup_at_open, m.open_d0, m.close_d0,
       m.ret_1d, m.ret_5d, m.ret_20d, m.max_high_5d, m.max_high_20d,
       st.security_type
FROM mi_ep_missed_outcomes m
LEFT JOIN mi_security_types st USING (ticker)
WHERE m.source IN ('moderate_alert', 'high_unentered')
ORDER BY m.alert_date, m.ticker;

\echo === OVERLAP ===
-- a ticker-day can carry a scan_filter row AND an alert row (HTFL is in duplicate_scan AND
-- stop_too_wide) — buckets overlap and must never be summed
SELECT COUNT(*) AS ticker_days_in_2plus_buckets
FROM (SELECT ticker, alert_date FROM mi_ep_missed_outcomes WHERE setup_at_open IS TRUE
      GROUP BY 1,2 HAVING COUNT(DISTINCT skip_category) > 1) x;

\echo === TRADED_PROXY_ROWS ===
-- the SAME daily-grain proxy, on the names we DID trade (first attempts, closed), per account —
-- the pass bar's comparator and the bridge from "tail share" to "what the bracket realized"
WITH t AS (
  SELECT id, ticker, alert_date, account_mode, total_pnl,
         COALESCE(risk_dollars_actual, risk_dollars) AS risk_budget
  FROM mi_live_trades
  WHERE signal_type = 'magna53' AND status = 'closed' AND entry_attempt = 1
)
SELECT t.ticker, t.alert_date, t.account_mode, t.total_pnl, t.risk_budget,
       d0.open_price AS open_d0, d0.close AS close_d0,
       CASE WHEN d0.open_price > 0 AND d5.close  IS NOT NULL THEN (d5.close  - d0.open_price) / d0.open_price END AS ret_5d,
       CASE WHEN d0.open_price > 0 AND d20.close IS NOT NULL THEN (d20.close - d0.open_price) / d0.open_price END AS ret_20d
FROM t
LEFT JOIN LATERAL (SELECT open_price, close FROM mi_daily_closes WHERE ticker = t.ticker AND trade_date = t.alert_date) d0 ON TRUE
LEFT JOIN LATERAL (SELECT close FROM mi_daily_closes WHERE ticker = t.ticker AND trade_date > t.alert_date ORDER BY trade_date ASC OFFSET 4  LIMIT 1) d5  ON TRUE
LEFT JOIN LATERAL (SELECT close FROM mi_daily_closes WHERE ticker = t.ticker AND trade_date > t.alert_date ORDER BY trade_date ASC OFFSET 19 LIMIT 1) d20 ON TRUE
ORDER BY t.account_mode, t.alert_date, t.ticker;

\echo === HTFL ===
SELECT ticker, alert_date, source, skip_category, skip_reason, ep_score, open_gap_pct, setup_at_open,
       open_d0, close_d0, ret_1d, ret_5d, ret_20d, max_high_5d, max_high_20d
FROM mi_ep_missed_outcomes WHERE ticker = 'HTFL' ORDER BY alert_date, source;

\echo === STOP_TOO_WIDE_ALL ===
-- P1 check on the operator's bucket: the 08-14 ladder capture held 13 MAGNA53-format stop_too_wide rows
-- (WST 04-23, WKC 04-24, BAND 04-30 +110% at 20 sessions, TTMI 04-30, STRL 05-05 +31.6%, EVER, AIP, GO,
-- PONY, CORT, AEVA, ATRO, HTFL) but capture 1's Q1 shows the bucket at n=4 mature with NO tail — STRL and
-- BAND have left the bucket (re-categorised? traded-CTE exclusion via mi_paper_trades? setup_at_open false?).
-- Every row that ever carried the reason, whatever its category/flag today, so the 13 → 4 can be reconciled.
SELECT m.ticker, m.alert_date, m.source, m.skip_category, m.skip_reason, m.setup_at_open, m.open_gap_pct,
       m.ret_5d, m.ret_20d, m.max_high_20d,
       EXISTS (SELECT 1 FROM mi_paper_trades p WHERE p.ticker = m.ticker AND p.alert_date = m.alert_date) AS in_paper_trades,
       (SELECT string_agg(lt.status || '/' || lt.account_mode, ',') FROM mi_live_trades lt
         WHERE lt.ticker = m.ticker AND lt.alert_date = m.alert_date) AS live_trade_rows
FROM mi_ep_missed_outcomes m
WHERE m.skip_reason ILIKE '%stop_too_wide%'
   OR (m.ticker, m.alert_date) IN (('BAND', DATE '2026-04-30'), ('STRL', DATE '2026-05-05'), ('WST', DATE '2026-04-23'),
                                   ('WKC', DATE '2026-04-24'), ('TTMI', DATE '2026-04-30'), ('EVER', DATE '2026-05-05'))
ORDER BY m.alert_date, m.ticker, m.source;
