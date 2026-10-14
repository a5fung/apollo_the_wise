\set QUIET on
\pset format unaligned
\pset fieldsep '|'
\pset footer off
\pset null ''
-- V1. BSP provenance: is it a real live alert (not a #687 test / rehearsal row)?
SELECT 'V1_bsp_alert' AS chk, id, ticker, alert_date, source, score_tier, ep_score, round(gap_pct::numeric,2) gap, round(rel_volume::numeric,1) rvol,
  left(coalesce(catalyst,''),70) catalyst, created_at AT TIME ZONE 'America/New_York' AS created_et, detected_at AT TIME ZONE 'America/New_York' AS detected_et, fire_status
FROM mi_ep_alerts WHERE alert_date = DATE '2026-10-14' ORDER BY id;
SELECT 'V1_bsp_shadow' AS chk, alert_id, ticker, alert_date, account_mode, trade_exists, trade_filled, qualifies_for_rank_eod, composite_rank_eod, pool_size_eod,
  composite_rank_asof0945, pool_size_asof0945, day_bar_source, computed_at AT TIME ZONE 'America/New_York' AS computed_et
FROM mi_alert_rank_shadow WHERE alert_date = DATE '2026-10-14';
-- V2. every OOS shadow row's alert_id resolves to a LIVE mi_ep_alerts row with the same ticker/date
SELECT 'V2_alert_id_join' AS chk, count(*) shadow_rows,
  count(*) FILTER (WHERE a.id IS NOT NULL) id_resolves,
  count(*) FILTER (WHERE a.source = 'live' AND a.ticker = s.ticker AND a.alert_date = s.alert_date) id_live_same_key,
  count(DISTINCT s.alert_date) sessions, min(s.alert_date) first_d, max(s.alert_date) last_d
FROM mi_alert_rank_shadow s LEFT JOIN mi_ep_alerts a ON a.id = s.alert_id WHERE s.alert_date > DATE '2026-08-16';
SELECT 'V2_sources_oos' AS chk, source, count(*), count(DISTINCT alert_date) FROM mi_ep_alerts WHERE alert_date > DATE '2026-08-16' GROUP BY source ORDER BY source;
-- V3. rank job run on 10-14
SELECT 'V3_job' AS chk, job_id, status, scheduled_for AT TIME ZONE 'America/New_York' sched_et, started_at AT TIME ZONE 'America/New_York' start_et, finished_at AT TIME ZONE 'America/New_York' fin_et, duration_s, coalesce(error_message,'') err
FROM mi_job_runs WHERE job_id = 'alert_rank_shadow' AND started_at >= TIMESTAMPTZ '2026-10-14 00:00-04' ORDER BY id;
-- V4. market-calendar recount: sessions = universe trade_dates with >5000 rows (not the ticker's own rows),
--     window = first 6 calendar sessions from the EP day; flag any ticker missing a session inside its window.
WITH cal AS (SELECT trade_date, row_number() OVER (ORDER BY trade_date) AS cn FROM (SELECT trade_date FROM mi_daily_closes WHERE trade_date >= DATE '2026-08-14' GROUP BY trade_date HAVING count(*) > 5000) q),
s AS (SELECT ticker, alert_date, adr20_frac, composite_rank_eod r_eod, pool_size_eod p_eod, composite_rank_asof0945 r_0945 FROM mi_alert_rank_shadow WHERE alert_date > DATE '2026-08-16'),
w AS (SELECT s.*, c0.cn AS cn0, (SELECT max(cn) FROM cal) - c0.cn + 1 AS cal_sess FROM s JOIN cal c0 ON c0.trade_date = s.alert_date),
j AS (SELECT w.ticker, w.alert_date, cal.cn - w.cn0 + 1 AS k, d.open_price, d.high_price, d.low_price
      FROM w JOIN cal ON cal.cn BETWEEN w.cn0 AND w.cn0 + 20 LEFT JOIN mi_daily_closes d ON d.ticker = w.ticker AND d.trade_date = cal.trade_date),
g AS (SELECT ticker, alert_date,
        max(open_price) FILTER (WHERE k = 1) o0, max(low_price) FILTER (WHERE k = 1) l0,
        max(high_price) FILTER (WHERE k <= 6) h6, min(low_price) FILTER (WHERE k BETWEEN 2 AND 6) ln5,
        max(high_price) FILTER (WHERE k <= 21) h21,
        count(*) FILTER (WHERE k <= 6 AND open_price IS NULL) miss6,
        count(*) FILTER (WHERE k <= 21 AND open_price IS NULL) miss21
      FROM j GROUP BY 1, 2),
x AS (SELECT w.*, g.*, (g.h6 - g.o0) / g.o0 / w.adr20_frac AS x5, (g.h21 - g.o0) / g.o0 / w.adr20_frac AS x20, g.ln5 < g.l0 AS broke FROM w JOIN g USING (ticker, alert_date))
SELECT 'V4_row' AS chk, ticker, alert_date, cal_sess, miss6, miss21, round(x5::numeric, 2) x5, broke, round(r_eod::numeric, 4) r_eod, p_eod, round(r_0945::numeric, 4) r_0945
FROM x WHERE cal_sess >= 6 AND (r_eod <= 0.25 OR x5 >= 8 OR miss6 > 0 OR ticker IN ('PENG','VST','MRNA','KOD')) ORDER BY alert_date, ticker;
WITH cal AS (SELECT trade_date, row_number() OVER (ORDER BY trade_date) AS cn FROM (SELECT trade_date FROM mi_daily_closes WHERE trade_date >= DATE '2026-08-14' GROUP BY trade_date HAVING count(*) > 5000) q),
s AS (SELECT ticker, alert_date, adr20_frac, composite_rank_eod r_eod, pool_size_eod p_eod, composite_rank_asof0945 r_0945 FROM mi_alert_rank_shadow WHERE alert_date > DATE '2026-08-16'),
w AS (SELECT s.*, c0.cn AS cn0, (SELECT max(cn) FROM cal) - c0.cn + 1 AS cal_sess FROM s JOIN cal c0 ON c0.trade_date = s.alert_date),
j AS (SELECT w.ticker, w.alert_date, cal.cn - w.cn0 + 1 AS k, d.open_price, d.high_price, d.low_price
      FROM w JOIN cal ON cal.cn BETWEEN w.cn0 AND w.cn0 + 20 LEFT JOIN mi_daily_closes d ON d.ticker = w.ticker AND d.trade_date = cal.trade_date),
g AS (SELECT ticker, alert_date, max(open_price) FILTER (WHERE k = 1) o0, max(low_price) FILTER (WHERE k = 1) l0,
        max(high_price) FILTER (WHERE k <= 6) h6, min(low_price) FILTER (WHERE k BETWEEN 2 AND 6) ln5, max(high_price) FILTER (WHERE k <= 21) h21 FROM j GROUP BY 1, 2),
x AS (SELECT w.*, (g.h6 - g.o0) / g.o0 / w.adr20_frac AS x5, (g.h21 - g.o0) / g.o0 / w.adr20_frac AS x20, g.ln5 < g.l0 AS broke FROM w JOIN g USING (ticker, alert_date))
SELECT 'V4_cells' AS chk, rk, cell,
  count(*) FILTER (WHERE cal_sess >= 6) matured5, count(*) FILTER (WHERE cal_sess >= 6 AND x5 >= 8) hit8x_5d, count(*) FILTER (WHERE cal_sess >= 6 AND broke) broke_low,
  count(*) FILTER (WHERE cal_sess >= 6 AND p_eod >= 2) matured5_pool2plus,
  count(*) FILTER (WHERE cal_sess >= 21) matured20, count(*) FILTER (WHERE cal_sess >= 21 AND x20 >= 8) hit8x_20d
FROM (SELECT x.*, 'EOD' rk, CASE WHEN r_eod <= 0.25 THEN 'top' ELSE 'rest' END cell FROM x
      UNION ALL SELECT x.*, '0945', CASE WHEN r_0945 <= 0.25 THEN 'top' ELSE 'rest' END FROM x) u
GROUP BY rk, cell ORDER BY rk, cell DESC;
-- V5. session pool sizes (single-alert days)
SELECT 'V5_pools' AS chk, count(*) sessions, count(*) FILTER (WHERE n = 1) single_alert, count(*) FILTER (WHERE n >= 2) multi_alert
FROM (SELECT alert_date, count(*) n FROM mi_alert_rank_shadow WHERE alert_date > DATE '2026-08-16' GROUP BY alert_date) z;
