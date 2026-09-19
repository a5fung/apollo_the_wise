-- #299 — the three READ-ONLY prod captures behind scripts/probes/_299_tape_free_features.py.
-- Captured ONCE on 2026-09-19 (CAPTURE ONCE, READ MANY). Run each COPY block on its own:
--   ssh apollo@87.99.134.162 'docker exec -i apollo-postgres psql -U apollo -d apollo -q' < block.sql > /tmp/299_<name>.csv

-- ===== block 1 -> /tmp/299_high.csv =====
-- Every score_tier='HIGH' row of mi_ep_alerts (the probe keeps the FIRST row per ticker-day),
-- joined to its 09:30-09:34 opening range, the scan tick's liquidity fields and settled outcomes.
COPY (
SELECT a.id, a.ticker, a.alert_date, to_char(a.detected_at AT TIME ZONE 'America/New_York','HH24:MI') AS det_et,
       a.gap_pct, a.rel_volume, a.pm_rvol, a.pm_rvol_baseline_n, a.vol_percentile, a.ep_score, a.score_tier, a.baseline_floor_tier, a.judge_tier, a.judge_direction,
       a.grade_engine_authority, a.judge_grade, a.catalyst_type, a.setup_class,
       a.tape_tier, a.tape_spike_ct, a.tape_held, a.tape_rev, a.tape_bmr2, a.tape_ntr_med,
       a.vol_hist_n, a.vol_r5_50, a.vol_lab50, a.vol_lab50_ratio, a.vol_alert_vs_max,
       o.or_high, o.or_low, o.or_vol, o.or_bars,
       s.today_volume AS tick_today_volume, s.current_price AS tick_price, s.adv AS tick_adv, s.quality_adv_dollar AS tick_adv_dollar, s.market_cap AS tick_mcap, s.atr_pct AS tick_atr_pct,
       so.fwd_1d_pct, so.fwd_1w_pct, so.fwd_1m_pct, so.fwd_3m_pct
FROM mi_ep_alerts a
LEFT JOIN LATERAL (
  SELECT max(high) AS or_high, min(low) AS or_low, sum(volume) AS or_vol, count(*) AS or_bars
  FROM mi_intraday_bars ib WHERE ib.ticker = a.ticker
    AND (ib.bar_time AT TIME ZONE 'America/New_York')::date = a.alert_date
    AND (ib.bar_time AT TIME ZONE 'America/New_York')::time >= '09:30' AND (ib.bar_time AT TIME ZONE 'America/New_York')::time < '09:35'
) o ON true
LEFT JOIN LATERAL (
  SELECT today_volume, current_price, adv, quality_adv_dollar, market_cap, atr_pct
  FROM mi_ep_scan_log sl WHERE sl.ticker = a.ticker AND sl.scan_date = a.alert_date AND sl.scan_time_et <= a.detected_at + interval '1 minute'
  ORDER BY sl.scan_time_et DESC LIMIT 1
) s ON true
LEFT JOIN mi_signal_outcomes so ON so.signal_type = 'ep_alert' AND so.signal_date = a.alert_date AND so.identifier = a.ticker
WHERE a.score_tier = 'HIGH'
ORDER BY a.alert_date, a.ticker
) TO STDOUT WITH CSV HEADER;

-- ===== block 2 -> /tmp/299_daily.csv =====
-- Daily OHLC for the ATR-14 reference (strictly prior sessions are selected in the probe).
COPY (
SELECT d.trade_date, d.ticker, d.high_price, d.low_price, d.close
FROM mi_daily_closes d
WHERE d.ticker IN (SELECT DISTINCT ticker FROM mi_ep_alerts WHERE score_tier='HIGH' UNION SELECT unnest(ARRAY['BFLY','ABNB','CHPT']))
  AND d.trade_date >= '2026-03-01'
ORDER BY d.ticker, d.trade_date
) TO STDOUT WITH CSV HEADER;

-- ===== block 3 -> /tmp/299_bar1.csv =====
-- The 09:30 one-minute bar per alert day — the ORB bar the live entry (and stop_too_wide) uses.
COPY (
SELECT ib.ticker, (ib.bar_time AT TIME ZONE 'America/New_York')::date AS d, ib.high AS b1_high, ib.low AS b1_low, ib.volume AS b1_vol
FROM mi_intraday_bars ib
JOIN (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts WHERE score_tier='HIGH'
      UNION SELECT 'BFLY','2026-06-18'::date UNION SELECT 'ABNB','2026-08-07'::date UNION SELECT 'CHPT','2026-09-03'::date) a
  ON a.ticker = ib.ticker AND (ib.bar_time AT TIME ZONE 'America/New_York')::date = a.alert_date
WHERE (ib.bar_time AT TIME ZONE 'America/New_York')::time = '09:30'
ORDER BY 1,2
) TO STDOUT WITH CSV HEADER;

-- The opening ranges of the three labelled EPs that never became alerts (BFLY 06-18, ABNB 08-07,
-- CHPT 09-03) are hard-coded in the probe from block-3-style reads of mi_intraday_bars.
