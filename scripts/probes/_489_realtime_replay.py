"""#489 Phase-0 replay — quantify the in-window-crosser class the Polygon feed delay misses.

Read-only. Reconstructs, per historical scan tick, the DELAYED gap (price at tick-LAG) vs the
REAL-TIME gap (price at tick) from Polygon 1-min bars, and counts names that really crossed the
10% floor INSIDE the 9:31-9:44 ORB window while the delayed feed still showed <10% (the IREN class
Pass-2 exists to catch) + the superset-threshold coverage of that class.

Assumptions: LAG_MIN feed lag (measured ~15-17; sensitivity printed). prev_close = prior trading
day's grouped-daily close. Candidate pre-filter mirrors the scan's silent gates (prev_close>=$5,
prev_vol>=50k) + day-high gap >= SCREEN_HIGH_PCT (a name that never reached ~9% intraday can't be a
10% crosser). Run: docker exec -i apollo-market python3 - < this_file
"""
import os, requests, datetime, time
from datetime import timedelta, date as ddate
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
KEY = os.environ["POLYGON_API_KEY"]
S = requests.Session()
LAG_MIN = 16
MIN_GAP = 10.0
SUPERSETS = [5, 6, 7, 8]
SCREEN_HIGH_PCT = 9.0
NDAYS = 25
START = ddate(2026, 7, 18)          # last full trading day before today (7/20 is partial/in-progress)
WIN = [9 * 60 + 31, 9 * 60 + 35, 9 * 60 + 40]   # in-window scan ticks
WIN_LAST = 9 * 60 + 44


def pget(path, params=None):
    p = dict(params or {}); p["apiKey"] = KEY
    for _ in range(4):
        try:
            r = S.get(f"https://api.polygon.io{path}", params=p, timeout=40)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(2); continue
        except Exception:
            time.sleep(1)
    return {}


def scan_ticks():
    out, h, m = [], 7, 0
    while (h, m) <= (9, 55):
        out.append(h * 60 + m)
        m += 5
        if m >= 60:
            h += 1; m = 0
    out.append(9 * 60 + 31)
    return sorted(set(out))


TICKS = scan_ticks()

# 0. common-stock/ADR universe (mirror the real scan's mi_security_types CS/ADRC gate) via Polygon reference
CS = set()
for typ in ("CS", "ADRC"):
    cur = None
    while True:
        pr = {"type": typ, "market": "stocks", "active": "true", "limit": "1000"}
        if cur:
            pr["cursor"] = cur
        d = pget("/v3/reference/tickers", pr)
        for r in d.get("results", []):
            if r.get("ticker"):
                CS.add(r["ticker"])
        nx = d.get("next_url")
        if not nx:
            break
        import urllib.parse as _u
        cur = _u.parse_qs(_u.urlparse(nx).query).get("cursor", [None])[0]
        if not cur:
            break
print(f"common-stock/ADR universe: {len(CS)} tickers")
DOLLAR_VOL_MIN = 5_000_000   # liquidity proxy (strips micro-cap pumps the mcap/ADV$ gates would drop)

# 1. collect NDAYS trading days (grouped-daily non-empty), oldest-first, with prior-day closes
days, d = [], START
while len(days) < NDAYS + 1 and d > ddate(2026, 1, 1):
    g = pget(f"/v2/aggs/grouped/locale/us/market/stocks/{d.isoformat()}", {"adjusted": "true"})
    res = g.get("results")
    if res:
        days.append((d.isoformat(), {r["T"]: r for r in res if "T" in r}))
    d -= timedelta(days=1)
days.reverse()
print(f"trading days: {len(days)} ({days[0][0]}..{days[-1][0]}) | LAG={LAG_MIN}min\n")

missed, cover = [], {s: [] for s in SUPERSETS}
fan = {s: [] for s in SUPERSETS}

