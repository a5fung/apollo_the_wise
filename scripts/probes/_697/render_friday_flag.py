"""#697 item 1: render the repaired Friday 'Flag Bases' section from STORED rows (q4_friday_boards.out).

No prod access: reads the captured file, feeds each Friday's stored COILED / TIGHTENING rows through the
REAL `friday_watchlist._fetch_flag` (fake pool) with the flag_continuation strategy DISABLED (as in prod), and
prints the lines the section would carry. Run from the repo root:
    python scripts/probes/_697/render_friday_flag.py > scripts/probes/_697/render_friday_flag.out
"""
import asyncio
import os
from collections import OrderedDict
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from agents.market_intelligence import friday_watchlist as fw

HERE = os.path.dirname(os.path.abspath(__file__))


def _load():
    by_friday: "OrderedDict[str, list[dict]]" = OrderedDict()
    scan_of: dict[str, str] = {}
    with open(os.path.join(HERE, "q4_friday_boards.out")) as fh:
        header = fh.readline().rstrip("\n").split("\t")
        for ln in fh:
            if ln.startswith("("):
                continue
            rec = dict(zip(header, ln.rstrip("\n").split("\t")))
            by_friday.setdefault(rec["friday"], [])
            scan_of[rec["friday"]] = rec["scan_date"]
            if not rec["ticker"]:
                continue
            f = lambda k: float(rec[k]) if rec[k] != "" else None  # noqa: E731
            by_friday[rec["friday"]].append({
                "ticker": rec["ticker"], "stage": rec["stage"], "base_age": int(rec["base_age"]),
                "runup_pct": f("runup_pct"), "range_contraction_ratio": f("range_contraction_ratio"),
                "vol_contraction_ratio": f("vol_contraction_ratio"), "breakout_close": None, "base_high": None,
                "fresh_tight_fires": rec["fresh_tight_fires"] == "true",
                "fresh_2bar_tr_pct": f("fresh_2bar_tr_pct"), "atr14_pct": f("atr14_pct"),
            })
    return by_friday, scan_of


async def main():
    by_friday, scan_of = _load()
    fw.should_run = AsyncMock(return_value=False)            # flag_continuation is deprecated / enabled=false in prod
    total_names = nonempty = 0
    for friday, rows in by_friday.items():
        conn = MagicMock()
        conn.fetchval = AsyncMock(return_value=date.fromisoformat(scan_of[friday]))
        conn.fetch = AsyncMock(return_value=rows)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=None)
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=cm)
        fw.get_pool = AsyncMock(return_value=pool)
        out = await fw._fetch_flag(7)
        merged = fw._merge_sources([out])
        print(f"== Friday {friday} (scan {scan_of[friday]}) - {len(out)} names"
              f"{'  [BEFORE the fix: section was EMPTY]' if out else '  [board empty - correctly empty]'}")
        for r in merged:
            print(f"   • {r['ticker']} — {fw._format_chip(r)}")
        total_names += len(out)
        nonempty += 1 if out else 0
    print(f"\n{nonempty} of {len(by_friday)} Fridays render a non-empty section; {total_names} names in all.")


asyncio.run(main())
