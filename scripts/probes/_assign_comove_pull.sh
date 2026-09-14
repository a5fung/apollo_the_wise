#!/usr/bin/env bash
# Assignment-gate co-movement backtest — stage 1 of 2: the READ-ONLY prod pull (2026-09-13).
#
# Pulls the five CSVs `_assign_comove_backtest.py` reads, straight from prod Postgres via the
# operator-authorized `ssh ... docker exec apollo-postgres psql` read path (the
# _ep_theme_belonging_pull.sh / _508_pull_snapshot.sh idiom — read-only SELECTs only). Nothing is
# written to the database.
#
# Usage: bash scripts/probes/_assign_comove_pull.sh <output-dir>
#        then: python scripts/probes/_assign_comove_backtest.py <output-dir>
#
# CSV, not tab COPY: audit `detail` is JSON with commas; CSV quoting handles it.
set -euo pipefail
OUT="${1:?usage: _assign_comove_pull.sh <output-dir>}"
HOST="${APOLLO_HOST:-apollo@87.99.134.162}"
# ~60 trading days of nightly runs + slack; the replay trims to the last 60 SPY sessions itself.
EVENT_DAYS="${EVENT_DAYS:-100}"
mkdir -p "$OUT"

run() {
  ssh -o ConnectTimeout=25 "$HOST" \
    "docker exec -i apollo-postgres psql -U apollo -d apollo -X -c \"COPY ($1) TO STDOUT WITH (FORMAT csv, HEADER true)\""
}

echo "pulling the assignment audit trail (proposals + every skip reason + the nightly strip) ..."
run "SELECT id, (created_at AT TIME ZONE 'America/New_York')::date AS run_date,
            to_char(created_at AT TIME ZONE 'America/New_York', 'HH24:MI') AS run_time_et,
            event_type, summary, detail
     FROM mi_audit_log
     WHERE created_at >= CURRENT_DATE - $EVENT_DAYS
       AND event_type IN ('assignment_llm_proposed', 'assignment_skipped_sector_outlier',
                          'assignment_skipped_sector_kw', 'assignment_skipped_desc_overlap',
                          'assignment_sector_kw_overridden_by_desc', 'assignment_skipped_exclusion',
                          'cooldown_blocked_assignment', 'assignment_theme_not_found',
                          'theme_carryforward_filter_stripped')
     ORDER BY id" > "$OUT/events.csv"

echo "pulling theme snapshots (window + 10 days back, every stage incl. Retired tombstones) ..."
run "SELECT theme_date, name, stage, tickers::text AS tickers
     FROM mi_themes
     WHERE theme_date >= CURRENT_DATE - ($EVENT_DAYS + 10)
     ORDER BY theme_date, name" > "$OUT/themes.csv"

echo "pulling the sector label per ticker (latest mi_stock_scores row, plus the overrides cache) ..."
run "SELECT ticker, sector, src FROM (
        SELECT DISTINCT ON (ticker) ticker, sector, 'scores' AS src
        FROM mi_stock_scores
        WHERE score_date >= CURRENT_DATE - 130 AND sector IS NOT NULL AND sector <> ''
        ORDER BY ticker, score_date DESC
     ) s
     UNION ALL
     SELECT ticker, sector, 'override' AS src FROM mi_ticker_overrides
     WHERE sector IS NOT NULL AND sector <> ''
     ORDER BY 1, 3" > "$OUT/sectors.csv"

echo "pulling the matched-control pool (assignment-eligible names per sector, deterministic draw) ..."
run "WITH latest AS (SELECT max(score_date) AS d FROM mi_stock_scores),
          elig AS (SELECT s.ticker, s.sector FROM mi_stock_scores s, latest
                   WHERE s.score_date = latest.d AND s.rs_rank <= 600
                     AND s.sector IS NOT NULL AND s.sector <> '')
     SELECT ticker, sector FROM (
        SELECT ticker, sector, row_number() OVER (PARTITION BY sector ORDER BY md5(ticker)) AS rn
        FROM elig
     ) x WHERE rn <= 40 ORDER BY sector, ticker" > "$OUT/controls.csv"

echo "pulling closes (theme members + every ticker named in the audit trail + controls + SPY) ..."
run "WITH members AS (SELECT DISTINCT unnest(tickers) AS t FROM mi_themes
                      WHERE theme_date >= CURRENT_DATE - ($EVENT_DAYS + 10)),
          ev AS (SELECT DISTINCT m[1] AS t
                 FROM mi_audit_log a,
                      LATERAL regexp_matches(a.detail, 'ticker.: ?.([A-Z][A-Z0-9.-]*)', 'g') AS m
                 WHERE a.created_at >= CURRENT_DATE - $EVENT_DAYS
                   AND a.event_type LIKE 'assignment_%'),
          latest AS (SELECT max(score_date) AS d FROM mi_stock_scores),
          elig AS (SELECT s.ticker, s.sector FROM mi_stock_scores s, latest
                   WHERE s.score_date = latest.d AND s.rs_rank <= 600
                     AND s.sector IS NOT NULL AND s.sector <> ''),
          ctrl AS (SELECT ticker AS t FROM (
                     SELECT ticker, row_number() OVER (PARTITION BY sector ORDER BY md5(ticker)) AS rn
                     FROM elig) x WHERE rn <= 40),
          uni AS (SELECT t FROM members UNION SELECT t FROM ev UNION SELECT t FROM ctrl UNION SELECT 'SPY')
     SELECT d.ticker, d.trade_date, d.close
     FROM mi_daily_closes d JOIN uni ON uni.t = d.ticker
     WHERE d.trade_date >= CURRENT_DATE - ($EVENT_DAYS + 120) AND d.close > 0
     ORDER BY d.ticker, d.trade_date" > "$OUT/closes.csv"

for f in events themes sectors controls closes; do
  printf '  %-14s %8d rows\n' "$f.csv" "$(( $(wc -l < "$OUT/$f.csv") - 1 ))"
done
echo "done -> $OUT   (next: python scripts/probes/_assign_comove_backtest.py $OUT)"
