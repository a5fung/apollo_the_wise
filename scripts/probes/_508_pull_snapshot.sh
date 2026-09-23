#!/usr/bin/env bash
# #508 exit-replay snapshot puller — READ-ONLY, reproducible.
#
# WHY THIS EXISTS (2026-09-09). `_508c_regime_separability_2026-08-17.py` pointed at a hardcoded
# session scratchpad that no longer exists, so a review gated on TRADE COUNT could not actually be
# re-run when the count arrived. The snapshot contract lived only in a docstring. It lives here now.
#
# Produces the four TSVs `_508_exit_rule_replay.py` reads, in its exact column order.
# `regime` is ENTRY-STAMPED from mi_live_trades (the 2026-08-08 operator fix) — NOT date-joined
# from mi_market_regime, which disagreed on 5 of 17 live trades and inflates the regime counts.
#
# Usage: bash scripts/probes/_508_pull_snapshot.sh <output-dir>
set -euo pipefail
OUT="${1:?usage: _508_pull_snapshot.sh <output-dir>}"
HOST="${APOLLO_HOST:-apollo@87.99.134.162}"
mkdir -p "$OUT"

# COPY TO STDOUT, not `psql -A -t`: COPY renders NULL as \N, which is what the replay parser
# expects. `-t` writes an empty string instead and the parser dies on int(''). Same trap the
# original 2026-07-30 pull avoided by using COPY; the contract was never written down.
run() { ssh -o ConnectTimeout=25 "$HOST" "docker exec -i apollo-postgres psql -U apollo -d apollo -X -c \"COPY ($1) TO STDOUT\""; }

REC_COLS="r.trade_id, r.ticker, r.signal_type, r.account_mode, r.alert_date, r.fill_day, r.close_day,
  r.filled_at, r.closed_at, r.entry_price, r.risk_per_share, r.entry_shares, r.realized_pnl,
  r.realized_r, r.peak_price, r.peak_r, r.peak_time, r.peak_day, r.peak_hold_day, r.peak_source,
  r.peak_bars_n, r.peak_close, r.peak_close_r, r.peak_close_day, r.giveback_r, r.capture_pct,
  r.hold_trading_days, r.stop_above_entry_ever, r.partial_taken, r.pnl_attribution,
  t.regime, r.stop_pct, r.stop_per_adr, r.peak_adr, r.realized_adr"

run "SELECT $REC_COLS FROM mi_sell_discipline_records r
     JOIN mi_live_trades t ON t.id = r.trade_id ORDER BY r.trade_id" > "$OUT/_508_records.tsv"

# Only columns 0,2,3,4 and 9 are read by the parser; 1/5/6/7/8 are positional filler it ignores.
run "SELECT t.id, t.ticker, t.hard_stop, t.orb_low, t.stop_price, t.entry_shares, 'f', 'f', 0, t.exits
     FROM mi_live_trades t JOIN mi_sell_discipline_records r ON r.trade_id = t.id
     ORDER BY t.id" > "$OUT/_508_trades.tsv"

run "SELECT r.trade_id, d.trade_date, d.open_price, d.high_price, d.low_price, d.close
     FROM mi_sell_discipline_records r
     JOIN mi_daily_closes d ON d.ticker = r.ticker
      AND d.trade_date BETWEEN r.alert_date - 1 AND COALESCE(r.close_day, r.alert_date) + 1
     ORDER BY r.trade_id, d.trade_date" > "$OUT/_508_daily.tsv"

run "SELECT r.trade_id, b.bar_time, b.open, b.high, b.low, b.close
     FROM mi_sell_discipline_records r
     JOIN mi_intraday_bars b ON b.ticker = r.ticker
      AND b.bar_time >= r.filled_at
      AND b.bar_time <= COALESCE(r.closed_at, r.filled_at + interval '10 days')
     ORDER BY r.trade_id, b.bar_time" > "$OUT/_508_minute.tsv"

wc -l "$OUT"/_508_*.tsv
