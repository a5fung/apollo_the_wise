"""#594 — does "did the gap clear multi-year overhead supply" separate his chart rulings?

PRE-DECLARED BEFORE ANY NUMBER WAS COMPUTED (2026-09-06). With ~25 labelled dates and a free
hand over five years of bars, a favourable cutline is trivially findable and worthless, so the
measure is fixed here in writing first:

  clearance_pct(ticker, date) =
      the percentage of DAILY HIGHS in the prior window that the GAP DAY'S CLOSE exceeds.

  window   = every stored bar strictly before the gap day, up to 5 years (all we now hold).
  measure  = ONE number. No tuning knobs, no thresholds, no alternates tried.
  compare  = median clearance_pct for his BAD_CHART dates vs his approved dates
             (GOOD_CHART, OKISH_CHART, and any WRONG_DAY `better_date` he STATED).

WHY THIS MEASURE: it is the literal reading of what he said. RNG — "a long base since 2022 and
this gap cleared most of it into top of previous range highs over multiple years" — should sit
near 100%. NVTX — "a double top from Oct 2025 that it didn't clear" — should sit lower, with
supply still overhead.

⚠ This was IMPOSSIBLE before 2026-09-06: history began 2025-08-04, so RNG's 2022 base did not
exist in our data. The 0.496 structure-read null was measured on that same 13-month window.

READ-ONLY. Computes, prints, writes nothing.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.market_intelligence.db import get_pool  # noqa: E402
# The fixture lives in tests/, which is not in the container image, so load it by PATH —
# from the repo when running on a dev box, or from /tmp when copied alongside this probe.
import importlib.util  # noqa: E402


def _load_fixture():
    for cand in (Path(__file__).resolve().parents[2] / "tests/fixtures/must_not_trade_charts.py",
                 Path("/tmp/must_not_trade_charts.py")):
        if cand.exists():
            spec = importlib.util.spec_from_file_location("_charts_fixture", cand)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise SystemExit("chart-ruling fixture not found on either path")


F = _load_fixture()

WINDOW_YEARS = 5


async def clearance(conn, ticker: str, d: date):
    row = await conn.fetchrow(
        """
        WITH prior AS (
            SELECT high_price FROM mi_daily_closes
            WHERE ticker = $1 AND trade_date < $2
              AND trade_date >= $2 - ($3 || ' years')::interval
              AND high_price IS NOT NULL
        ), gap AS (
            SELECT close FROM mi_daily_closes WHERE ticker = $1 AND trade_date = $2
        )
        SELECT (SELECT close FROM gap) AS gap_close,
               (SELECT COUNT(*) FROM prior) AS n_prior,
               (SELECT COUNT(*) FROM prior, gap WHERE prior.high_price < gap.close) AS n_below
        """,
        ticker, d, str(WINDOW_YEARS),
    )
    if not row or row["gap_close"] is None or not row["n_prior"]:
        return None, row["n_prior"] if row else 0
    return 100.0 * row["n_below"] / row["n_prior"], row["n_prior"]


async def main() -> None:
    pool = await get_pool()
    approved, bad, other = [], [], []
    async with pool.acquire() as conn:
        for r in F.CHART_RULINGS:
            pct, n = await clearance(conn, r.ticker, date.fromisoformat(r.alert_date))
            rec = (r.ticker, r.alert_date, r.verdict, pct, n)
            (bad if r.verdict == F.BAD_CHART else
             approved if r.verdict in (F.GOOD_CHART, F.OKISH_CHART) else other).append(rec)
            # a better_date he STATED is an approved date in its own right
            if (r.better_date and r.better_date_provenance == F.STATED):
                p2, n2 = await clearance(conn, r.ticker, date.fromisoformat(r.better_date))
                approved.append((r.ticker, r.better_date, "STATED_better_date", p2, n2))

    def show(title, rows):
        print(f"\n{title}")
        vals = []
        for t, d, v, p, n in sorted(rows, key=lambda x: -(x[3] or -1)):
            pp = f"{p:5.1f}%" if p is not None else "  n/a"
            print(f"  {t:6} {d}  {pp}  ({n:4} prior bars)  {v}")
            if p is not None:
                vals.append(p)
        if vals:
            vals.sort()
            med = vals[len(vals)//2] if len(vals) % 2 else (vals[len(vals)//2-1]+vals[len(vals)//2])/2
            print(f"  -> n={len(vals)}  median {med:.1f}%")
        return vals

    a = show("APPROVED by him (GOOD_CHART / OKISH_CHART / STATED better_date)", approved)
    b = show("BAD_CHART", bad)
    show("OTHER verdicts (WRONG_DAY's own date, WRONG_STAGE, etc.)", other)
    if a and b:
        a.sort(); b.sort()
        ma = a[len(a)//2] if len(a) % 2 else (a[len(a)//2-1]+a[len(a)//2])/2
        mb = b[len(b)//2] if len(b) % 2 else (b[len(b)//2-1]+b[len(b)//2])/2
        print(f"\nSEPARATION  approved median {ma:.1f}%  vs  bad median {mb:.1f}%"
              f"   gap {ma-mb:+.1f} points   (n={len(a)} vs {len(b)})")


if __name__ == "__main__":
    asyncio.run(main())
