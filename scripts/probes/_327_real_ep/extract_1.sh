#!/bin/bash
# #327 real-EP rerun (2026-09-26) — pull 1 of 2, read-only, $0. Outputs are gitignored (>500 KB) except
# alerts.tsv (small). Population = the STEP 0 gate's 277 campaigns (gate.sql / gate_out.txt).
#   alerts.tsv   the 277 campaigns + context (tier / score / gap / catalyst / prior close / era)
#   daily.tsv    mi_daily_closes for the cohort tickers 2025-12-01 .. 2026-09-25 (MA warm-up for the
#                50-DMA / 65-EMA arms at a May fire + the full walk horizon)
#   mincov.tsv   which (ticker, ET day) pairs mi_intraday_bars holds, 2026-04-20 .. 2026-09-25, with
#                the bar count — drives pull 2 (extract_2.sh), the minute bars for the window pairs
set -euo pipefail
cd "$(dirname "$0")"
HOST="apollo@87.99.134.162"
PSQL='docker exec -i apollo-postgres psql -U apollo -d apollo -A -v ON_ERROR_STOP=1'
POP="WITH a AS (SELECT DISTINCT ON (ticker, alert_date) ticker, alert_date, score_tier, gap_pct, ep_score, catalyst_quality, in_active_theme, created_at FROM mi_ep_alerts WHERE alert_date BETWEEN DATE '2026-05-01' AND DATE '2026-09-11' AND COALESCE(source,'live')='live' ORDER BY ticker, alert_date, created_at)"

echo "[1/3] alerts.tsv"
ssh "$HOST" "$PSQL -c \"$POP SELECT a.ticker, a.alert_date, a.score_tier, a.ep_score, a.gap_pct, a.catalyst_quality, a.in_active_theme, CASE WHEN a.alert_date < DATE '2026-08-22' THEN 'A' ELSE 'B' END AS era, (SELECT d.close FROM mi_daily_closes d WHERE d.ticker=a.ticker AND d.trade_date < a.alert_date ORDER BY d.trade_date DESC LIMIT 1) AS prior_close FROM a ORDER BY a.ticker, a.alert_date\"" > alerts.tsv

echo "[2/3] daily.tsv"
ssh "$HOST" "$PSQL -c \"$POP SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close, d.volume FROM mi_daily_closes d WHERE d.ticker IN (SELECT ticker FROM a) AND d.trade_date BETWEEN DATE '2025-12-01' AND DATE '2026-09-25' ORDER BY d.ticker, d.trade_date\"" > daily.tsv

echo "[3/3] mincov.tsv"
ssh "$HOST" "$PSQL -c \"$POP SELECT b.ticker, (b.bar_time AT TIME ZONE 'America/New_York')::date AS d, count(*) AS n FROM mi_intraday_bars b WHERE b.ticker IN (SELECT ticker FROM a) AND b.bar_time >= TIMESTAMPTZ '2026-04-20 00:00 America/New_York' AND b.bar_time < TIMESTAMPTZ '2026-09-26 00:00 America/New_York' GROUP BY 1,2 ORDER BY 1,2\"" > mincov.tsv

date -u +"pulled_at_utc=%Y-%m-%dT%H:%M:%SZ" | tee extract_1.pulled_at
wc -l alerts.tsv daily.tsv mincov.tsv; du -sh alerts.tsv daily.tsv mincov.tsv
