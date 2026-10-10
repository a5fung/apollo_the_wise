"""#692 Alpaca/Benzinga source — the ONE $0 raw pull (read-only; no model call, no write).

Runs INSIDE apollo-market (it holds the Polygon + Alpaca keys):
    docker cp pull_news.py apollo-market:/tmp/pull_news.py
    docker cp cells.json   apollo-market:/tmp/cells.json
    docker exec -w /app apollo-market python /tmp/pull_news.py /tmp/cells.json /tmp/news_pull.jsonl
    docker cp apollo-market:/tmp/news_pull.jsonl .

Per cell it calls the SAME collector functions the live scan calls — get_polygon_news(on_or_before=
day, lookback 14, limit 20) and get_alpaca_news(to_date=day, lookback 14, limit 20) — and stores
the RAW items, so the candidate selection / merge can be re-run locally any number of times for $0
(capture once, read many). cells.json = {"cells": [[ticker, "YYYY-MM-DD"], ...],
"weekly": [[ticker, "YYYY-MM-DD" (week end)], ...]}; weekly cells use a 7-day lookback, limit 50.
"""
import asyncio
import json
import sys
from datetime import date

from agents.market_intelligence import collector


async def main(cells_path: str, out_path: str) -> None:
    spec = json.load(open(cells_path))
    n = 0
    with open(out_path, "w") as out:
        for kind, rows, lookback, limit in (("cell", spec["cells"], 14, 20),
                                            ("weekly", spec.get("weekly", []), 7, 50)):
            for ticker, day in rows:
                d = date.fromisoformat(day)
                poly = await collector.get_polygon_news(
                    ticker, lookback_days=lookback, on_or_before=d, limit=limit)
                alp = await collector.get_alpaca_news(
                    ticker, to_date=d, lookback_days=lookback, limit=limit, include_content=False)
                out.write(json.dumps({"kind": kind, "ticker": ticker, "day": day, "lookback": lookback,
                                      "polygon": poly, "alpaca": alp}, default=str) + "\n")
                out.flush()
                n += 1
                await asyncio.sleep(0.4)     # stay well under Alpaca's 200 requests/minute
    print(f"wrote {n} cells to {out_path}")


asyncio.run(main(sys.argv[1], sys.argv[2]))
