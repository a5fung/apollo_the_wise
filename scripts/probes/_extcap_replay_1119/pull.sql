SET default_transaction_read_only = on;
\echo === POP ===
WITH x AS (
  SELECT DISTINCT scan_date, ticker,
    NULLIF(regexp_replace(filter_reason,'^already up ([0-9.]+)%.*$','\1'),filter_reason)::numeric AS pct
  FROM mi_ep_scan_log WHERE filter_reason ILIKE '%(extended)%' AND scan_date >= DATE '2026-08-23' AND scan_date < CURRENT_DATE - 5)
SELECT * FROM x WHERE pct >= 50 ORDER BY scan_date, ticker;
\echo === SCAN ===
SELECT s.* FROM mi_ep_scan_log s JOIN (SELECT DISTINCT scan_date, ticker FROM mi_ep_scan_log WHERE filter_reason ILIKE '%(extended)%' AND scan_date >= DATE '2026-08-23' AND scan_date < CURRENT_DATE - 5) p USING (scan_date, ticker) ORDER BY s.scan_date, s.ticker;
\echo === MIN ===
SELECT b.ticker, to_char(b.bar_time AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') AS et_min, b.open, b.high, b.low, b.close, b.volume
FROM (SELECT DISTINCT scan_date, ticker FROM mi_ep_scan_log WHERE filter_reason ILIKE '%(extended)%' AND scan_date >= DATE '2026-08-23' AND scan_date < CURRENT_DATE - 5) p
JOIN mi_intraday_bars b ON b.ticker=p.ticker AND b.bar_time >= ((p.scan_date + time '09:30') AT TIME ZONE 'America/New_York') AND b.bar_time < ((p.scan_date + time '16:00') AT TIME ZONE 'America/New_York')
ORDER BY 1,2;
\echo === DAILY ===
SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close, d.volume FROM mi_daily_closes d
WHERE d.trade_date >= '2026-07-01' AND d.ticker IN (SELECT DISTINCT ticker FROM mi_ep_scan_log WHERE filter_reason ILIKE '%(extended)%' AND scan_date >= DATE '2026-08-23')
ORDER BY 1,2;
