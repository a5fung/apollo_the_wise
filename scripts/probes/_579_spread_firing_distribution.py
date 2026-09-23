#!/usr/bin/env python3
"""#579 step (b) — MEASURE how often a strength-map spread would speak, before any threshold exists.

The task's own DoD: *"applied first to the strength-map spreads, with the firing distribution
MEASURED before any threshold is chosen (P2 — price it like the gap floor, do not guess)"*, and
*"a stated silence rate"*. This is that measurement and nothing else — it proposes no rule, changes
no code, and writes nothing.

THE PRIMITIVE IS NOT INVENTED HERE. `strength_map._dominance_band` already does
unusual-against-its-own-history for BTC dominance: the band is the MEDIAN ABSOLUTE 30-day move over
the recent 60 days, floored, with a `widened` flag when recent/baseline >= 1.5. The task says
generalise the one that works, so the same shape is applied to each complex's direction spread.

Read-only against `mi_daily_closes`. Run:
    python scripts/probes/_579_spread_firing_distribution.py            # uses a cached pull
    python scripts/probes/_579_spread_firing_distribution.py --refresh  # re-pulls from prod
"""
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.market_intelligence.strength_map import (  # noqa: E402
    COMPLEXES,
    _DOM_BAND_FLOOR,
    _DOM_BASELINE_DAYS,
    _DOM_RECENT_DAYS,
    _DOM_WIDEN_RATIO,
)

_CACHE = Path(__file__).with_name("_579_closes.tsv")
_HOST = "apollo@87.99.134.162"
_MOVE_DAYS = 30          # the horizon the crypto lane speaks over
_WINDOW_BARS = 21        # ~1 month of trading days, the window the operator was shown


def _pull() -> None:
    tickers = sorted({t for c in COMPLEXES for k in ("anchor", "senior", "junior") for t in c[k]})
    sql = ("SELECT ticker, trade_date, close FROM mi_daily_closes WHERE ticker = ANY(ARRAY["
           + ",".join(f"'{t}'" for t in tickers) + "]) ORDER BY ticker, trade_date")
    out = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=15", _HOST,
         f"docker exec apollo-postgres psql -U apollo -d apollo -tAF'\t' -c \"{sql}\""],
        capture_output=True, text=True, timeout=180)
    _CACHE.write_text(out.stdout)
    print(f"pulled {len(out.stdout.splitlines())} rows -> {_CACHE}")


def _load() -> dict:
    series: dict[str, list[tuple[str, float]]] = {}
    for line in _CACHE.read_text().splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or not parts[2]:
            continue
        series.setdefault(parts[0], []).append((parts[1], float(parts[2])))
    return series


def _basket_ret(series, tickers, i, bars):
    """Mean trailing return over `bars` for the basket, as of index i. None if any leg is short."""
    rets = []
    for t in tickers:
        s = series.get(t)
        if not s or i >= len(s) or i - bars < 0 or s[i - bars][1] == 0:
            return None
        rets.append((s[i][1] / s[i - bars][1] - 1) * 100.0)
    return statistics.fmean(rets) if rets else None


def main(refresh: bool) -> int:
    if refresh or not _CACHE.exists():
        _pull()
    series = _load()
    print(f"{'complex':<16}{'days':>6}{'band':>8}{'fires':>7}{'rate':>8}   silence")
    print("-" * 62)
    for c in COMPLEXES:
        anchor, expr = c["anchor"], c["senior"] + c["junior"]
        if not anchor or not expr:
            print(f"{c['name']:<16}{'':>6}{'':>8}{'':>7}{'':>8}   no anchor/expression pair — skipped")
            continue
        dates = [d for d, _ in series[expr[0]]]
        spreads = []
        for i in range(len(dates)):
            a = _basket_ret(series, anchor, i, _WINDOW_BARS)
            e = _basket_ret(series, expr, i, _WINDOW_BARS)
            spreads.append((dates[i], (e - a) if (a is not None and e is not None) else None))
        vals = [(d, v) for d, v in spreads if v is not None]
        if len(vals) < _DOM_BASELINE_DAYS:
            print(f"{c['name']:<16}{len(vals):>6}   too little history")
            continue
        fires = 0
        judged = 0
        for j in range(_DOM_BASELINE_DAYS, len(vals)):
            recent = [abs(vals[k][1] - vals[k - _MOVE_DAYS][1])
                      for k in range(j - _DOM_RECENT_DAYS, j) if k - _MOVE_DAYS >= 0]
            if not recent:
                continue
            band = max(statistics.median(recent), _DOM_BAND_FLOOR)
            move = abs(vals[j][1] - vals[j - _MOVE_DAYS][1])
            judged += 1
            fires += int(move >= band)
        rate = fires / judged * 100 if judged else float("nan")
        print(f"{c['name']:<16}{judged:>6}{band:>8.2f}{fires:>7}{rate:>7.1f}%   "
              f"silent {100 - rate:.1f}% of days")
    print("\nband = median |30d move| over the trailing 60 judged days, floored at "
          f"{_DOM_BAND_FLOOR} — the SAME shape as `_dominance_band`, not a new threshold.")
    print(f"widen flag would use recent/baseline >= {_DOM_WIDEN_RATIO} over {_DOM_BASELINE_DAYS}d.")
    return 0


if __name__ == "__main__":
    sys.exit(main("--refresh" in sys.argv))
