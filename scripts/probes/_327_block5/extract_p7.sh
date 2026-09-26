#!/bin/bash
# Block 5 / P7 (the delayed-entry DIAGNOSIS, 2026-09-26) — three supplementary read-only prod
# pulls, $0, gitignored outputs (*.csv). None of these existed in the P0/P3 extracts:
#   1. index_daily.csv   — SPY / QQQ / IWM daily bars (the "market on the fire day" cut, Q3)
#   2. ep_scan_log.csv   — mi_ep_scan_log rows 2026-08-20..09-25: what OUR OWN EP screen did to
#                          each (ticker, gap day) — the alert tier / ep_score / catalyst /
#                          rejection stage the lane's trigger rows do not carry (ep_score is
#                          stamped on 103 of 3,767 trigger rows; the scan log has the rest)
#   3. ep_alerts.csv     — mi_ep_alerts since 2026-07-01 (every source; the probe filters on
#                          COALESCE(source,'live')='live', the seed query's own LIVE_SOURCE_SQL)
# Pulled once, read many. Pull time recorded in ep_scan_log.pulled_at (same table state as the
# P0/P3 pulls of the same day; mi_ep_alerts / mi_ep_scan_log are append-only).
set -euo pipefail
cd "$(dirname "$0")"
HOST="apollo@87.99.134.162"
PSQL='docker exec -i apollo-postgres psql -U apollo -d apollo -v ON_ERROR_STOP=1'

echo "[1/3] mi_daily_closes — SPY / QQQ / IWM, 2026-06-01 .."
ssh "$HOST" "$PSQL -c \"\\copy (
  SELECT trade_date, ticker, close, volume, open_price, high_price, low_price
  FROM mi_daily_closes
  WHERE ticker IN ('SPY','QQQ','IWM') AND trade_date >= '2026-06-01'
  ORDER BY ticker, trade_date
) TO STDOUT WITH CSV HEADER\"" > index_daily.csv

echo "[2/3] mi_ep_scan_log — 2026-08-20 .. 2026-09-25, every scan tick row"
ssh "$HOST" "$PSQL -c \"\\copy (
  SELECT id, scan_date, ticker, scan_time_et, gap_pct, prev_close, rel_volume, filter_reason,
         reject_stage, ep_score, score_tier, ep_bar, score_side, catalyst_quality,
         llm_catalyst_quality, extension_pct, prior_3m_change, market_cap, float_shares, atr_pct,
         adv, quality_adv_dollar, vol_percentile, in_active_theme, days_since_prior_alert,
         minutes_since_open, price_source, current_price
  FROM mi_ep_scan_log
  WHERE scan_date BETWEEN '2026-08-20' AND '2026-09-25'
  ORDER BY scan_date, ticker, scan_time_et
) TO STDOUT WITH CSV HEADER\"" > ep_scan_log.csv

echo "[3/3] mi_ep_alerts — since 2026-07-01, every source (filtered to live in the probe)"
ssh "$HOST" "$PSQL -c \"\\copy (
  SELECT id, ticker, alert_date, gap_pct, rel_volume, ep_score, score_tier, catalyst_quality,
         source, detected_at, in_active_theme, judge_tier, judge_direction, judge_grade,
         setup_class, vol_percentile, pm_rvol
  FROM mi_ep_alerts
  WHERE alert_date >= '2026-07-01'
  ORDER BY alert_date, ticker
) TO STDOUT WITH CSV HEADER\"" > ep_alerts.csv

date -u +"pulled_at_utc=%Y-%m-%dT%H:%M:%SZ" | tee ep_scan_log.pulled_at
wc -l index_daily.csv ep_scan_log.csv ep_alerts.csv
