#!/usr/bin/env bash
# STEP 0 DATA GATE — every lens in scripts/backtest_data_audit/ on ONE daily-bar export, in order. $0, offline, read-only on the data.
# Standard: docs/methodology/backtest_data_standard.md §2 (the gate table G1..G10). README.md in this dir explains each step.
#
#   bash scripts/backtest_data_audit/run_all.sh <era-dir> <label> [richer-era-dir]
#
#   era-dir      directory holding daily_closes_all.csv.gz and whichever sidecars exist: daily_raw_close.csv.gz (measured raw close),
#                symbol_guard.tsv (identity breaks), cb702_splits.psv, cb702_sic.psv, small_pulls.psv, minutes/, out/{entries,candidates,
#                watch,trades}*.tsv*  — a missing sidecar skips the flag that needs it and the summary says so
#   label        A | B | any short name. A/B set the watch-window defaults (A 2017-03-01..2021-12-31, B 2022-03-28..2024-12-31)
#   richer-dir   the export that still carries delisted names (era B when auditing era A): enables the pair checks + the overlap
#
# Env:  OUT=<dir>        where consoles and TSVs go (default: a dated dir under $TMPDIR)      CUTOFF=2024-12-31 (the scripts refuse later)
#       FAST=1           skip the two minute-reading steps (entries, calendar --minutes)        APOLLO_DATA=~/apollo_data
#       WATCH_START / WATCH_END   override the watch window        TRADES=<tsv.gz>   the trade list for G8 (default: out/trades_*exitpb.tsv.gz)
#
# Every lens runs even if an earlier one fails (no `set -e`): the gate wants ALL readings, then `gate_verdict.py` decides. Exit code:
# 0 = every gate PASS, 2 = at least one REFUSAL (see the verdict table), 1 = a script crashed.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ERA_DIR="${1:?era-dir}"; LABEL="${2:?label}"; RICH_DIR="${3:-}"
APOLLO_DATA="${APOLLO_DATA:-$HOME/apollo_data}"
CUTOFF="${CUTOFF:-2024-12-31}"
OUT="${OUT:-${TMPDIR:-/tmp}/backtest_data_audit_${LABEL}_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$OUT"/{universe,dup,price,sectype,pit}
EXPORT="$ERA_DIR/daily_closes_all.csv.gz"
[ -f "$EXPORT" ] || { echo "no export at $EXPORT"; exit 1; }
RICH_EXPORT=""; [ -n "$RICH_DIR" ] && RICH_EXPORT="$RICH_DIR/daily_closes_all.csv.gz"
PY="${PYTHON:-python3}"

# ---- sidecars (present → used; absent → the step runs without that flag and the log says so) ------------------------------------
first() { for f in "$@"; do [ -e "$f" ] && { echo "$f"; return; }; done; echo ""; }
RAW=$(first "$ERA_DIR/daily_raw_close.csv.gz")
GUARD=$(first "$ERA_DIR/symbol_guard.tsv")
SPLITS=$(first "$ERA_DIR/cb702_splits.psv" "$APOLLO_DATA/cb702/cb702_splits.psv")
SIC=$(first "$ERA_DIR/cb702_sic.psv" "$APOLLO_DATA/cb702/cb702_sic.psv")
SMALL=$(first "$ERA_DIR/small_pulls.psv" "$APOLLO_DATA/cb702/small_pulls.psv")
ASSETS=$(first "$APOLLO_DATA/cb702/qm_streams/alpaca_all_2016_2022/assets.tsv")
MINUTES=$(first "$ERA_DIR/minutes")
ENTRIES=$(first "$ERA_DIR"/out/entries_pre_tl_com.tsv.gz "$ERA_DIR"/out/entries_discovery.tsv.gz "$ERA_DIR"/out/entries_*.tsv.gz)
CANDS=$(first "$ERA_DIR"/out/candidates_tl_com.tsv "$ERA_DIR"/out/candidates.tsv)
WATCH=$(first "$ERA_DIR"/out/watch_tl_com.tsv.gz "$ERA_DIR"/out/watch.tsv.gz)
TRADES="${TRADES:-$(first "$ERA_DIR"/out/trades_*exitpb.tsv.gz)}"
case "$LABEL" in
  A) WS="${WATCH_START:-2017-03-01}"; WE="${WATCH_END:-2021-12-31}" ;;
  *) WS="${WATCH_START:-2022-03-28}"; WE="${WATCH_END:-2024-12-31}" ;;
