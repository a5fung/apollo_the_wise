"""Step 0 of #119: fetch Polygon news corpus for the FP/TP cases that
motivated Path B proximity check.

Dumps each article's title + per-ticker sentiment_reasoning so we can
read the corpus before designing the proximity rule. Critical insight
expected: in FP cases (QBTS/RGTI/INFQ), the M&A keyword in
sentiment_reasoning refers to a DIFFERENT company (IonQ), not the
filtering ticker. In TP cases (D, EL), the keyword is sentence-adjacent
to the ticker.

Run: docker exec apollo-market python -m scripts._b119_mna_proximity_corpus
"""
import asyncio
import json
import os

import httpx

CASES = [
    # TPs — keyword expected to be tight to ticker
    {"ticker": "D",    "label": "TP", "window": ("2026-05-15", "2026-05-17"), "title_hint": "Dominion In Talks"},
    {"ticker": "EL",   "label": "TP", "window": ("2026-04-01", "2026-05-22"), "title_hint": "Walks Away From Merger"},
    # FPs — keyword expected to be far from ticker (about a different company)
    {"ticker": "QBTS", "label": "FP", "window": ("2026-05-10", "2026-05-12"), "title_hint": "IonQ Rises"},
    {"ticker": "RGTI", "label": "FP", "window": ("2026-05-10", "2026-05-12"), "title_hint": "IonQ Rises"},
    {"ticker": "INFQ", "label": "FP", "window": ("2026-05-01", "2026-05-22"), "title_hint": "Infleqtion"},
    {"ticker": "IREN", "label": "FP", "window": ("2026-04-01", "2026-05-22"), "title_hint": "Acquisition of Nostrum"},
]


async def fetch_corpus():
    api_key = os.environ["POLYGON_API_KEY"]
    out = []
    async with httpx.AsyncClient(timeout=15) as cl:
        for case in CASES:
            r = await cl.get(
                "https://api.polygon.io/v2/reference/news",
                params={
                    "ticker": case["ticker"],
                    "published_utc.gte": case["window"][0],
                    "published_utc.lte": case["window"][1],
                    "limit": 30,
                    "apiKey": api_key,
                },
            )
            data = r.json()
            target = None
            for art in data.get("results", []):
                if case["title_hint"] in (art.get("title") or ""):
                    target = art
                    break
            if target is None:
                out.append({**case, "found": False})
                continue

            # Pull the per-ticker insight reasoning
            insights = target.get("insights") or []
            ticker_insight = next(
                (i for i in insights if i.get("ticker") == case["ticker"]),
                None,
            )
            out.append({
                **case,
                "found": True,
                "title": target.get("title"),
                "description": (target.get("description") or "")[:500],
                "ticker_in_insights": ticker_insight is not None,
                "sentiment": ticker_insight.get("sentiment") if ticker_insight else None,
                "sentiment_reasoning": ticker_insight.get("sentiment_reasoning") if ticker_insight else None,
                "insight_tickers": [i.get("ticker") for i in insights],
            })

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    asyncio.run(fetch_corpus())
