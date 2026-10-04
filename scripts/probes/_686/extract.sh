#!/bin/bash
# #686 — the ONE data pull for the September block (read-only, $0). Written 2026-10-04, FROZEN
# (sha256 recorded in docs/analysis/686_preregistration_2026-10-04.md §Freeze record). Derived from
# scripts/probes/_684/extract.sh + live_entry_bars.sql with exactly four changes, each marked
# "#686:" below: (1) the scan-date window is the registered block 2026-09-04..2026-09-25 (not
# "last date with 15 later sessions"); (2) two HIGH-only tick/alert columns the live-entry frame
# needs (first_high_time, any_high_alert) — #684's first_pass_time is the first pass of ANY tier;
# (3) the daily / regime pulls run through the pull date so the 15 forward sessions are present.
#
# REFUSES to run before the earliest run date (PT 2026-10-17 — the 15th NYSE session after 09-25
# is 10-16 and its daily bar lands with that evening's nightly pull). Nothing here reads an outcome
# into a human's view: the files land on disk for preregistered_read.py, which is the ONE read.
#
# Outputs (data/): pop.tsv hist.tsv scores.tsv themes.tsv prior.tsv orb.tsv regime.tsv sector.tsv
#   daily.tsv.gz (gitignored) live_entry_bars.tsv (gitignored)  — same shapes as #684's files, so
#   #684's features.py / study.py / study_orb_live.py read them unchanged.
set -euo pipefail
cd "$(dirname "$0")"
EARLIEST="2026-10-17"
TODAY_PT=$(TZ=America/Los_Angeles date +%F)
if [[ "$TODAY_PT" < "$EARLIEST" ]]; then   # no override: a pull before the date would put the block's outcomes on disk
  echo "REFUSED: #686 block matures with the 2026-10-16 session; earliest pull/run is $EARLIEST PT (today $TODAY_PT)." >&2
  exit 3
fi
mkdir -p data && cd data
HOST="apollo@87.99.134.162"
PSQL='docker exec -i apollo-postgres psql -U apollo -d apollo -A -F "|" -v ON_ERROR_STOP=1'

# #686: fixed block window. Everything else in POP is #684's CTE verbatim (same dedupe rule).
POP="WITH raw AS (SELECT l.* FROM mi_ep_scan_log l WHERE l.scan_date BETWEEN DATE '2026-09-04' AND DATE '2026-09-25' AND l.ep_score IS NOT NULL),
ticks AS (SELECT ticker, scan_date, count(*) AS n_ticks, bool_or(filter_reason IS NULL AND score_tier IS NOT NULL) AS any_pass_tick,
          max(ep_score) AS max_score, min(ep_score) AS min_score,
          min(scan_time_et) FILTER (WHERE filter_reason IS NULL AND score_tier IS NOT NULL) AS first_pass_time,
          min(scan_time_et) FILTER (WHERE filter_reason IS NULL AND score_tier = 'HIGH') AS first_high_time,
          min(scan_time_et) AS first_tick_time, max(scan_time_et) AS last_tick_time
          FROM raw GROUP BY ticker, scan_date),
pop AS (SELECT DISTINCT ON (r.ticker, r.scan_date) r.* FROM raw r
        ORDER BY r.ticker, r.scan_date, (r.filter_reason IS NULL AND r.score_tier IS NOT NULL) DESC, r.ep_score DESC, r.scan_time_et DESC)"

run() { # name, select-sql
  echo "[$1]"
  ssh "$HOST" "$PSQL" <<< "$POP $2" > "$1"
  wc -l "$1"
}

