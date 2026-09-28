#!/bin/bash
# #684 — the ONE data pull (read-only, $0). Captured once; every later step reads these files.
# Population (gate.sql / gate_out.txt): every gap-day candidate the EP scan SCORED (ep_score NOT NULL)
# in mi_ep_scan_log, scan_date 2026-05-01 .. 2026-09-03 (the last scan date with >= 15 later sessions
# in mi_daily_closes), ONE row per (ticker, scan_date): prefer the tick that PASSED (filter_reason NULL
# and score_tier set), else the highest ep_score, ties -> latest scan_time_et.  670 rows / 546 names.
# Outputs:
#   pop.tsv      the 670 rows + every scan-log column + tick summary + the mi_ep_alerts join (live source)
#                + mi_alert_rank_shadow expectedness/base columns (alerted rows only) + catalyst metrics
#   hist.tsv     per row, server-side aggregates over the FULL mi_daily_closes history (2021-09 ->):
#                all-time high before the gap day, its date, history start, 52-week / 6-month highs
#   scores.tsv   per row, the latest mi_stock_scores row with score_date < scan_date (RS rank, sector, ADV)
#   themes.tsv   per row, the hottest non-Retired mi_themes snapshot containing the ticker as of scan_date-1
#                (unbounded, = get_theme_heat_asof) and the 7d-bounded variant (= live in_active_theme)
#   prior.tsv    per row, the ticker's previous scored scan-log date and previous live alert date
#   orb.tsv      per row, mi_intraday_bars aggregated 09:30-09:44 ET (open, high, low, close, volume, bars)
#                plus the day's bar count (coverage)
#   regime.tsv   mi_market_regime 2026-04-01 .. 2026-09-25
#   sector.tsv   mi_ticker_overrides sector/industry for the population tickers
#   daily.tsv.gz mi_daily_closes for the population tickers + SPY/QQQ/IWM, 2025-03-01 .. 2026-09-25 (gitignored)
set -euo pipefail
cd "$(dirname "$0")"
HOST="apollo@87.99.134.162"
PSQL='docker exec -i apollo-postgres psql -U apollo -d apollo -A -F "|" -v ON_ERROR_STOP=1'

POP="WITH sess AS (SELECT trade_date FROM mi_daily_closes GROUP BY trade_date HAVING count(*) >= 500),
last_ok AS (SELECT max(s.trade_date) AS d FROM sess s WHERE (SELECT count(*) FROM sess s2 WHERE s2.trade_date > s.trade_date) >= 15),
raw AS (SELECT l.* FROM mi_ep_scan_log l WHERE l.scan_date BETWEEN DATE '2026-05-01' AND (SELECT d FROM last_ok) AND l.ep_score IS NOT NULL),
ticks AS (SELECT ticker, scan_date, count(*) AS n_ticks, bool_or(filter_reason IS NULL AND score_tier IS NOT NULL) AS any_pass_tick,
          max(ep_score) AS max_score, min(ep_score) AS min_score,
          min(scan_time_et) FILTER (WHERE filter_reason IS NULL AND score_tier IS NOT NULL) AS first_pass_time,
          min(scan_time_et) AS first_tick_time, max(scan_time_et) AS last_tick_time
          FROM raw GROUP BY ticker, scan_date),
pop AS (SELECT DISTINCT ON (r.ticker, r.scan_date) r.* FROM raw r
        ORDER BY r.ticker, r.scan_date, (r.filter_reason IS NULL AND r.score_tier IS NOT NULL) DESC, r.ep_score DESC, r.scan_time_et DESC)"

run() { # name, select-sql
  echo "[$1]"
  ssh "$HOST" "$PSQL" <<< "$POP $2" > "$1"
  wc -l "$1"
}

