"""#624 backfill — Polygon fetcher, run INSIDE apollo-market (the key lives in its env; never printed, never copied).

READ-ONLY with respect to prod: it talks to Polygon directly over HTTPS with the key in an Authorization header
(never in a URL, so it cannot leak into a log line), and it does NOT go through collector._polygon_get — that
helper writes an mi_audit_log row on failure, and this probe makes no DB writes at all. $0 (Polygon Starter).

Modes (all resumable from their own log; one call per key; paced >= 0.35 s per worker):
  splits                 -> /tmp/_624bf/splits.json            every US split with execution_date >= 2024-01-02
  minutes <tag>          -> /tmp/_624bf/min_<tag>.tsv          1-min bars 04:00-15:59 ET, adjusted=true, consolidated
                            /tmp/_624bf/log_min_<tag>.txt       ticker|date|n_total|n_kept|status
                            reads /tmp/_624bf/list_min_<tag>.txt (ticker|YYYY-MM-DD per line)
  ref <tag>              -> /tmp/_624bf/ref_<tag>.jsonl        /v3/reference/tickers/{t}?date=D (point-in-time)
                            reads /tmp/_624bf/list_ref_<tag>.txt (ticker|YYYY-MM-DD per line)
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import httpx

ET = ZoneInfo("America/New_York")
BASE = "https://api.polygon.io"
D = "/tmp/_624bf"
PACE = 0.35
KEY = os.environ.get("POLYGON_API_KEY", "")
HDR = {"Authorization": f"Bearer {KEY}"}
REF_KEYS = ("ticker", "name", "type", "active", "market", "locale", "primary_exchange", "currency_name",
            "weighted_shares_outstanding", "share_class_shares_outstanding", "market_cap", "delisted_utc",
            "list_date", "cik", "composite_figi", "share_class_figi")


def _clean(s: str) -> str:
    s = str(s)
    if KEY:
        s = s.replace(KEY, "<k>")
    return s.replace("|", "/").replace("\n", " ")[:80]


async def _get(client: httpx.AsyncClient, path: str, params: dict | None = None):
    """(http_status, json|None, err|None). 3 attempts on 429 / transport errors."""
    last = None
    for attempt in range(3):
        try:
            r = await client.get(path if path.startswith("http") else BASE + path, params=params, headers=HDR)
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


def _load_done(logp: str, ncol: int = 2) -> set:
    done = set()
    if os.path.exists(logp):
        for line in open(logp):
            p = line.rstrip("\n").split("|")
            if len(p) >= ncol:
                done.add(tuple(p[:ncol]))
    return done


async def splits():
    out, n = [], 0
    async with httpx.AsyncClient(timeout=30) as client:
        url, params = "/v3/reference/splits", {"execution_date.gte": "2024-01-02", "limit": 1000,
                                               "sort": "execution_date", "order": "asc"}
        while True:
            st, data, err = await _get(client, url, params)
            n += 1
            if err:
                print("ERROR", err, "after", n, "calls"); sys.exit(2)
            out.extend(data.get("results") or [])
            nxt = data.get("next_url")
            if not nxt:
                break
            url, params = nxt, None
            await asyncio.sleep(PACE)
    json.dump(out, open(f"{D}/splits.json", "w"))
    print("calls", n, "splits", len(out))


async def minutes(tag: str):
    lst, outp, logp = f"{D}/list_min_{tag}.txt", f"{D}/min_{tag}.tsv", f"{D}/log_min_{tag}.txt"
    done = _load_done(logp)
    keys = [tuple(x.strip().split("|")) for x in open(lst) if x.strip()]
    fo, fl = open(outp, "a"), open(logp, "a")
    async with httpx.AsyncClient(timeout=30) as client:
        for i, (t, d) in enumerate(keys):
            if (t, d) in done:
                continue
            t0 = time.monotonic()
            st, data, err = await _get(client, f"/v2/aggs/ticker/{t}/range/1/minute/{d}/{d}",
                                       {"adjusted": "true", "sort": "asc", "limit": 50000})
            bars = (data or {}).get("results") or []
            kept = 0
            for b in bars:
                m = datetime.fromtimestamp(b["t"] / 1000, tz=ET)
                if m.date().isoformat() != d or not (dtime(4, 0) <= m.time() < dtime(16, 0)):
                    continue
                fo.write(f"{t}|{m.strftime('%Y-%m-%d %H:%M')}|{b.get('o')}|{b.get('h')}|{b.get('l')}|{b.get('c')}|{b.get('v')}\n")
                kept += 1
            fl.write(f"{t}|{d}|{len(bars)}|{kept}|{'ok' if err is None else _clean(err)}\n")
            if i % 25 == 0:
                fo.flush(); fl.flush()
            el = time.monotonic() - t0
            if el < PACE:
                await asyncio.sleep(PACE - el)
    fo.close(); fl.close()
    open(f"{D}/done_min_{tag}", "w").write("done\n")


async def ref(tag: str):
    lst, outp = f"{D}/list_ref_{tag}.txt", f"{D}/ref_{tag}.jsonl"
    done = set()
    if os.path.exists(outp):
        for line in open(outp):
            try:
                j = json.loads(line); done.add((j["t"], j["d"]))
            except Exception:  # noqa: BLE001
                pass
    keys = [tuple(x.strip().split("|")) for x in open(lst) if x.strip()]
    fo = open(outp, "a")
    async with httpx.AsyncClient(timeout=30) as client:
        for i, (t, d) in enumerate(keys):
            if (t, d) in done:
                continue
            t0 = time.monotonic()
            st, data, err = await _get(client, f"/v3/reference/tickers/{t}", {"date": d})
            res = (data or {}).get("results") or {}
            fo.write(json.dumps({"t": t, "d": d, "http": st, "err": None if err is None else _clean(err),
                                 "r": {k: res.get(k) for k in REF_KEYS} if res else None}) + "\n")
            if i % 25 == 0:
                fo.flush()
            el = time.monotonic() - t0
            if el < PACE:
                await asyncio.sleep(PACE - el)
    fo.close()
    open(f"{D}/done_ref_{tag}", "w").write("done\n")


if __name__ == "__main__":
    os.makedirs(D, exist_ok=True)
    if not KEY:
        print("no key in env"); sys.exit(3)
    mode = sys.argv[1]
    if mode == "splits":
        asyncio.run(splits())
    elif mode == "minutes":
        asyncio.run(minutes(sys.argv[2]))
    elif mode == "ref":
        asyncio.run(ref(sys.argv[2]))
