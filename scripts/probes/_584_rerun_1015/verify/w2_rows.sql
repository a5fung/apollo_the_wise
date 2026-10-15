-- ADVERSARIAL VERIFY 2026-10-15 (read-only): per-row outcome fields derived IN SQL from raw mi_universe_floor_shadow + mi_daily_closes + mi_splits.
-- Independent of the gatherer's pandas/pure-python pipelines. Aggregated locally by w3_aggregate.py.
BEGIN READ ONLY;
COPY (
WITH cal AS (
  SELECT trade_date, (row_number() OVER (ORDER BY trade_date))::int ci
  FROM (SELECT DISTINCT trade_date FROM mi_daily_closes WHERE trade_date BETWEEN '2026-06-01' AND '2026-10-14') x
), s AS (
  SELECT s.scan_date, s.ticker, (s.failed_price_floor OR s.failed_volume_floor) rej,
         s.today_dollar_volume_at_open ao, s.minutes_since_open_at_open m_ao, s.gap_pct_at_open gap, s.today_price_at_open p_ao,
         c.ci ci0, c5.trade_date d5, c20.trade_date d20
  FROM mi_universe_floor_shadow s
  JOIN cal c ON c.trade_date = s.scan_date
  LEFT JOIN cal c5 ON c5.ci = c.ci + 5
  LEFT JOIN cal c20 ON c20.ci = c.ci + 20
  WHERE s.scan_date <= '2026-10-14'
)
SELECT s.scan_date, s.ticker, s.rej, s.ao, s.m_ao, s.gap, s.p_ao, s.d5, s.d20,
  b0.open_price d0_open, b0.high_price d0_high, b0.low_price d0_low, b0.close d0_close,
  adr.adr20, adr.n_pre, adr.n_pre_0720,
  f5.n_fwd5, f5.pk5, f5.pk5x, f5.c5, f5.maxq5, f5.minq5,
  f20.n_fwd20, f20.pk20, f20.pk20x, f20.c20, f20.maxq20, f20.minq20,
  sp.fac, sp.n_split_after_d0, sp.n_split_in_20
FROM s
LEFT JOIN mi_daily_closes b0 ON b0.ticker = s.ticker AND b0.trade_date = s.scan_date
LEFT JOIN LATERAL (
  SELECT avg((z.high_price - z.low_price) / NULLIF(z.close,0)) adr20, count(*) n_pre,
         count(*) FILTER (WHERE z.trade_date >= '2026-07-20') n_pre_0720
  FROM (SELECT d.trade_date, d.high_price, d.low_price, d.close FROM mi_daily_closes d
        WHERE d.ticker = s.ticker AND d.trade_date < s.scan_date AND d.trade_date >= '2026-06-01'
        ORDER BY d.trade_date DESC LIMIT 20) z) adr ON true
LEFT JOIN LATERAL (
  SELECT count(*) FILTER (WHERE w.trade_date > s.scan_date) n_fwd5, max(w.high_price) pk5,
         max(w.high_price) FILTER (WHERE w.trade_date > s.scan_date) pk5x,
         max(w.close) FILTER (WHERE w.trade_date = s.d5) c5, max(w.q) maxq5, min(w.q) minq5
  FROM (SELECT d.trade_date, d.high_price, d.close, d.close / NULLIF(lag(d.close) OVER (ORDER BY d.trade_date),0) q
        FROM mi_daily_closes d WHERE d.ticker = s.ticker AND d.trade_date BETWEEN s.scan_date AND COALESCE(s.d5, DATE '2026-10-14')) w) f5 ON true
LEFT JOIN LATERAL (
  SELECT count(*) FILTER (WHERE w.trade_date > s.scan_date) n_fwd20, max(w.high_price) pk20,
         max(w.high_price) FILTER (WHERE w.trade_date > s.scan_date) pk20x,
         max(w.close) FILTER (WHERE w.trade_date = s.d20) c20, max(w.q) maxq20, min(w.q) minq20
  FROM (SELECT d.trade_date, d.high_price, d.close, d.close / NULLIF(lag(d.close) OVER (ORDER BY d.trade_date),0) q
        FROM mi_daily_closes d WHERE d.ticker = s.ticker AND d.trade_date BETWEEN s.scan_date AND COALESCE(s.d20, DATE '2026-10-14')) w) f20 ON true
LEFT JOIN LATERAL (
  SELECT exp(COALESCE(sum(ln(sp.split_to::float8 / sp.split_from)),0)) fac, count(*) n_split_after_d0,
         count(*) FILTER (WHERE sp.execution_date <= COALESCE(s.d20, DATE '2026-10-14')) n_split_in_20
  FROM mi_splits sp WHERE sp.ticker = s.ticker AND sp.execution_date > s.scan_date AND sp.adjustment_applied) sp ON true
ORDER BY s.scan_date, s.ticker
) TO STDOUT WITH CSV HEADER;
ROLLBACK;
