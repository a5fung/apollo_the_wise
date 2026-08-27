-- Silent-days verification, capture 2 (2026-08-25) — READ-ONLY, one run.
-- (a) the UPSTREAM names that never reached mi_ep_scan_log (real-time declines / shadow catches)
-- (b) the 26 must-not-miss fixture EPs, so the rejected names can be compared against a
--     re-derived liquidity/volatility profile of what a REAL EP looks like in OUR OWN data.
-- Run: ssh apollo@... "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|~|' -P pager=off" \
--        < scripts/probes/_silentdays_capture2.sql > scripts/probes/_silentdays_capture2_out.txt

\echo ===U1_UPSTREAM_CLOSES===
SELECT trade_date, ticker, open_price, high_price, low_price, close, volume
FROM mi_daily_closes
WHERE ticker IN ('CLF','RUM','USDE','NXTT','SUJA','WBTN','NCTY','HMN','ABCL','PSQH','CRML',
                 'PHOS','DBGI','PTHS','FISI','CLRO','SUPX')
  AND trade_date >= '2026-06-01'
ORDER BY ticker, trade_date;

\echo ===U2_UPSTREAM_SCANLOG_ANY===
SELECT scan_date, ticker, count(*) ticks,
       max(gap_pct) max_gap,
       replace(string_agg(DISTINCT coalesce(filter_reason,'<none>'),' ;; '),'|~|','/') reasons
FROM mi_ep_scan_log
WHERE ticker IN ('CLF','RUM','USDE','NXTT','SUJA','WBTN','NCTY','HMN','ABCL','PSQH','CRML',
                 'PHOS','DBGI','PTHS','FISI','CLRO')
  AND scan_date >= '2026-08-01'
GROUP BY 1,2 ORDER BY 1,2;

\echo ===U3_UPSTREAM_ALERTS===
SELECT alert_date, ticker, gap_pct, ep_score, score_tier, catalyst_quality, coalesce(source,'live') src
FROM mi_ep_alerts
WHERE ticker IN ('CLF','RUM','USDE','NXTT','SUJA','WBTN','NCTY','HMN','ABCL','PSQH','CRML','MAIR',
                 'NBBK','NSSC','SCTX','APMD','AERO','CAPR','OESX','WAFD','MEI','IMTX','GRML','DFNS',
                 'AMIX','SDOT','HVII','SUPX','JLHL','BBCQ','DTIL','SPAI','PMI','REAX','FLNC','KURA')
  AND alert_date >= '2026-01-01'
ORDER BY ticker, alert_date;

\echo ===F1_FIXTURE_CLOSES===
SELECT trade_date, ticker, open_price, high_price, low_price, close, volume
FROM mi_daily_closes
WHERE ticker IN ('MRNA','MU','UMC','STRL','MRVL','ASX','SNDK','SNOW','ALGM','NBIS','AMKR','AEHR',
                 'FLY','BE','USAR','QCOM','QBTS','AMD','HUT','QURE','ARM','SMTC','IREN','APLD','INTC')
  AND trade_date >= '2026-01-15'
ORDER BY ticker, trade_date;

\echo ===F2_FIXTURE_SCANLOG===
SELECT scan_date, ticker, gap_pct, prev_close, adv, ep_score, score_tier, catalyst_quality,
       replace(coalesce(filter_reason,'<none>'),'|~|','/') filter_reason
FROM mi_ep_scan_log
WHERE (ticker,scan_date) IN (
  ('MRNA','2026-08-19'),('MU','2026-04-08'),('UMC','2026-04-17'),('STRL','2026-04-08'),
  ('MRVL','2026-03-31'),('ASX','2026-04-08'),('SNDK','2026-04-08'),('SNOW','2026-05-07'),
  ('ALGM','2026-04-08'),('NBIS','2026-04-08'),('AMKR','2026-04-08'),('AEHR','2026-03-31'),
  ('UMC','2026-05-06'),('FLY','2026-03-12'),('BE','2026-04-08'),('USAR','2026-04-08'),
  ('QCOM','2026-04-24'),('QBTS','2026-04-08'),('AMD','2026-04-24'),('HUT','2026-04-08'),
  ('QURE','2026-05-29'),('ARM','2026-05-06'),('SMTC','2026-03-30'),('IREN','2026-04-08'),
  ('APLD','2026-04-08'),('INTC','2026-04-24'))
ORDER BY ticker, scan_date;

\echo ===M1_MCAP_CACHE_SOURCE===
-- anything persisted about market cap for the rejected names
SELECT * FROM mi_ticker_overrides
WHERE ticker IN ('CAPR','DTIL','SUPX','BBCQ','OESX','MAIR','NBBK','NSSC','SCTX','CLF','HMN')
LIMIT 100;
