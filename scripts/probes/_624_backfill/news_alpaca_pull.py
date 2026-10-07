"""#624 news step 1 (supplementary cross-check) — the SAME windows as news_pull.py, on the source the LIVE grader reads
(Alpaca News = Benzinga). Free. READ-ONLY, no DB writes, one single-threaded worker paced 0.5 s (< 120 calls/min, well
under Alpaca's 200/min), run after hours. Keys are read from the container env and sent only in headers; never printed.

Reads /tmp/_624bf/news_list.txt (ticker|D|HH:MM|prev_session|set). Window: [prior session 16:00 ET, D HH:MM ET].
Writes /tmp/_624bf/news_alpaca_raw.jsonl (resumable) + news_alpaca_raw_log.txt.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone, time as dtime, date
from zoneinfo import ZoneInfo

import httpx

ET = ZoneInfo("America/New_York")
UTC = timezone.utc
URL = "https://data.alpaca.markets/v1beta1/news"
KID = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY", "")
SEC = os.environ.get("ALPACA_PAPER_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY", "")
HDR = {"APCA-API-KEY-ID": KID, "APCA-API-SECRET-KEY": SEC}
PACE = 0.5


def iso(d):
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def main():
    lst = sys.argv[1] if len(sys.argv) > 1 else "/tmp/_624bf/news_list.txt"
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/_624bf/news_alpaca_raw.jsonl"
    logp = out.replace(".jsonl", "_log.txt")
    rows = [l.rstrip("\n").split("|") for l in open(lst) if l.strip()]
    done = set()
    if os.path.exists(out):
        for l in open(out):
            try:
                r = json.loads(l)
                done.add((r["ticker"], r["D"]))
            except Exception:  # noqa: BLE001
                pass
    async with httpx.AsyncClient(timeout=40) as client:
        with open(out, "a") as of, open(logp, "a") as lf:
            for tk, d, tick, pd_, sset in rows:
                if (tk, d) in done:
                    continue
                hh, mm = (int(x) for x in tick.split(":")[:2])
                end = datetime.combine(date.fromisoformat(d), dtime(hh, mm), tzinfo=ET)
                start = datetime.combine(date.fromisoformat(pd_), dtime(16, 0), tzinfo=ET)
                params = {"symbols": tk, "start": iso(start), "end": iso(end), "limit": 50, "sort": "asc",
                          "include_content": "false"}
                items, pages, err = [], 0, None
                while pages < 4:
                    js = None
                    for attempt in range(4):
                        try:
                            r = await client.get(URL, params=params, headers=HDR)
                        except httpx.TransportError as e:
                            err = f"transport:{type(e).__name__}"
                            await asyncio.sleep(2 * (attempt + 1))
                            continue
                        if r.status_code == 429:
                            err = "http429"
                            await asyncio.sleep(15 * (attempt + 1))
                            continue
                        if r.status_code != 200:
                            err = f"http{r.status_code}"
                            break
                        js = r.json()
                        break
                    await asyncio.sleep(PACE)
                    if js is None:
                        break
                    items += js.get("news") or []
                    tok = js.get("next_page_token")
                    pages += 1
                    if not tok:
                        break
                    params["page_token"] = tok
                if err and not items and js is None:
                    lf.write(f"{tk}|{d}|FAIL|{err}\n"); lf.flush()
                    continue
                arts = [{"published_utc": a.get("created_at", ""), "publisher": a.get("source", ""),
                         "title": a.get("headline", "") or "", "description": a.get("summary", "") or "",
                         "article_url": a.get("url", ""), "n_tickers": len(a.get("symbols") or []),
                         "tickers": a.get("symbols") or []} for a in items]
                of.write(json.dumps({"ticker": tk, "D": d, "tick": tick, "prev_session": pd_, "set": sset,
                                     "window_utc": [iso(start), iso(end)], "articles": arts}) + "\n")
                of.flush()
                lf.write(f"{tk}|{d}|ok|{len(arts)}\n"); lf.flush()
    print("done")


asyncio.run(main())