esac
# Hand-verified non-common instruments that pass the universe filters in era A (security_type_check U2; a person confirmed each
# against price level and dates — the classifier only PROPOSES). Reported as a count; exclusion is the operator's fork (standard §5).
VERIFIED_REAL="UWT,DWT,GASL,RUSL,MRRL,FRLG,BSCJ,BSCK,BSJJ,BSJK,BSJL,IBDL,IBDM,ERUS,WTRU,BDXA,PSTH,AGC,IPOA,TACO,SAMA,MUDS,HCAC"

{
  echo "run_all.sh  $(date -u +%FT%TZ)  label=$LABEL  export=$EXPORT  richer=${RICH_EXPORT:-none}  cutoff=$CUTOFF  out=$OUT"
  echo "sidecars: raw=${RAW:-none} guard=${GUARD:-none} splits=${SPLITS:-none} sic=${SIC:-none} small=${SMALL:-none} assets=${ASSETS:-none}"
  echo "          minutes=${MINUTES:-none} entries=${ENTRIES:-none} candidates=${CANDS:-none} watch=${WATCH:-none} trades=${TRADES:-none}"
  echo "watch window: $WS .. $WE   FAST=${FAST:-0}"
  echo "export sha256: $(shasum -a 256 "$EXPORT" | cut -c1-16)  size: $(stat -f %z "$EXPORT" 2>/dev/null || stat -c %s "$EXPORT")"
} | tee "$OUT/run_all.log"

declare -a STEPS RCS
step() {  # step <name> <cmd...>   — runs, logs rc, never aborts the chain
  local name="$1"; shift
  echo "== [$name] $*" | tee -a "$OUT/run_all.log"
  local t0=$SECONDS
  "$@" > "$OUT/$name.console.txt" 2>&1; local rc=$?
  echo "   rc=$rc  ($((SECONDS - t0))s)  -> $OUT/$name.console.txt" | tee -a "$OUT/run_all.log"
  STEPS+=("$name"); RCS+=("$rc")
}
opt() { [ -n "$2" ] && printf '%s\n%s\n' "$1" "$2"; }   # emits "--flag value" only when value is non-empty

# 0. selftests — a check that cannot see its planted case is not a check (standard §3)
step selftest_universe  $PY "$HERE/universe_check.py" --selftest
step selftest_duplicate $PY "$HERE/duplicate_series_check.py" --selftest
step selftest_price     $PY "$HERE/price_integrity_check.py" --selftest
step selftest_sectype   $PY "$HERE/security_type_check.py" --selftest

# 1. G1 G2 G4 + stale/non-equity tripwires — universe completeness, survivorship, identity (pair checks need the richer export)
step universe $PY "$HERE/universe_check.py" --export "$EXPORT" --label "$LABEL" --cutoff "$CUTOFF" --out-dir "$OUT/universe" \
  $(opt --other "$RICH_EXPORT") $( [ -n "$RICH_EXPORT" ] && printf '%s\n%s\n' --other-label R ) \
  $(opt --guard "$GUARD") $(opt --splits "$SPLITS") $(opt --sic "$SIC") $(opt --small-pulls "$SMALL") $(opt --raw-close "$RAW") $(opt --assets "$ASSETS")

# 2. G3 — one company under two symbols (strict + scaled twins); --vs adds the cross-era seam
step duplicate $PY "$HERE/duplicate_series_check.py" "$EXPORT" --label "$LABEL" --out "$OUT/dup" --cut "$CUTOFF" $(opt --assets "$ASSETS") $(opt --vs "$RICH_EXPORT")

# 3. G5 — price + corporate actions; the three positive controls MUST be flagged (exit 3 otherwise)
step price $PY "$HERE/price_integrity_check.py" --export "$EXPORT" --label "$LABEL" --out-dir "$OUT/price" --cutoff "$CUTOFF" \
  $(opt --raw-close "$RAW") $(opt --splits "$SPLITS") $(opt --sectype "$SMALL") $(opt --compare "$RICH_EXPORT") $( [ -n "$RICH_EXPORT" ] && printf '%s\n%s\n' --compare-label R )

