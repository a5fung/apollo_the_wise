-- #562/#327 theoretical-day1 card — ONE read-only prod capture (2026-09-01). Never re-run to re-read.
-- Run: ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -X -q" < _562td_capture.sql > _562td_capture_out.txt
\echo ===SECTION_SCHEMA===
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_ep_alerts' ORDER BY ordinal_position;
\echo ===SECTION_ALERTTIMES===
SELECT ticker, alert_date, score_tier,
       to_char(detected_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS detected_et,
       to_char(created_at  AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS created_et
FROM mi_ep_alerts
WHERE COALESCE(source,'live')='live' AND alert_date BETWEEN '2026-05-01' AND '2026-08-31'
ORDER BY alert_date, ticker;
\echo ===SECTION_MINUTES===
WITH p(ticker, d) AS (VALUES ('ABSI','2026-06-24'::date),('ACAD','2026-06-26'::date),('AEHR','2026-07-15'::date),('AGX','2026-06-05'::date),('ALAB','2026-05-20'::date),('ARM','2026-05-20'::date),('ARWR','2026-07-22'::date),('AVAV','2026-05-28'::date),('AVAV','2026-06-30'::date),('CLSK','2026-07-14'::date),('CRSR','2026-05-27'::date),('DELL','2026-05-29'::date),('DFTX','2026-06-22'::date),('DOCN','2026-07-07'::date),('DY','2026-05-27'::date),('DYN','2026-05-20'::date),('ELVN','2026-06-11'::date),('FCEL','2026-06-24'::date),('GH','2026-05-20'::date),('GRRR','2026-06-02'::date),('HPE','2026-06-02'::date),('JBL','2026-06-17'::date),('MLTX','2026-06-22'::date),('MRNA','2026-08-19'::date),('MRVL','2026-06-02'::date),('MU','2026-06-25'::date),('NAVN','2026-06-11'::date),('NRIX','2026-06-08'::date),('NVTS','2026-06-03'::date),('QURE','2026-06-17'::date),('RCAT','2026-05-28'::date),('RDW','2026-08-06'::date),('RUM','2026-06-04'::date),('RXT','2026-06-16'::date),('SHAZ','2026-06-12'::date),('SNX','2026-06-25'::date),('SWBI','2026-06-18'::date),('SYRE','2026-06-22'::date),('TER','2026-07-29'::date),('TTAN','2026-06-05'::date),('UUUU','2026-06-18'::date),('VPG','2026-05-12'::date))
SELECT b.ticker,
       to_char(b.bar_time AT TIME ZONE 'America/New_York','YYYY-MM-DD') AS d,
       to_char(b.bar_time AT TIME ZONE 'America/New_York','HH24:MI') AS bar_et,
       b.open, b.high, b.low, b.close, b.volume
FROM mi_intraday_bars b JOIN p ON b.ticker=p.ticker
  AND (b.bar_time AT TIME ZONE 'America/New_York')::date = p.d
WHERE (b.bar_time AT TIME ZONE 'America/New_York')::time >= TIME '09:30'
  AND (b.bar_time AT TIME ZONE 'America/New_York')::time < TIME '16:00'
ORDER BY b.ticker, b.bar_time;
