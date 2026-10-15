-- #584 10-15 VERIFIER: per-row outcomes computed ENTIRELY in SQL (no pandas, no reader code).
-- Rows: rejected-side in-window (at_open read <= 15 min) with at_open $vol >= $10M, plus admitted-side in-window with gap_at_open >= 10.
-- Per row, for H in (5, 20): D0 open/close, ADR = mean (H-L)/C over the ticker's 20 most recent bars before D0 (and how many exist),
-- n forward bars D1..DH, close at DH, peak high D0..DH (incl gap day) and D1..DH (ex gap day), max close-to-close ratio D0..DH (the >4x guard).
BEGIN READ ONLY;
COPY (
WITH cal AS (
  SELECT trade_date, (row_number() OVER (ORDER BY trade_date))::int rn
  FROM (SELECT DISTINCT trade_date FROM mi_daily_closes WHERE trade_date BETWEEN DATE '2026-07-01' AND DATE '2026-10-14') x),
s AS (
  SELECT scan_date, ticker, (failed_price_floor OR failed_volume_floor) AS rej,
         failed_price_floor fp, failed_volume_floor fv, gap_pct_at_open g, today_dollar_volume_at_open ao,
         minutes_since_open_at_open m, today_price_at_open p_ao, prev_close
  FROM mi_universe_floor_shadow
  WHERE scan_date <= DATE '2026-10-14' AND today_dollar_volume_at_open IS NOT NULL AND minutes_since_open_at_open <= 15
    AND ( ((failed_price_floor OR failed_volume_floor) AND today_dollar_volume_at_open >= 10000000)
       OR (NOT (failed_price_floor OR failed_volume_floor) AND gap_pct_at_open >= 10) ))
SELECT s.scan_date, s.ticker, s.rej, s.fp, s.fv, s.g, s.ao, s.m, s.p_ao, s.prev_close,
       d0.open_price o0, d0.high_price h0, d0.close c0,
       pre.adr, pre.npre,
       c5.trade_date d5, f5.nfwd nfwd5, f5.cH c5, f5.pk_in pk5_in, f5.pk_ex pk5_ex, f5.maxq maxq5,
       c20.trade_date d20, f20.nfwd nfwd20, f20.cH c20, f20.pk_in pk20_in, f20.pk_ex pk20_ex, f20.maxq maxq20
FROM s
JOIN cal c0 ON c0.trade_date = s.scan_date
LEFT JOIN cal c5  ON c5.rn  = c0.rn + 5
LEFT JOIN cal c20 ON c20.rn = c0.rn + 20
LEFT JOIN mi_daily_closes d0 ON d0.ticker = s.ticker AND d0.trade_date = s.scan_date
LEFT JOIN LATERAL (
  SELECT avg((z.high_price - z.low_price) / NULLIF(z.close, 0)) adr, count(*) npre
  FROM (SELECT high_price, low_price, close FROM mi_daily_closes p
        WHERE p.ticker = s.ticker AND p.trade_date < s.scan_date ORDER BY p.trade_date DESC LIMIT 20) z) pre ON true
LEFT JOIN LATERAL (
  SELECT count(*) FILTER (WHERE w.trade_date > s.scan_date) nfwd,
         max(w.close) FILTER (WHERE w.trade_date = c5.trade_date) cH,
         max(w.high_price) pk_in,
         max(w.high_price) FILTER (WHERE w.trade_date > s.scan_date) pk_ex,
         max(w.q) maxq
  FROM (SELECT d.trade_date, d.close, d.high_price, d.close / NULLIF(lag(d.close) OVER (ORDER BY d.trade_date), 0) q
        FROM mi_daily_closes d WHERE d.ticker = s.ticker AND d.trade_date BETWEEN s.scan_date AND c5.trade_date) w) f5 ON c5.trade_date IS NOT NULL
LEFT JOIN LATERAL (
  SELECT count(*) FILTER (WHERE w.trade_date > s.scan_date) nfwd,
         max(w.close) FILTER (WHERE w.trade_date = c20.trade_date) cH,
         max(w.high_price) pk_in,
         max(w.high_price) FILTER (WHERE w.trade_date > s.scan_date) pk_ex,
         max(w.q) maxq
  FROM (SELECT d.trade_date, d.close, d.high_price, d.close / NULLIF(lag(d.close) OVER (ORDER BY d.trade_date), 0) q
        FROM mi_daily_closes d WHERE d.ticker = s.ticker AND d.trade_date BETWEEN s.scan_date AND c20.trade_date) w) f20 ON c20.trade_date IS NOT NULL
ORDER BY s.scan_date, s.ticker
) TO STDOUT WITH CSV HEADER;
\echo === SPLITS touching any of these rows' windows (execution_date in D0-30d .. 10-15)
SELECT sp.ticker, sp.execution_date, sp.split_from, sp.split_to, sp.adjustment_applied
FROM mi_splits sp
WHERE sp.execution_date >= DATE '2026-08-01'
  AND sp.ticker IN (SELECT ticker FROM mi_universe_floor_shadow
                    WHERE scan_date <= DATE '2026-10-14' AND today_dollar_volume_at_open IS NOT NULL AND minutes_since_open_at_open <= 15
                      AND ( ((failed_price_floor OR failed_volume_floor) AND today_dollar_volume_at_open >= 50000000)
                         OR (NOT (failed_price_floor OR failed_volume_floor) AND gap_pct_at_open >= 10)))
ORDER BY 2, 1;
ROLLBACK;
