\set QUIET on
\pset format unaligned
\pset fieldsep '|'
\pset footer off
\pset null ''
-- R1. independent recount on the MARKET CALENDAR (universe days with >5000 rows), not each ticker's own rows.
--     k = calendar session number from the EP day (EP day = 1). 5-day window = k<=6; 20-day window = k<=21.
CREATE TEMP TABLE rr AS
WITH cal AS (SELECT trade_date, row_number() OVER (ORDER BY trade_date) AS cn FROM (SELECT trade_date FROM mi_daily_closes WHERE trade_date >= DATE '2026-08-14' GROUP BY trade_date HAVING count(*) > 5000) q),
s AS (SELECT ticker, alert_date, trade_filled, adr20_frac, composite_rank_eod r_eod, pool_size_eod p_eod, composite_rank_asof0945 r_0945, pool_size_asof0945 p_0945 FROM mi_alert_rank_shadow WHERE alert_date > DATE '2026-08-16'),
w AS (SELECT s.*, c0.cn AS cn0, (SELECT max(cn) FROM cal) - c0.cn + 1 AS cal_sess FROM s JOIN cal c0 ON c0.trade_date = s.alert_date),
j AS (SELECT w.ticker AS tk, w.alert_date AS ad, cal.cn - w.cn0 + 1 AS k, cal.trade_date, d.open_price, d.high_price, d.low_price
      FROM w JOIN cal ON cal.cn BETWEEN w.cn0 AND w.cn0 + 20 LEFT JOIN mi_daily_closes d ON d.ticker = w.ticker AND d.trade_date = cal.trade_date),
g AS (SELECT tk, ad,
        max(open_price) FILTER (WHERE k = 1) o0, max(low_price) FILTER (WHERE k = 1) l0,
        max(high_price) FILTER (WHERE k <= 6) h6, min(low_price) FILTER (WHERE k BETWEEN 2 AND 6) ln5,
        max(high_price) FILTER (WHERE k <= 21) h21,
        count(*) FILTER (WHERE k <= 6 AND open_price IS NULL) miss6,
        count(*) FILTER (WHERE k <= 21 AND open_price IS NULL) miss21
      FROM j GROUP BY 1, 2)
SELECT w.ticker, w.alert_date, w.trade_filled, w.cal_sess, w.r_eod, w.p_eod, w.r_0945, w.p_0945, g.miss6, g.miss21,
       (g.h6 - g.o0) / g.o0 / w.adr20_frac AS x5, (g.h21 - g.o0) / g.o0 / w.adr20_frac AS x20, g.ln5 < g.l0 AS broke
FROM w JOIN g ON g.tk = w.ticker AND g.ad = w.alert_date;
SELECT 'R1_totals' AS chk, count(*) AS rows, count(DISTINCT alert_date) AS sessions, max(alert_date) AS latest, count(*) FILTER (WHERE trade_filled) AS filled, count(*) FILTER (WHERE cal_sess >= 6) AS mat5, count(*) FILTER (WHERE cal_sess >= 21) AS mat20, count(*) FILTER (WHERE miss6 > 0 AND cal_sess >= 6) AS gap_in_5d_window, count(*) FILTER (WHERE miss21 > 0 AND cal_sess >= 21) AS gap_in_20d_window FROM rr;
SELECT 'R2_cells' AS chk, rk, cell,
  count(*) FILTER (WHERE cal_sess >= 6) AS mat5, count(*) FILTER (WHERE cal_sess >= 6 AND x5 >= 8) AS hit5, count(*) FILTER (WHERE cal_sess >= 6 AND broke) AS broke_low,
  count(*) FILTER (WHERE cal_sess >= 21) AS mat20, count(*) FILTER (WHERE cal_sess >= 21 AND x20 >= 8) AS hit20,
  string_agg(ticker, ',' ORDER BY alert_date) FILTER (WHERE cal_sess >= 21 AND x20 >= 8) AS hit20_names
FROM (SELECT rr.*, 'EOD' rk, CASE WHEN r_eod <= 0.25 THEN 'top' ELSE 'rest' END cell FROM rr
      UNION ALL SELECT rr.*, '0945', CASE WHEN r_0945 <= 0.25 THEN 'top' ELSE 'rest' END FROM rr
      UNION ALL SELECT rr.*, '0945_tol', CASE WHEN r_0945 <= 0.25 + 1e-9 THEN 'top' ELSE 'rest' END FROM rr) u
GROUP BY rk, cell ORDER BY rk, cell DESC;
SELECT 'R3_rows' AS chk, ticker, alert_date, cal_sess, miss6, round(x5::numeric,2) x5, round(x20::numeric,2) x20, broke, round(r_eod::numeric,4) r_eod, p_eod, round(r_0945::numeric,4) r_0945, trade_filled
FROM rr WHERE ticker IN ('WOLF','AAOI','HUM','BSP','VICR','GNRC','MRNA','KOD','CIFR','PENG') OR x5 >= 8 OR x20 >= 8 OR r_eod <= 0.25 ORDER BY alert_date, ticker;
SELECT 'R4_today_maturity' AS chk, ticker, alert_date, cal_sess FROM rr WHERE cal_sess IN (6, 21) ORDER BY cal_sess, ticker;
SELECT 'R5_pools' AS chk, count(DISTINCT alert_date) AS sessions, count(DISTINCT alert_date) FILTER (WHERE p_eod = 1) AS single_sessions, count(*) FILTER (WHERE cal_sess >= 6 AND p_eod >= 2) AS mat5_pool2plus, count(*) FILTER (WHERE cal_sess >= 6 AND r_eod <= 0.25) AS mat5_top, count(*) FILTER (WHERE cal_sess >= 6) AS mat5 FROM rr;
-- R6. why no alert on 10-15: what the admitted names did downstream
SELECT 'R6_audit_mentions' AS chk, created_at AT TIME ZONE 'America/New_York' AS at_et, event_type, left(summary,170) AS summary FROM mi_audit_log WHERE created_at >= TIMESTAMPTZ '2026-10-15 00:00-04' AND created_at < TIMESTAMPTZ '2026-10-15 16:00-04' AND (summary ~ '\m(ERIC|OPI|NRXS|NTWK|FMFC|BETR)\M') AND event_type NOT IN ('ep_rt_admit','ep_rt_universe_coverage','ep_rt_floor_flip_up','ep_rt_floor_flip_down') ORDER BY created_at LIMIT 40;
SELECT 'R7_missed_1015' AS chk, ticker, alert_date, source FROM mi_ep_missed_outcomes WHERE alert_date >= DATE '2026-10-15' ORDER BY ticker LIMIT 20;
