\set QUIET on
\pset format unaligned
\pset fieldsep '|'
\pset footer off
\pset null ''
-- A. schemas (test/rehearsal flags? date columns?)
SELECT 'A_schema' AS chk, table_name, string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name IN ('mi_alert_rank_shadow','mi_ep_alerts','mi_live_trades') GROUP BY table_name;
-- B. population: duplicates and live-alert backing
SELECT 'B_dupes' AS chk, ticker, alert_date, count(*) FROM mi_alert_rank_shadow WHERE alert_date > DATE '2026-08-16' GROUP BY 2,3 HAVING count(*)>1;
SELECT 'B_backing' AS chk, count(*) AS shadow_rows, count(DISTINCT s.alert_date) AS sessions,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM mi_ep_alerts a WHERE a.ticker=s.ticker AND a.alert_date=s.alert_date AND a.source='live')) AS with_live_alert
FROM mi_alert_rank_shadow s WHERE s.alert_date > DATE '2026-08-16';
SELECT 'B_live_alerts_oos' AS chk, count(*) AS live_alert_rows, count(DISTINCT alert_date) AS live_alert_days,
  count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM mi_alert_rank_shadow s WHERE s.ticker=a.ticker AND s.alert_date=a.alert_date)) AS live_alerts_without_shadow
FROM mi_ep_alerts a WHERE a.alert_date > DATE '2026-08-16' AND a.source='live';
SELECT 'B_alerts_any_source_1012_1013' AS chk, source, alert_date, count(*) FROM mi_ep_alerts WHERE alert_date >= DATE '2026-10-09' GROUP BY 2,3;
-- C. independent per-row outcome, sessions numbered from the EP day
WITH s AS (SELECT ticker,alert_date,adr20_frac,composite_rank_eod r_eod,pool_size_eod p_eod,composite_rank_asof0945 r_0945,pool_size_asof0945 p_0945 FROM mi_alert_rank_shadow WHERE alert_date > DATE '2026-08-16'),
d AS (SELECT s.ticker, s.alert_date, c.trade_date, c.open_price, c.high_price, c.low_price,
        row_number() OVER (PARTITION BY s.ticker, s.alert_date ORDER BY c.trade_date) AS k
      FROM s JOIN mi_daily_closes c ON c.ticker=s.ticker AND c.trade_date>=s.alert_date),
o AS (SELECT s.*, (SELECT count(*) FROM d WHERE d.ticker=s.ticker AND d.alert_date=s.alert_date) AS nsess,
        (SELECT open_price FROM d WHERE d.ticker=s.ticker AND d.alert_date=s.alert_date AND k=1 AND d.trade_date=s.alert_date) AS o0,
        (SELECT low_price FROM d WHERE d.ticker=s.ticker AND d.alert_date=s.alert_date AND k=1 AND d.trade_date=s.alert_date) AS l0,
        (SELECT max(high_price) FROM d WHERE d.ticker=s.ticker AND d.alert_date=s.alert_date AND k<=6) AS h6,
        (SELECT min(low_price) FROM d WHERE d.ticker=s.ticker AND d.alert_date=s.alert_date AND k BETWEEN 2 AND 6) AS lnext5
      FROM s),
x AS (SELECT o.*, (h6-o0)/o0/adr20_frac AS x5, (nsess>=6) AS mat, (lnext5<l0) AS broke FROM o)
SELECT 'C_row' AS chk, ticker, alert_date, nsess, round(x5::numeric,2) x5, broke, round(r_eod::numeric,4) r_eod, p_eod, round(r_0945::numeric,4) r_0945, p_0945 FROM x
WHERE alert_date >= DATE '2026-10-01' OR x5 >= 8 OR r_eod <= 0.2500001 OR r_0945 <= 0.2500001 ORDER BY alert_date, ticker;
WITH s AS (SELECT ticker,alert_date,adr20_frac,composite_rank_eod r_eod,composite_rank_asof0945 r_0945 FROM mi_alert_rank_shadow WHERE alert_date > DATE '2026-08-16'),
d AS (SELECT s.ticker, s.alert_date, c.trade_date, c.open_price, c.high_price, c.low_price,
        row_number() OVER (PARTITION BY s.ticker, s.alert_date ORDER BY c.trade_date) AS k
      FROM s JOIN mi_daily_closes c ON c.ticker=s.ticker AND c.trade_date>=s.alert_date),
g AS (SELECT ticker, alert_date, count(*) nsess,
        max(open_price) FILTER (WHERE k=1) o0, max(low_price) FILTER (WHERE k=1) l0,
        max(high_price) FILTER (WHERE k<=6) h6, min(low_price) FILTER (WHERE k BETWEEN 2 AND 6) ln5,
        max(high_price) FILTER (WHERE k<=21) h21
      FROM d GROUP BY 1,2),
x AS (SELECT s.*, g.nsess, (g.h6-g.o0)/g.o0/s.adr20_frac x5, (g.h21-g.o0)/g.o0/s.adr20_frac x20, g.ln5<g.l0 broke FROM s JOIN g USING (ticker, alert_date))
SELECT 'C_cells' AS chk, rk, cell,
  count(*) FILTER (WHERE nsess>=6) AS matured5,
  count(*) FILTER (WHERE nsess>=6 AND x5>=8) AS hit8x_5d,
  count(*) FILTER (WHERE nsess>=6 AND broke) AS broke_low,
  count(*) FILTER (WHERE nsess>=21) AS matured20,
  count(*) FILTER (WHERE nsess>=21 AND x20>=8) AS hit8x_20d
FROM (SELECT x.*, 'EOD' rk, CASE WHEN r_eod<=0.25 THEN 'top' ELSE 'rest' END cell FROM x
      UNION ALL SELECT x.*, '0945', CASE WHEN r_0945<=0.25 THEN 'top' ELSE 'rest' END FROM x
      UNION ALL SELECT x.*, '0945_tol', CASE WHEN r_0945<=0.25+1e-9 THEN 'top' ELSE 'rest' END FROM x) u
GROUP BY rk, cell ORDER BY rk, cell DESC;
SELECT 'C_totals' AS chk, count(*) rows, count(DISTINCT alert_date) sessions, max(alert_date) latest FROM mi_alert_rank_shadow WHERE alert_date > DATE '2026-08-16';
-- D. daily closes uniqueness for the shadow tickers
SELECT 'D_close_dupes' AS chk, count(*) FROM (SELECT c.ticker, c.trade_date FROM mi_daily_closes c WHERE c.trade_date >= DATE '2026-08-17' AND c.ticker IN (SELECT ticker FROM mi_alert_rank_shadow WHERE alert_date > DATE '2026-08-16') GROUP BY 1,2 HAVING count(*)>1) z;
-- F. what ep_rt_admit means on the quiet days
SELECT 'F_admit' AS chk, created_at AT TIME ZONE 'America/New_York' AS at_et, left(summary,160) FROM mi_audit_log WHERE event_type='ep_rt_admit' AND created_at >= TIMESTAMPTZ '2026-10-12 00:00-04' ORDER BY created_at LIMIT 8;
SELECT 'F_alert_events' AS chk, (created_at AT TIME ZONE 'America/New_York')::date d, event_type, count(*) FROM mi_audit_log WHERE created_at >= TIMESTAMPTZ '2026-10-05 00:00-04' AND (event_type ILIKE '%alert%' AND event_type ILIKE '%ep%') GROUP BY 2,3 ORDER BY 2,3;