run pop.tsv "SELECT p.ticker, p.scan_date, p.ep_score, p.score_tier, p.catalyst_quality, p.filter_reason, p.reject_stage, p.score_side,
  p.gap_pct, p.prev_close, p.current_price, p.rel_volume, p.pm_rvol, p.projected_vol_multiple, p.adv, p.adv_source, p.rank_by_gap, p.rank_by_prescore,
  p.minutes_since_open, to_char(p.scan_time_et AT TIME ZONE 'America/New_York','HH24:MI') AS scan_time, p.prev_day_volume, p.today_volume,
  p.days_since_prior_alert, p.extension_pct, p.quality_adv_dollar, p.atr_pct, p.market_cap, p.vol_percentile, p.prior_3m_change, p.float_shares,
  p.in_active_theme AS scan_in_active_theme, p.llm_catalyst_quality, p.ep_bar, p.score_breakdown::text AS score_breakdown,
  t.n_ticks, t.any_pass_tick, t.max_score, t.min_score,
  to_char(t.first_pass_time AT TIME ZONE 'America/New_York','HH24:MI') AS first_pass_time,
  to_char(t.first_tick_time AT TIME ZONE 'America/New_York','HH24:MI') AS first_tick_time,
  to_char(t.last_tick_time AT TIME ZONE 'America/New_York','HH24:MI') AS last_tick_time,
  a.id AS alert_id, a.score_tier AS alert_tier, a.ep_score AS alert_score, a.gap_pct AS alert_gap_pct, a.catalyst_quality AS alert_catalyst_quality,
  a.catalyst_type, a.in_active_theme AS alert_in_active_theme, a.judge_tier, a.judge_grade, a.judge_materiality_tier, a.materiality_tier,
  a.setup_class, a.tape_tier, a.vol_r5_50, a.vol_alert_vs_max, a.vol_hist_n, a.rubric_version,
  to_char(a.created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') AS alert_created_et,
  rs.expct_scheduled, rs.expct_looking, rs.expct_beat, rs.expct_growth_yoy_pct, rs.expct_combined_class,
  rs.ext_xadr_eod, rs.ext_xadr_pregap, rs.tightness_pct_eod, rs.composite_rank_eod, rs.open_range_position AS rs_open_range_position,
  rs.base_days_adr6, rs.base_depth_adr6, rs.base_days_raw40, rs.base_depth_raw40, rs.adr20_frac AS rs_adr20_frac,
  cm.q_revenue_yoy_pct, cm.extraction_quality
FROM pop p JOIN ticks t USING (ticker, scan_date)
LEFT JOIN LATERAL (SELECT * FROM mi_ep_alerts a WHERE a.ticker=p.ticker AND a.alert_date=p.scan_date AND COALESCE(a.source,'live')='live' ORDER BY a.created_at LIMIT 1) a ON TRUE
LEFT JOIN LATERAL (SELECT * FROM mi_alert_rank_shadow r WHERE r.ticker=p.ticker AND r.alert_date=p.scan_date ORDER BY r.computed_at DESC LIMIT 1) rs ON TRUE
LEFT JOIN LATERAL (SELECT * FROM mi_ep_catalyst_metrics c WHERE c.ticker=p.ticker AND c.alert_date=p.scan_date ORDER BY c.extracted_at DESC LIMIT 1) cm ON TRUE
ORDER BY p.scan_date, p.ticker;"

run hist.tsv "SELECT p.ticker, p.scan_date,
  (SELECT min(trade_date) FROM mi_daily_closes d WHERE d.ticker=p.ticker) AS hist_start,
  (SELECT count(*) FROM mi_daily_closes d WHERE d.ticker=p.ticker AND d.trade_date < p.scan_date) AS n_hist,
  (SELECT max(high_price) FROM mi_daily_closes d WHERE d.ticker=p.ticker AND d.trade_date < p.scan_date) AS ath_high,
  (SELECT max(close) FROM mi_daily_closes d WHERE d.ticker=p.ticker AND d.trade_date < p.scan_date) AS ath_close,
  (SELECT max(trade_date) FROM mi_daily_closes d WHERE d.ticker=p.ticker AND d.trade_date < p.scan_date AND d.high_price = (SELECT max(high_price) FROM mi_daily_closes d2 WHERE d2.ticker=p.ticker AND d2.trade_date < p.scan_date)) AS ath_date,
  (SELECT max(high_price) FROM mi_daily_closes d WHERE d.ticker=p.ticker AND d.trade_date < p.scan_date AND d.trade_date >= p.scan_date - 365) AS high_52w,
  (SELECT max(high_price) FROM mi_daily_closes d WHERE d.ticker=p.ticker AND d.trade_date < p.scan_date AND d.trade_date >= p.scan_date - 182) AS high_6m,
  (SELECT max(high_price) FROM mi_daily_closes d WHERE d.ticker=p.ticker AND d.trade_date < p.scan_date AND d.trade_date >= p.scan_date - 730) AS high_2y
FROM pop p ORDER BY p.scan_date, p.ticker;"

run scores.tsv "SELECT p.ticker, p.scan_date, s.score_date, s.rs_rank, s.rs_composite, s.rs_1m, s.rs_3m, s.rs_6m, s.sector, s.adv_20, s.sma_10, s.sma_20, s.sma_50, s.close AS score_close,
  (SELECT count(*) FROM mi_stock_scores s2 WHERE s2.score_date = s.score_date) AS pool_size_that_day
FROM pop p LEFT JOIN LATERAL (SELECT * FROM mi_stock_scores s WHERE s.ticker=p.ticker AND s.score_date < p.scan_date ORDER BY s.score_date DESC LIMIT 1) s ON TRUE
ORDER BY p.scan_date, p.ticker;"

run themes.tsv "SELECT p.ticker, p.scan_date,
  u.name AS theme_name, u.stage AS theme_stage, u.score AS theme_score, u.theme_date AS theme_date, u.days_active, u.consecutive_accelerating, u.rs_avg AS theme_rs_avg, cardinality(u.tickers) AS theme_size,
  b.name AS theme_name_7d, b.stage AS theme_stage_7d, b.score AS theme_score_7d, b.theme_date AS theme_date_7d
FROM pop p
LEFT JOIN LATERAL (SELECT * FROM mi_themes t WHERE p.ticker = ANY(t.tickers) AND t.stage <> 'Retired' AND t.theme_date <= p.scan_date - 1 ORDER BY t.theme_date DESC, t.score DESC NULLS LAST LIMIT 1) u ON TRUE
LEFT JOIN LATERAL (SELECT * FROM mi_themes t WHERE p.ticker = ANY(t.tickers) AND t.stage <> 'Retired' AND t.theme_date <= p.scan_date - 1 AND t.theme_date >= p.scan_date - 8 ORDER BY t.theme_date DESC, t.score DESC NULLS LAST LIMIT 1) b ON TRUE
ORDER BY p.scan_date, p.ticker;"

run prior.tsv "SELECT p.ticker, p.scan_date,
  (SELECT max(l.scan_date) FROM mi_ep_scan_log l WHERE l.ticker=p.ticker AND l.scan_date < p.scan_date AND l.ep_score IS NOT NULL) AS prev_scored_date,
  (SELECT max(l.scan_date) FROM mi_ep_scan_log l WHERE l.ticker=p.ticker AND l.scan_date < p.scan_date AND l.filter_reason IS NULL AND l.score_tier IS NOT NULL) AS prev_pass_date,
  (SELECT max(a.alert_date) FROM mi_ep_alerts a WHERE a.ticker=p.ticker AND a.alert_date < p.scan_date AND COALESCE(a.source,'live')='live') AS prev_alert_date,
  (SELECT min(l.scan_date) FROM mi_ep_scan_log l) AS scanlog_start
FROM pop p ORDER BY p.scan_date, p.ticker;"

run orb.tsv "SELECT p.ticker, p.scan_date,
  o.n_bars_0930_0944, o.orb_open, o.orb_high, o.orb_low, o.orb_close_0944, o.orb_vol, o.first_bar_et, o.last_bar_et,
  (SELECT count(*) FROM mi_intraday_bars b WHERE b.ticker=p.ticker AND b.bar_time >= (p.scan_date::timestamp AT TIME ZONE 'America/New_York') AND b.bar_time < ((p.scan_date+1)::timestamp AT TIME ZONE 'America/New_York')) AS n_bars_day
FROM pop p
LEFT JOIN LATERAL (
  SELECT count(*) AS n_bars_0930_0944, max(high) AS orb_high, min(low) AS orb_low, sum(volume) AS orb_vol,
         (array_agg(open ORDER BY bar_time))[1] AS orb_open, (array_agg(close ORDER BY bar_time DESC))[1] AS orb_close_0944,
         to_char(min(bar_time) AT TIME ZONE 'America/New_York','HH24:MI') AS first_bar_et, to_char(max(bar_time) AT TIME ZONE 'America/New_York','HH24:MI') AS last_bar_et
  FROM mi_intraday_bars b WHERE b.ticker=p.ticker
    AND b.bar_time >= ((p.scan_date::text||' 09:30')::timestamp AT TIME ZONE 'America/New_York')
    AND b.bar_time <  ((p.scan_date::text||' 09:45')::timestamp AT TIME ZONE 'America/New_York')
) o ON TRUE
ORDER BY p.scan_date, p.ticker;"

echo "[regime.tsv]"
ssh "$HOST" "$PSQL -c \"SELECT regime_date, regime, ep_threshold, spy_vs_50ma, spy_vs_200ma, qqq_vs_50ma, vix, breadth_pct_above_40ma, t2108, qqq_ema_bullish, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') AS created_et FROM mi_market_regime WHERE regime_date BETWEEN DATE '2026-04-01' AND DATE '2026-09-25' ORDER BY regime_date\"" > regime.tsv
wc -l regime.tsv

run sector.tsv "SELECT o.ticker, o.sector, o.industry FROM mi_ticker_overrides o WHERE o.ticker IN (SELECT DISTINCT ticker FROM pop) ORDER BY 1;"

echo "[daily.tsv.gz]"
ssh "$HOST" "$PSQL" <<< "$POP SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close, d.volume FROM mi_daily_closes d WHERE (d.ticker IN (SELECT DISTINCT ticker FROM pop) OR d.ticker IN ('SPY','QQQ','IWM')) AND d.trade_date BETWEEN DATE '2025-03-01' AND DATE '2026-09-25' ORDER BY d.ticker, d.trade_date;" | gzip > daily.tsv.gz
gzcat daily.tsv.gz | wc -l; du -sh daily.tsv.gz

date -u +"pulled_at_utc=%Y-%m-%dT%H:%M:%SZ" | tee extract.pulled_at
du -sh *.tsv *.gz