# #686: + t.first_high_time, ah.any_high_alert, ah.first_high_alert_et (HIGH-only columns). All other columns = #684 verbatim.
run pop.tsv "SELECT p.ticker, p.scan_date, p.ep_score, p.score_tier, p.catalyst_quality, p.filter_reason, p.reject_stage, p.score_side,
  p.gap_pct, p.prev_close, p.current_price, p.rel_volume, p.pm_rvol, p.projected_vol_multiple, p.adv, p.adv_source, p.rank_by_gap, p.rank_by_prescore,
  p.minutes_since_open, to_char(p.scan_time_et AT TIME ZONE 'America/New_York','HH24:MI') AS scan_time, p.prev_day_volume, p.today_volume,
  p.days_since_prior_alert, p.extension_pct, p.quality_adv_dollar, p.atr_pct, p.market_cap, p.vol_percentile, p.prior_3m_change, p.float_shares,
  p.in_active_theme AS scan_in_active_theme, p.llm_catalyst_quality, p.ep_bar, p.score_breakdown::text AS score_breakdown,
  t.n_ticks, t.any_pass_tick, t.max_score, t.min_score,
  to_char(t.first_pass_time AT TIME ZONE 'America/New_York','HH24:MI') AS first_pass_time,
  to_char(t.first_high_time AT TIME ZONE 'America/New_York','HH24:MI') AS first_high_time,
  to_char(t.first_tick_time AT TIME ZONE 'America/New_York','HH24:MI') AS first_tick_time,
  to_char(t.last_tick_time AT TIME ZONE 'America/New_York','HH24:MI') AS last_tick_time,
  a.id AS alert_id, a.score_tier AS alert_tier, a.ep_score AS alert_score, a.gap_pct AS alert_gap_pct, a.catalyst_quality AS alert_catalyst_quality,
  a.catalyst_type, a.in_active_theme AS alert_in_active_theme, a.judge_tier, a.judge_grade, a.judge_materiality_tier, a.materiality_tier,
  a.setup_class, a.tape_tier, a.vol_r5_50, a.vol_alert_vs_max, a.vol_hist_n, a.rubric_version,
  to_char(a.created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') AS alert_created_et,
  ah.any_high_alert, to_char(ah.first_high_alert AT TIME ZONE 'America/New_York','HH24:MI') AS first_high_alert_et,
  rs.expct_scheduled, rs.expct_looking, rs.expct_beat, rs.expct_growth_yoy_pct, rs.expct_combined_class,
  rs.ext_xadr_eod, rs.ext_xadr_pregap, rs.tightness_pct_eod, rs.composite_rank_eod, rs.open_range_position AS rs_open_range_position,
  rs.base_days_adr6, rs.base_depth_adr6, rs.base_days_raw40, rs.base_depth_raw40, rs.adr20_frac AS rs_adr20_frac,
  cm.q_revenue_yoy_pct, cm.extraction_quality
FROM pop p JOIN ticks t USING (ticker, scan_date)
LEFT JOIN LATERAL (SELECT * FROM mi_ep_alerts a WHERE a.ticker=p.ticker AND a.alert_date=p.scan_date AND COALESCE(a.source,'live')='live' ORDER BY a.created_at LIMIT 1) a ON TRUE
LEFT JOIN LATERAL (SELECT bool_or(x.score_tier='HIGH') AS any_high_alert, min(x.created_at) FILTER (WHERE x.score_tier='HIGH') AS first_high_alert
                   FROM mi_ep_alerts x WHERE x.ticker=p.ticker AND x.alert_date=p.scan_date AND COALESCE(x.source,'live')='live') ah ON TRUE
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

# #686: live_entry_bars (= #684 live_entry_bars.sql verbatim apart from the POP window): every 1-minute bar
# 09:30-16:00 ET for every population row, for the live-entry frame's bar-by-bar replay.
run live_entry_bars.tsv "SELECT p.ticker, p.scan_date, to_char(b.bar_time AT TIME ZONE 'America/New_York', 'HH24:MI') AS hhmm, b.open, b.high, b.low
FROM pop p
JOIN mi_intraday_bars b ON b.ticker = p.ticker
  AND b.bar_time >= ((p.scan_date::text||' 09:30')::timestamp AT TIME ZONE 'America/New_York')
  AND b.bar_time <  ((p.scan_date::text||' 16:00')::timestamp AT TIME ZONE 'America/New_York')
ORDER BY p.scan_date, p.ticker, b.bar_time;"

# #686 (4th change, added at review 2026-10-04): mi_live_trades ORDER RECORDS for the population — what the live
# path actually attempted. scheduler.py:1194 `already_alerted` is ANY-tier and the judge update rewrites
# mi_ep_alerts.score_tier in place, so a HIGH alert row is only an upper bound on "ordered"; STEP 0 of the
# read cross-tabs model-orderable vs this record. Status is collapsed to skipped / cancelled / placed and NO
# price, share or P&L column is pulled — the file holds no outcome.
run trades.tsv "SELECT t.ticker, t.alert_date, t.signal_type, t.account_mode,
  CASE WHEN t.status='skipped' THEN 'skipped' WHEN t.status='cancelled' THEN 'cancelled' ELSE 'placed' END AS status,
  t.skip_reason, to_char(t.created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS created_et
FROM mi_live_trades t WHERE t.signal_type='magna53' AND (t.ticker, t.alert_date) IN (SELECT ticker, scan_date FROM pop)
ORDER BY t.alert_date, t.ticker, t.created_at;"

echo "[regime.tsv]"   # #686: through the pull date (was ..09-25)
ssh "$HOST" "$PSQL -c \"SELECT regime_date, regime, ep_threshold, spy_vs_50ma, spy_vs_200ma, qqq_vs_50ma, vix, breadth_pct_above_40ma, t2108, qqq_ema_bullish, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') AS created_et FROM mi_market_regime WHERE regime_date BETWEEN DATE '2026-04-01' AND CURRENT_DATE ORDER BY regime_date\"" > regime.tsv
wc -l regime.tsv

run sector.tsv "SELECT o.ticker, o.sector, o.industry FROM mi_ticker_overrides o WHERE o.ticker IN (SELECT DISTINCT ticker FROM pop) ORDER BY 1;"

echo "[daily.tsv.gz]"  # #686: through the pull date (was ..09-25) — the 15 forward sessions must be inside
ssh "$HOST" "$PSQL" <<< "$POP SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close, d.volume FROM mi_daily_closes d WHERE (d.ticker IN (SELECT DISTINCT ticker FROM pop) OR d.ticker IN ('SPY','QQQ','IWM')) AND d.trade_date BETWEEN DATE '2025-03-01' AND CURRENT_DATE ORDER BY d.ticker, d.trade_date;" | gzip > daily.tsv.gz
gzcat daily.tsv.gz | wc -l; du -sh daily.tsv.gz

date -u +"pulled_at_utc=%Y-%m-%dT%H:%M:%SZ" | tee extract.pulled_at
du -sh *.tsv *.gz
