#!/usr/bin/env bash
# Theme BELONGING backtest — stage 1 of 2: the READ-ONLY prod pull (2026-09-13).
#
# Pulls the six CSVs `_ep_theme_belonging_backtest.py` reads, straight from prod Postgres via the
# operator-authorized `ssh ... docker exec apollo-postgres psql` read path (the _508_pull_snapshot.sh
# idiom — read-only SELECTs only, HANDOFF.md). Nothing is written to the database.
#
# Usage: bash scripts/probes/_ep_theme_belonging_pull.sh <output-dir>
#        then: python scripts/probes/_ep_theme_belonging_backtest.py <output-dir>
#
# CSV, not tab COPY: score_breakdown is JSON with commas; CSV quoting handles it, and NULL is an
# empty field (the parser treats '' as None everywhere).
set -euo pipefail
OUT="${1:?usage: _ep_theme_belonging_pull.sh <output-dir>}"
HOST="${APOLLO_HOST:-apollo@87.99.134.162}"
WINDOW_DAYS="${WINDOW_DAYS:-120}"
mkdir -p "$OUT"

run() {
  ssh -o ConnectTimeout=25 "$HOST" \
    "docker exec -i apollo-postgres psql -U apollo -d apollo -X -c \"COPY ($1) TO STDOUT WITH (FORMAT csv, HEADER true)\""
}

echo "pulling alerts (last $WINDOW_DAYS days, with the nearest scan-log tick + the day's regime) ..."
run "SELECT a.id, a.ticker, a.alert_date, a.detected_at, a.ep_score, a.score_tier, a.baseline_floor_tier,
            a.judge_tier, a.grade_engine_authority, a.catalyst_quality, a.confidence_multiplier,
            a.gap_pct, a.rel_volume, a.vol_percentile, a.in_active_theme,
            s.ep_bar, s.score_side, s.score_breakdown::text AS score_breakdown,
            s.in_active_theme AS log_in_active_theme, s.ep_score AS log_ep_score,
            s.float_shares, s.adv, s.prev_close, s.projected_vol_multiple, s.catalyst_quality AS log_catalyst_quality,
            r.regime, r.ep_threshold AS regime_ep_threshold
     FROM mi_ep_alerts a
     LEFT JOIN LATERAL (
        SELECT l.ep_bar, l.score_side, l.score_breakdown, l.in_active_theme, l.ep_score,
               l.float_shares, l.adv, l.prev_close, l.projected_vol_multiple, l.catalyst_quality
        FROM mi_ep_scan_log l
        WHERE l.ticker = a.ticker AND l.scan_date = a.alert_date AND l.ep_score IS NOT NULL
        ORDER BY CASE WHEN a.detected_at IS NULL OR l.scan_time_et IS NULL THEN 1e12
                      ELSE abs(extract(epoch FROM (l.scan_time_et - a.detected_at))) END, l.id DESC
        LIMIT 1
     ) s ON true
     LEFT JOIN LATERAL (
        SELECT regime, ep_threshold FROM mi_market_regime
        WHERE regime_date <= a.alert_date ORDER BY regime_date DESC LIMIT 1
     ) r ON true
     WHERE a.alert_date >= CURRENT_DATE - $WINDOW_DAYS AND a.ep_score IS NOT NULL
     ORDER BY a.alert_date, a.ticker" > "$OUT/alerts.csv"

echo "pulling theme snapshots (window + 8 days back, every stage incl. Retired tombstones) ..."
run "SELECT theme_date, name, stage, tickers::text AS tickers, description
     FROM mi_themes
     WHERE theme_date >= CURRENT_DATE - ($WINDOW_DAYS + 8)
     ORDER BY theme_date, name" > "$OUT/themes.csv"

echo "pulling ticker descriptions (the nightly assignment prompt's own one-liners) ..."
run "SELECT ticker, description, sector, industry, company_name FROM mi_ticker_overrides
     WHERE coalesce(description,'') <> '' OR coalesce(sector,'') <> ''
     ORDER BY ticker" > "$OUT/descriptions.csv"

