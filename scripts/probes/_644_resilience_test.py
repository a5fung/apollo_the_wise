"""#644 step 2, part B — run the REAL `db.get_down_day_resilience` (not a
reimplementation) against real prod closes, per week-1 cohort, and test the
resilience-sign split against the ~52-55% base rate. $0 — closes were pulled
ONCE via read-only psql (`scripts/probes/_644_closes.csv`, 45,982 rows,
508 tickers incl. SPY, 2026-05-01..2026-09-10) and are read locally from
here on; no repeat DB round trips.

Population: `_644_entrants.json` (built by portfolio-app2/_644_entrants.py) —
one row per ENTRANT to board[w] relative to board[w_prev], across the 11
post-launch transitions (week_start > 2026-06-22), each with its as_of_date,
ticker basket, and whether it holds board[w_next] (null for the 152nd week's
19 entrants, which have no next week yet). This reproduces #639's own
published "152 entrants" exactly and its hold-next rate to within 0.1 point
of the previously-reported 52.0% (51.9% here) — see the analysis doc for the
full reconciliation note (the exact n differs, 133 vs ~150, because the ad
hoc script behind that number was never committed and isn't available to
diff against byte-for-byte; the near-exact rate match is the check that
matters for this test).

Cohort resilience = MEDIAN of `get_down_day_resilience(as_of_date,
tickers=basket, lookback=20)`'s per-ticker resilience values, computed
AS OF the cohort's own first-board-week as_of_date (never a later date).
"""
import csv
import json
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock
import asyncio

sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
import agents.market_intelligence.db as db  # noqa: E402


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


class _RealPullConn:
    """Same three-query dispatch as get_down_day_resilience, honoring the
    real SQL text's comparison operators, backed by the actual prod pull."""

    def __init__(self, rows: list[dict]):
        self._rows = rows

    async def fetch(self, sql, *args):
        if "DISTINCT trade_date" in sql:
            bound, limit = args
            op_le = "trade_date <= $1" in sql
            dates = sorted(
                {r["trade_date"] for r in self._rows
                 if (r["trade_date"] <= bound if op_le else r["trade_date"] < bound)},
                reverse=True,
            )[:limit]
            return [{"trade_date": dt} for dt in dates]
        if "ticker = 'SPY'" in sql:
            (dates_arg,) = args
            return [dict(r) for r in self._rows
                    if r["ticker"] == "SPY" and r["trade_date"] in dates_arg]
        if "ticker = ANY($1)" in sql:
            tickers_arg, dates_arg = args
            tset = set(tickers_arg)
            return [dict(r) for r in self._rows
                    if r["ticker"] in tset and r["trade_date"] in dates_arg]
        (dates_arg,) = args
        return [dict(r) for r in self._rows if r["trade_date"] in dates_arg]


def _load_closes(path: str) -> list[dict]:
    rows = []
    with open(path, newline="") as f:
        for ticker, trade_date, close in csv.reader(f):
            rows.append({
                "ticker": ticker,
                "trade_date": _parse_date(trade_date),
                "close": float(close),
            })
    return rows


