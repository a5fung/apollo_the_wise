\set QUIET on
\pset format unaligned
\pset fieldsep '|'
\pset footer off
\pset null ''
-- V4_row (fixed): market-calendar per-row recount; flags any ticker missing a session inside its 6-session window
WITH cal AS (SELECT trade_date, row_number() OVER (ORDER BY trade_date) AS cn FROM (SELECT trade_date FROM mi_daily_closes WHERE trade_date >= DATE '2026-08-14' GROUP BY trade_date HAVING count(*) > 5000) q),
s AS (SELECT ticker, alert_date, adr20_frac, composite_rank_eod r_eod, pool_size_eod p_eod, composite_rank_asof0945 r_0945 FROM mi_alert_rank_shadow WHERE alert_date > DATE '2026-08-16'),
w AS (SELECT s.*, c0.cn AS cn0, (SELECT max(cn) FROM cal) - c0.cn + 1 AS cal_sess FROM s JOIN cal c0 ON c0.trade_date = s.alert_date),
j AS (SELECT w.ticker AS tk, w.alert_date AS ad, cal.cn - w.cn0 + 1 AS k, cal.trade_date, d.open_price, d.high_price, d.low_price
      FROM w JOIN cal ON cal.cn BETWEEN w.cn0 AND w.cn0 + 20 LEFT JOIN mi_daily_closes d ON d.ticker = w.ticker AND d.trade_date = cal.trade_date),
g AS (SELECT tk, ad,
        max(open_price) FILTER (WHERE k = 1) o0, max(low_price) FILTER (WHERE k = 1) l0,
        max(high_price) FILTER (WHERE k <= 6) h6, min(low_price) FILTER (WHERE k BETWEEN 2 AND 6) ln5,
        max(trade_date) FILTER (WHERE k = 6) d6,
        count(*) FILTER (WHERE k <= 6 AND open_price IS NULL) miss6
      FROM j GROUP BY 1, 2),
x AS (SELECT w.ticker, w.alert_date, w.cal_sess, w.r_eod, w.p_eod, w.r_0945, g.miss6, g.d6, g.h6, g.ln5, g.l0,
        (g.h6 - g.o0) / g.o0 / w.adr20_frac AS x5, g.ln5 < g.l0 AS broke FROM w JOIN g ON g.tk = w.ticker AND g.ad = w.alert_date)
SELECT 'V4_row' AS chk, ticker, alert_date, cal_sess, d6, miss6, round(x5::numeric, 2) x5, h6, ln5, l0, broke, round(r_eod::numeric, 4) r_eod, p_eod, round(r_0945::numeric, 4) r_0945
FROM x WHERE (cal_sess >= 6 AND (r_eod <= 0.25 OR r_0945 <= 0.2500001 OR x5 >= 8 OR miss6 > 0)) OR ticker IN ('PENG','VST','MRNA','KOD','BSP','WOLF','AAOI','HUM') ORDER BY alert_date, ticker;
