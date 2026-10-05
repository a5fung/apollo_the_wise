"""#594 sample #3 (2026-10-05): render each name's point-in-time daily chart (bars up to the day BEFORE
the date) with the live chart renderer, read-only. Writes PNGs to /tmp/sample3_charts/."""
import asyncio
import os
from datetime import date

from agents.market_intelligence.chart_axis import render_prior_day_chart

NAMES = [("AEVA", "2026-08-06"), ("RXT", "2026-06-16"), ("BLZE", "2026-08-04"), ("RUM", "2026-06-04"),
         ("HPE", "2026-06-02"), ("CDNA", "2026-07-16"), ("MAN", "2026-07-16"), ("IBTA", "2026-08-04"),
         ("KRO", "2026-08-06"), ("HURN", "2026-07-29")]


async def main():
    os.makedirs("/tmp/sample3_charts", exist_ok=True)
    for t, d in NAMES:
        png, n_daily = await render_prior_day_chart(t, date.fromisoformat(d))
        if not png:
            print(t, d, "NO CHART:", n_daily, "daily bars")
            continue
        with open(f"/tmp/sample3_charts/{t}_{d}.png", "wb") as f:
            f.write(png)
        print(t, d, "ok", len(png), "bytes,", n_daily, "bars")


asyncio.run(main())