# 4. G6 — security type: untyped admitted nights <= 2% (exit 3), the verified non-common list counted, identity-break exposure
if [ -n "$SMALL" ] && [ -n "$SIC" ] && [ -n "$ASSETS" ] && { [ -n "$RAW" ] || [ -n "$SPLITS" ]; }; then
  RAWORSPLIT=$( [ -n "$RAW" ] && printf '%s\n%s\n' --raw-close "$RAW" || printf '%s\n%s\n' --splits "$SPLITS" )
  step sectype $PY "$HERE/security_type_check.py" --export "$EXPORT" --era "$LABEL" $RAWORSPLIT --small "$SMALL" --sic "$SIC" --assets "$ASSETS" \
    --watch-start "$WS" --watch-end "$WE" --cutoff "$CUTOFF" --max-unknown-share 0.02 --verified-real "$VERIFIED_REAL" \
    $(opt --breaks "$GUARD") $(opt --vs-export "$RICH_EXPORT") $( [ -n "$RICH_EXPORT" ] && [ -n "$SPLITS" ] && printf '%s\n%s\n' --vs-splits "$SPLITS" ) \
    $( [ -n "$WATCH" ] && printf '%s\n%s\n' --impact "$WATCH::::watch_date" ) --out "$OUT/sectype"
else
  echo "== [sectype] SKIPPED: needs small_pulls.psv + cb702_sic.psv + assets.tsv + (daily_raw_close.csv.gz | cb702_splits.psv)" | tee -a "$OUT/run_all.log"
fi

# 5. G7 — the point-in-time checklist (exit 1 when a code anchor moved)
step pit_lint $PY "$HERE/pit_lint.py" lint --out "$OUT/pit"

# 6. G9 — calendar, early-close after-hours minutes (the minute scan is the slow part: FAST=1 skips it)
step pit_calendar $PY "$HERE/pit_lint.py" calendar --export "$EXPORT" --label "$LABEL" --out "$OUT/pit" $( [ "${FAST:-0}" != 1 ] && opt --minutes "$MINUTES" )

# 7. F7 — non-point-in-time inputs on the universe member-nights (reads the era dir's own small_pulls / sic / raw / guard)
step pit_inputs $PY "$HERE/pit_lint.py" inputs --data "$ERA_DIR" --start "$WS" --end "$WE" --label "$LABEL" --out "$OUT/pit" \
  $( [ -n "$RAW" ] && echo --raw-close ) $( [ -n "$GUARD" ] && echo --breaks ) $(opt --assets "$ASSETS")

# 8. F8 — walks that end inside the horizon / cross a break; the chain key recomputed point-in-time; entry-time facts (W2 costs)
if [ -n "$CANDS" ]; then
  step pit_horizon $PY "$HERE/pit_lint.py" horizon --data "$ERA_DIR" --candidates "$CANDS" --k tl --through "$CUTOFF" --label "$LABEL" --out "$OUT/pit" $( [ -n "$GUARD" ] && echo --breaks )
  [ -n "$WATCH" ] && step pit_chain $PY "$HERE/pit_lint.py" chain --watch "$WATCH" --candidates "$CANDS" --through "$CUTOFF" --label "$LABEL" --out "$OUT/pit"
fi
if [ -n "$ENTRIES" ]; then
  step pit_entries $PY "$HERE/pit_lint.py" entries --entries "$ENTRIES" --k tl --through "$CUTOFF" --label "$LABEL" --out "$OUT/pit" \
    $( [ "${FAST:-0}" != 1 ] && opt --minutes "$MINUTES" ) $( [ "${FAST:-0}" != 1 ] && opt --candidates "$CANDS" )
fi

# 9. G10 — the same dates through both exports (only with a richer export)
[ -n "$RICH_DIR" ] && step pit_overlap $PY "$HERE/pit_lint.py" overlap --era-a "$ERA_DIR" --era-b "$RICH_DIR" --out "$OUT/pit"

# 10. G8 — the trade list this read will quote: sealed-trade dependence + artifact touch
if [ -n "$TRADES" ] && [ -f "$OUT/price/${LABEL}_flags.tsv" ]; then
  step trade_impact $PY "$HERE/trade_impact.py" --flags "$OUT/price/${LABEL}_flags.tsv" --export "$EXPORT" --trades "$TRADES" --label "$LABEL" --cutoff "$CUTOFF" --kind c0
fi

# ---- verdict ------------------------------------------------------------------------------------------------------------------
{
  echo; echo "step rc table:"; for i in "${!STEPS[@]}"; do printf '  %-20s rc=%s\n' "${STEPS[$i]}" "${RCS[$i]}"; done
} | tee -a "$OUT/run_all.log"
$PY "$HERE/gate_verdict.py" "$OUT" --label "$LABEL" | tee "$OUT/verdict.txt"
VRC=${PIPESTATUS[0]}
for rc in "${RCS[@]}"; do [ "$rc" -ne 0 ] && [ "$rc" -ne 3 ] && { echo "a lens crashed (rc not 0/3) — the verdict above carries it as REFUSE; see the step table"; exit 1; }; done
exit "$VRC"
