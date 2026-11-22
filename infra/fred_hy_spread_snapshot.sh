#!/usr/bin/env bash
# Daily snapshot of the ICE BofA US High Yield OAS (FRED BAMLH0A0HYM2). FRED keeps only ~3 years of this
# series, so each day's full file is kept; merging them rebuilds the history past the 3-year window.
# His ruling 2026-11-22 ("yes on recs", docs/analysis/liquidity_composite_prereg_2026-11-22.md §10-11): internal storage only.
# To install on the host (needs his permission): copy to /home/apollo/fred_hy_spread_snapshot.sh and add the cron line
#   15 14 * * * /home/apollo/fred_hy_spread_snapshot.sh >> /home/apollo/fred_snapshots/snapshot.log 2>&1
# Keyless public endpoint; sends nothing.
set -euo pipefail
DIR=/home/apollo/fred_snapshots
mkdir -p "$DIR"
OUT="$DIR/BAMLH0A0HYM2_$(date -u +%Y-%m-%d).csv"
TMP="$(mktemp)"
if curl -sf --max-time 60 "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2" -o "$TMP" && [ "$(wc -l < "$TMP")" -gt 100 ]; then
  mv "$TMP" "$OUT"; echo "$(date -u +%FT%TZ) ok $(wc -l < "$OUT") rows $(tail -1 "$OUT")"
else
  rm -f "$TMP"; echo "$(date -u +%FT%TZ) FAILED"; exit 1
fi