for i in range(1, len(days)):
    ds, gd = days[i]
    _, gp = days[i - 1]
    cands = []
    for t, row in gd.items():
        if "." in t or len(t) > 5:
            continue
        prev = gp.get(t)
        if not prev:
            continue
        if t not in CS:                      # common-stock/ADR only (real scan's mi_security_types gate)
            continue
        pc, pv, hi = prev.get("c"), prev.get("v"), row.get("h")
        if not (pc and pc >= 5 and pv and pv >= 50000 and hi):
            continue
        if pc * pv < DOLLAR_VOL_MIN:          # liquidity proxy for the mcap>=$500M / ADV$>=$1M gates
            continue
        if (hi / pc - 1) * 100 < SCREEN_HIGH_PCT:
            continue
        cands.append((t, pc))
    day_fan = {s: {w: 0 for w in WIN} for s in SUPERSETS}
    for t, pc in cands:
        mb = pget(f"/v2/aggs/ticker/{t}/range/1/minute/{ds}/{ds}",
                  {"adjusted": "true", "sort": "asc", "limit": "50000"})
        bars = mb.get("results") or []
        series = []
        for b in bars:
            bt = datetime.datetime.fromtimestamp(b["t"] / 1000, ET)
            if bt.date().isoformat() == ds:
                series.append((bt.hour * 60 + bt.minute, b["c"]))
        series.sort()
        if not series:
            continue

        def price_at(mod, _s=series):
            p = None
            for mm, cc in _s:
                if mm <= mod:
                    p = cc
                else:
                    break
            return p

        rt, dl = {}, {}
        first_rt = first_dl = None
        for tk in TICKS:
            rp, dp = price_at(tk), price_at(tk - LAG_MIN)
            rt[tk] = (rp / pc - 1) * 100 if rp else None
            dl[tk] = (dp / pc - 1) * 100 if dp else None
            if rt[tk] is not None and rt[tk] >= MIN_GAP and first_rt is None:
                first_rt = tk
            if dl[tk] is not None and dl[tk] >= MIN_GAP and first_dl is None:
                first_dl = tk
        # fan-out: per in-window tick, count of superset admits (delayed gap in [s,10))
        for s in SUPERSETS:
            for w in WIN:
                if dl.get(w) is not None and dl[w] >= s:
                    day_fan[s][w] += 1
        caught = first_dl is not None and first_dl <= WIN_LAST
        missed_iw = first_rt is not None and first_rt <= WIN_LAST and not caught
        if missed_iw:
            tk = first_rt
            missed.append({"d": ds, "t": t, "tk": tk, "rt": round(rt[tk], 2),
                           "dl": round(dl[tk], 2) if dl[tk] is not None else None})
            for s in SUPERSETS:
                # caught by fix iff some in-window tick has delayed>=s AND rt>=10 (Pass1 admits + Pass2 confirms)
                ok = any(dl.get(w) is not None and dl[w] >= s and rt.get(w) is not None and rt[w] >= MIN_GAP for w in WIN)
                cover[s].append(1 if ok else 0)
    for s in SUPERSETS:
        for w in WIN:
            fan[s].append(day_fan[s][w])
    print(f"  {ds}: {len(cands)} screened, {sum(1 for m in missed if m['d']==ds)} missed-crosser(s)")

n = len(missed)
print(f"\n=== IN-WINDOW CROSSERS MISSED BY THE DELAY (the IREN class): {n} over {len(days)-1} days "
      f"(~{n/(len(days)-1):.2f}/day) ===")
print("superset coverage (of missed crossers, fraction Pass-1 admits + Pass-2 confirms in-window):")
for s in SUPERSETS:
    c = cover[s]
    pct = sum(c) / len(c) * 100 if c else 0
    fa = sorted(fan[s])
    p50 = fa[len(fa) // 2] if fa else 0
    p95 = fa[int(len(fa) * 0.95)] if fa else 0
    print(f"  >={s}%: catches {sum(c)}/{len(c)} = {pct:.0f}%  | fan-out/tick p50={p50} p95={p95}")
print("\n=== named missed list ===")
for m in sorted(missed, key=lambda x: (x["d"], x["tk"])):
    print(f"  {m['d']} {m['t']:6} cross@{m['tk']//60:02d}:{m['tk']%60:02d} rt={m['rt']}% delayed={m['dl']}%")
