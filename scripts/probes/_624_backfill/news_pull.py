"""#624 backfill — pre-entry NEWS pull (Polygon /v2/reference/news), run INSIDE apollo-market. $0, READ-ONLY, no DB writes.

The key lives in the container env and is sent only in an Authorization header (never in a URL, never printed).
It does NOT go through collector._polygon_get / get_polygon_news: those write an mi_audit_log row on a sustained
failure and clamp the window to whole dates; this probe needs an exact timestamp window and must write nothing.

Reads /tmp/_624bf/news_list.txt  (ticker|D|HH:MM|prev_session_date|set), one call (plus next_url pages) per row.
Window (no look-ahead): published_utc in [prior session 16:00 ET, D HH:MM ET].  The same call also asks for the 7
calendar days before that window ("earlier_7d" — titles only, to see whether the catalyst is older than the window).
Writes /tmp/_624bf/news_raw.jsonl (resumable: rows already in the log are skipped) + /tmp/_624bf/news_log.txt.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone, time as dtime, date
from zoneinfo import ZoneInfo

import httpx

ET = ZoneInfo("America/New_York")
UTC = timezone.utc
BASE = "https://api.polygon.io"
D = "/tmp/_624bf"
PACE = 0.3
KEY = os.environ.get("POLYGON_API_KEY", "")
HDR = {"Authorization": f"Bearer {KEY}"}
MAXPAGES = 4


def iso(dtm: datetime) -> str:
    return dtm.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def get(client, url, params=None):
    last = None
    for attempt in range(4):
        try:
            r = await client.get(url, params=params, headers=HDR)
        except httpx.TransportError as e:
            last = f"transport:{type(e).__name__}"
            await asyncio.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 429:
            last = "http429"
            await asyncio.sleep(15 * (attempt + 1))
            continue
        if r.status_code != 200:
            return r.status_code, None, f"http{r.status_code}"
        try:
            return 200, r.json(), None
        except Exception as e:  # noqa: BLE001
            return 200, None, f"json:{type(e).__name__}"
    return None, None, last or "failed"


def slim(a: dict, tk: str, full: bool) -> dict:
    ins = [i for i in (a.get("insights") or []) if str(i.get("ticker", "")).upper() == tk]
    out = {
        "published_utc": a.get("published_utc", ""),
        "publisher": (a.get("publisher") or {}).get("name", ""),
        "title": a.get("title", ""),
        "article_url": a.get("article_url", ""),
        "n_tickers": len(a.get("tickers") or []),
    }
    if full:
        out["description"] = a.get("description", "") or ""
        out["tickers"] = a.get("tickers") or []
        out["keywords"] = a.get("keywords") or []
        out["insight"] = ([{"sentiment": i.get("sentiment"), "reasoning": i.get("sentiment_reasoning", "")}
                           for i in ins][:1])
    return out


async def pull_one(client, tk, d, tick, pd_, sset):
    D_ = date.fromisoformat(d)
    P_ = date.fromisoformat(pd_)
    hh, mm = (int(x) for x in tick.split(":")[:2])
    end = datetime.combine(D_, dtime(hh, mm), tzinfo=ET)
    start = datetime.combine(P_, dtime(16, 0), tzinfo=ET)
    ext = start - timedelta(days=7)
    params = {"ticker": tk, "published_utc.gte": iso(ext), "published_utc.lte": iso(end),
              "limit": 1000, "order": "asc", "sort": "published_utc"}
    url, pages, items, err = f"{BASE}/v2/reference/news", 0, [], None
    while url and pages < MAXPAGES:
        st, js, err = await get(client, url, params if pages == 0 else None)
        await asyncio.sleep(PACE)
        if js is None:
            return None, err, 0
        items += js.get("results") or []
        url = js.get("next_url")
        pages += 1
    win, early = [], []
    s_u, e_u = iso(start), iso(end)
    for a in items:
        p = a.get("published_utc", "")
        if s_u <= p <= e_u:
            win.append(slim(a, tk, True))
        elif p < s_u:
            early.append(slim(a, tk, False))
    rec = {"ticker": tk, "D": d, "tick": tick, "prev_session": pd_, "set": sset,
           "window_utc": [s_u, e_u], "articles": win, "earlier_7d": early,
           "truncated": bool(url)}
    return rec, None, pages


async def worker(name, rows, out_f, log_f, done):
    async with httpx.AsyncClient(timeout=40) as client:
        for tk, d, tick, pd_, sset in rows:
            if (tk, d) in done:
                continue
            rec, err, pages = await pull_one(client, tk, d, tick, pd_, sset)
            if rec is None:
                log_f.write(f"{tk}|{d}|FAIL|{str(err).replace(KEY, '<k>') if KEY else err}\n")
                log_f.flush()
                continue
            out_f.write(json.dumps(rec) + "\n")
            out_f.flush()
            log_f.write(f"{tk}|{d}|ok|{len(rec['articles'])}|{len(rec['earlier_7d'])}|pages={pages}\n")
            log_f.flush()


async def main():
    lst = sys.argv[1] if len(sys.argv) > 1 else f"{D}/news_list.txt"
    out = sys.argv[2] if len(sys.argv) > 2 else f"{D}/news_raw.jsonl"
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
    n = 3
    shards = [rows[i::n] for i in range(n)]
    with open(out, "a") as of, open(logp, "a") as lf:
        await asyncio.gather(*[worker(i, s, of, lf, done) for i, s in enumerate(shards)])
    print(f"rows={len(rows)} previously_done={len(done)}")


asyncio.run(main())