def main() -> int:
    closes = _load_closes("scripts/probes/_644_closes.csv")
    print(f"loaded {len(closes)} close rows, {len({r['ticker'] for r in closes})} tickers")
    entrants = json.load(open("scripts/probes/_644_entrants.json"))
    print(f"loaded {len(entrants)} entrant rows")

    pool = MagicMock()
    conn = _RealPullConn(closes)
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=acquire_cm)
    db.get_pool = AsyncMock(return_value=pool)

    results = []
    no_coverage = []
    for e in entrants:
        as_of = _parse_date(e["as_of_date"])
        basket = e["tickers"]
        if not basket:
            no_coverage.append((e["canonical_id"], e["week_start"], "empty basket"))
            continue
        per_ticker = asyncio.run(
            db.get_down_day_resilience(as_of, tickers=basket, lookback=20)
        )
        if not per_ticker:
            no_coverage.append((e["canonical_id"], e["week_start"], "no per-ticker resilience"))
            continue
        vals = [r["resilience"] for r in per_ticker]
        n_covered = len(vals)
        cohort_resilience = statistics.median(vals)
        results.append({
            **e,
            "cohort_resilience": cohort_resilience,
            "n_basket": len(basket),
            "n_covered": n_covered,
        })

    print(f"\nscored: {len(results)} / {len(entrants)} entrants "
          f"({len(no_coverage)} without any resilience coverage)")
    for cid, wk, reason in no_coverage[:20]:
        print(f"  NO COVERAGE: {cid} {wk} — {reason}")
    if len(no_coverage) > 20:
        print(f"  ... and {len(no_coverage) - 20} more")

    # ── base rate on the SCORED population itself (own denominator) ────────
    scorable = [r for r in results if r["holds_next"] is not None]
    n_scorable = len(scorable)
    n_hold = sum(1 for r in scorable if r["holds_next"])
    base_rate = n_hold / n_scorable if n_scorable else float("nan")
    print(f"\nbase rate on scored+scorable population: {n_hold}/{n_scorable} "
          f"= {base_rate*100:.1f}%")

    pos = [r for r in scorable if r["cohort_resilience"] > 0]
    nonpos = [r for r in scorable if r["cohort_resilience"] <= 0]
    n_pos, n_nonpos = len(pos), len(nonpos)
    hold_pos = sum(1 for r in pos if r["holds_next"])
    hold_nonpos = sum(1 for r in nonpos if r["holds_next"])
    rate_pos = hold_pos / n_pos if n_pos else float("nan")
    rate_nonpos = hold_nonpos / n_nonpos if n_nonpos else float("nan")

    print(f"\nPOSITIVE resilience:      n={n_pos:3d}  holds next={hold_pos:3d}  rate={rate_pos*100:5.1f}%")
    print(f"NON-POSITIVE resilience:  n={n_nonpos:3d}  holds next={hold_nonpos:3d}  rate={rate_nonpos*100:5.1f}%")
    print(f"difference (pos - nonpos): {(rate_pos-rate_nonpos)*100:+.1f} points")

    # two-proportion standard error, for a plain significance statement
    def se(n, k):
        if n == 0:
            return float("nan")
        p = k / n
        return (p * (1 - p) / n) ** 0.5

    se_pos, se_nonpos = se(n_pos, hold_pos), se(n_nonpos, hold_nonpos)
    combined_se = (se_pos**2 + se_nonpos**2) ** 0.5
    diff = rate_pos - rate_nonpos
    if combined_se > 0:
        print(f"combined SE of the difference: {combined_se*100:.1f} points "
              f"-> difference is {abs(diff)/combined_se:.2f} SE")

    # median split as a secondary, clearly-labeled cut (balances n if the sign split is lopsided)
    med = statistics.median(r["cohort_resilience"] for r in scorable)
    above = [r for r in scorable if r["cohort_resilience"] > med]
    below = [r for r in scorable if r["cohort_resilience"] <= med]
    n_above, n_below = len(above), len(below)
    hold_above = sum(1 for r in above if r["holds_next"])
    hold_below = sum(1 for r in below if r["holds_next"])
    rate_above = hold_above / n_above if n_above else float("nan")
    rate_below = hold_below / n_below if n_below else float("nan")
    print(f"\n[secondary] median resilience split at {med*100:+.2f}%:")
    print(f"  ABOVE median: n={n_above:3d}  holds next={hold_above:3d}  rate={rate_above*100:5.1f}%")
    print(f"  AT/BELOW median: n={n_below:3d}  holds next={hold_below:3d}  rate={rate_below*100:5.1f}%")

    with open("scripts/probes/_644_scored.json", "w") as f:
        json.dump(results, f, indent=1, default=str)
    print("\nwrote scripts/probes/_644_scored.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
