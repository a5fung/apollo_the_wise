"""#644 correction test scoring. usage: python3 score.py A   (B on 12-11 after re-pulling closes.out through 12-11)"""
import sys, json, csv, statistics, asyncio, importlib.util, random
from datetime import date
from unittest.mock import AsyncMock, MagicMock
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
spec = importlib.util.spec_from_file_location("old", "/Users/alvinfung/apollo_the_wise/scripts/probes/_644_resilience_test.py")
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
db = old.db
D = "/Users/alvinfung/apollo_the_wise/scripts/probes/_644_correction_1128/"
OUT = sys.argv[1] if len(sys.argv) > 1 else "A"
WIN = {"A": ("2026-11-20", "2026-11-27"), "B": ("2026-11-27", "2026-12-11")}[OUT]
rows = []
for r in csv.reader(open(D + "closes.out")):
    if len(r) != 3 or r[0] == "ticker": continue
    rows.append({"ticker": r[0], "trade_date": old._parse_date(r[1]), "close": float(r[2])})
px = {}
for r in rows: px.setdefault(r["ticker"], {})[r["trade_date"]] = r["close"]
spy_dates = sorted(px["SPY"])
w_lo, w_hi = date(2026, 10, 7), date(2026, 11, 20)
LOOKBACK = sum(1 for d in spy_dates if w_lo <= d <= w_hi)
conn = old._RealPullConn(rows)
cm = MagicMock(); cm.__aenter__ = AsyncMock(return_value=conn); cm.__aexit__ = AsyncMock(return_value=None)
pool = MagicMock(); pool.acquire = MagicMock(return_value=cm)
db.get_pool = AsyncMock(return_value=pool)
d0, d1 = (old._parse_date(x) for x in WIN)
def ret(t): 
    p = px.get(t, {}); return p[d1] / p[d0] - 1 if d0 in p and d1 in p else None
spy_ret = ret("SPY")
pop = json.load(open(D + "population.json"))

def build(as_of):
    res = []
    for e in pop:
        pt = asyncio.run(db.get_down_day_resilience(as_of, tickers=e["tickers"], lookback=LOOKBACK))
        rv = {r["ticker"]: r["resilience"] for r in pt}
        ok = [t for t in e["tickers"] if t in rv and ret(t) is not None]
        if len(ok) < 3: continue
        res.append({"cid": e["canonical_id"], "tickers": e["tickers"], "n": len(ok),
                    "score": statistics.median(rv[t] for t in ok),
                    "excess": statistics.mean(ret(t) for t in ok) - spy_ret})
    return res

def thirds(res):
    s = sorted(res, key=lambda r: (-r["score"], r["cid"])); k = len(s) // 3
    return s[:k], s[k:len(s) - k], s[len(s) - k:], s

def test(res, seed=644, N=10000):
    top, mid, bot, _ = thirds(res)
    med = lambda a: statistics.median(r["excess"] for r in a) * 100
    gap = med(top) - med(bot)
    pool_ = [r["excess"] for r in top + bot]; k = len(top)
    rng = random.Random(seed); ge = 0
    for _ in range(N):
        rng.shuffle(pool_)
        if (statistics.median(pool_[:k]) - statistics.median(pool_[k:])) * 100 >= gap: ge += 1
    p = (ge + 1) / (N + 1)
    verdict = "PASS" if (gap >= 1.0 and p < 0.05) else "FAIL" if (gap < 0 or p >= 0.20) else "inconclusive"
    return {"n_themes": len(res), "n_third": k, "top_median_excess_pp": med(top), "mid_median_excess_pp": med(mid),
            "bot_median_excess_pp": med(bot), "gap_pp": gap, "p_onesided": p, "verdict": verdict,
            "top_score_median": statistics.median(r["score"] for r in top), "bot_score_median": statistics.median(r["score"] for r in bot)}

def drop_overlap(res):
    s = sorted(res, key=lambda r: (-r["score"], r["cid"])); kept = []
    for i, r in enumerate(s):
        T = set(r["tickers"])
        if any(len(T & set(h["tickers"])) / len(T) > 0.5 for h in s[:i]): continue
        kept.append(r)
    return kept

board = json.load(open(D + "board.json"))
def share(res):
    top, mid, bot, _ = thirds(res); o = {}
    for w, b in board.items():
        o[w] = None if b is None else {n: sum(r["cid"] in set(b) for r in g) / len(g) for n, g in (("top", top), ("mid", mid), ("bottom", bot))}
    return o

out = {"outcome": OUT, "window": WIN, "spy_return_pct": spy_ret * 100, "lookback_sessions": LOOKBACK}
# PRIMARY: exactly as written, as_of = 2026-11-20 (function uses sessions STRICTLY BEFORE as_of)
res = build(date(2026, 11, 20))
out["primary_as_of_1120"] = {**test(res), "overlap_dropped": test(drop_overlap(res)), "board_share": share(res)}
# SENSITIVITY (labelled, NOT the verdict): as_of = next session after 11-20 so the 33-session window 10-07..11-20 is exactly covered
res2 = build(date(2026, 11, 23))
out["sensitivity_as_of_1123"] = {**test(res2), "overlap_dropped": test(drop_overlap(res2))}
json.dump(out, open(D + f"results_{OUT}.json", "w"), indent=1)
print(json.dumps(out, indent=1))