echo "pulling the scored-but-not-alerting scan-log rows (null control i) ..."
run "SELECT DISTINCT ON (l.scan_date, l.ticker)
            l.scan_date, l.ticker, l.ep_score, l.ep_bar, l.score_side, l.score_breakdown::text AS score_breakdown,
            l.in_active_theme, l.catalyst_quality, l.gap_pct
     FROM mi_ep_scan_log l
     WHERE l.scan_date >= CURRENT_DATE - $WINDOW_DAYS AND l.ep_score IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM mi_ep_alerts a WHERE a.ticker = l.ticker AND a.alert_date = l.scan_date)
     ORDER BY l.scan_date, l.ticker, l.id DESC" > "$OUT/scanlog_nonalert.csv"

echo "pulling random board names per alert date (null control ii, deterministic draw) ..."
run "WITH dates AS (SELECT DISTINCT alert_date AS d FROM mi_ep_alerts
                    WHERE alert_date >= CURRENT_DATE - $WINDOW_DAYS AND ep_score IS NOT NULL)
     SELECT trade_date, ticker FROM (
        SELECT c.trade_date, c.ticker,
               row_number() OVER (PARTITION BY c.trade_date ORDER BY md5(c.ticker || c.trade_date::text)) AS rn
        FROM mi_daily_closes c JOIN dates ON dates.d = c.trade_date
        WHERE c.close >= 5 AND c.volume IS NOT NULL AND c.volume * c.close >= 5e6
          AND c.ticker NOT IN (SELECT ticker FROM mi_ep_alerts a WHERE a.alert_date = c.trade_date)
     ) x WHERE rn <= 10 ORDER BY trade_date, ticker" > "$OUT/controls.csv"

echo "pulling closes for the whole universe (members + alerts + scored names + controls + SPY) ..."
run "WITH members AS (SELECT DISTINCT unnest(tickers) AS t FROM mi_themes
                      WHERE theme_date >= CURRENT_DATE - ($WINDOW_DAYS + 8)
                        AND stage IN ('Nascent','Accelerating','Mainstream')),
          alerts AS (SELECT DISTINCT ticker AS t FROM mi_ep_alerts WHERE alert_date >= CURRENT_DATE - $WINDOW_DAYS),
          scored AS (SELECT DISTINCT ticker AS t FROM mi_ep_scan_log
                     WHERE scan_date >= CURRENT_DATE - $WINDOW_DAYS AND ep_score IS NOT NULL),
          dates AS (SELECT DISTINCT alert_date AS d FROM mi_ep_alerts
                    WHERE alert_date >= CURRENT_DATE - $WINDOW_DAYS AND ep_score IS NOT NULL),
          ctrl AS (SELECT ticker AS t FROM (
                     SELECT c.trade_date, c.ticker,
                            row_number() OVER (PARTITION BY c.trade_date ORDER BY md5(c.ticker || c.trade_date::text)) AS rn
                     FROM mi_daily_closes c JOIN dates ON dates.d = c.trade_date
                     WHERE c.close >= 5 AND c.volume IS NOT NULL AND c.volume * c.close >= 5e6
                       AND c.ticker NOT IN (SELECT ticker FROM mi_ep_alerts a WHERE a.alert_date = c.trade_date)
                   ) x WHERE rn <= 10),
          uni AS (SELECT t FROM members UNION SELECT t FROM alerts UNION SELECT t FROM scored
                  UNION SELECT t FROM ctrl UNION SELECT 'SPY')
     SELECT d.ticker, d.trade_date, d.close
     FROM mi_daily_closes d JOIN uni ON uni.t = d.ticker
     WHERE d.trade_date >= CURRENT_DATE - ($WINDOW_DAYS + 110) AND d.close > 0
     ORDER BY d.ticker, d.trade_date" > "$OUT/closes.csv"

for f in alerts themes descriptions scanlog_nonalert controls closes; do
  printf '  %-18s %8d rows\n' "$f.csv" "$(( $(wc -l < "$OUT/$f.csv") - 1 ))"
done
echo "done -> $OUT   (next: python scripts/probes/_ep_theme_belonging_backtest.py $OUT)"
