"""#624 news step 1 — live EP alerts (Aug-Oct 2026): did Polygon's pre-alert news contain what the live grader read?
Inputs: news_alerts.jsonl (prod SELECT: grader corpus classes + Benzinga titles it saw), news_alert_raw.jsonl (Polygon pull,
window = prior session 16:00 ET .. alert detection time, + prior 7d).  No network."""
import json, re, os, sys, collections
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence.collector import is_primary_subject_news
H = os.path.dirname(os.path.abspath(__file__))
al = [json.loads(l) for l in open(os.path.join(H, "news_alerts.jsonl"))]
po = {}
for l in open(os.path.join(H, "news_alert_raw.jsonl")):
    r = json.loads(l); po[(r["ticker"], r["D"])] = r
ap = {}
p = os.path.join(H, "news_alert_alpaca_raw.jsonl")
if os.path.exists(p):
    for l in open(p):
        r = json.loads(l); ap[(r["ticker"], r["D"])] = r


def toks(s):
    return set(re.findall(r"[a-z0-9]+", s.lower())) - {"the", "a", "an", "of", "to", "and", "in", "for", "on", "with", "as", "at", "by", "from", "inc"}


def match(gt, pt):
    a, b = toks(gt), toks(pt)
    if not a or not b: return False
    ov = len(a & b) / min(len(a), len(b))
    return ov >= 0.7 and len(a & b) >= 3


rows = []
for a in al:
    k = (a["ticker"], a["alert_date"])
    if k not in po: continue
    r = po[k]
    win = r["articles"]; early = r["earlier_7d"]
    prim = [x for x in win if is_primary_subject_news({"title": x["title"], "symbols": x.get("tickers") or []}, a["ticker"], "")]
    bz = [b["title"] for b in a["benzinga"]]
    pool_win = [x["title"] for x in win]
    pool_all = pool_win + [x["title"] for x in early]
    m_win = [t for t in bz if any(match(t, pt) for pt in pool_win)]
    m_all = [t for t in bz if any(match(t, pt) for pt in pool_all)]
    rows.append({"ticker": a["ticker"], "date": a["alert_date"], "q": a["catalyst_quality"], "type": a["catalyst_type"], "gap": a["gap_pct"],
                 "n_poly": len(win), "n_poly_prim": len(prim), "n_early": len(early), "n_bz": len(bz), "bz_match_win": len(m_win),
                 "bz_match_all": len(m_all), "sec": (a["sec_head"] or "")[:40], "bz": bz, "prim_titles": [x["title"] for x in prim][:3],
                 "catalyst": a["catalyst"][:150]})
n = len(rows)
print("alerts compared:", n, "| quality:", dict(collections.Counter(r["q"] for r in rows)))
print("Polygon >=1 article in window:", sum(r["n_poly"] > 0 for r in rows), "| primary-subject >=1:", sum(r["n_poly_prim"] > 0 for r in rows),
      "| >=1 in window or prior 7d:", sum((r["n_poly"] + r["n_early"]) > 0 for r in rows))
hb = [r for r in rows if r["n_bz"] > 0]
print("alerts where the grader read >=1 Benzinga item:", len(hb), "| of those, Polygon has a title-matching article in window:",
      sum(r["bz_match_win"] > 0 for r in hb), "| in window or prior 7d:", sum(r["bz_match_all"] > 0 for r in hb))
tb = sum(r["n_bz"] for r in hb); tm = sum(r["bz_match_win"] for r in hb); tma = sum(r["bz_match_all"] for r in hb)
print(f"Benzinga items the grader read: {tb}; matched in Polygon window: {tm} ({100*tm/max(tb,1):.0f}%); window+prior7d: {tma} ({100*tma/max(tb,1):.0f}%)")
print("by grade (strong/game_changer only), Polygon primary>=1:", {q: (sum(1 for r in rows if r['q']==q and r['n_poly_prim']>0), sum(1 for r in rows if r['q']==q)) for q in ("game_changer","strong","routine")})
print("\n-- matched by name (Benzinga title the grader read also in Polygon window)")
for r in rows:
    if r["bz_match_win"]:
        print(f"  {r['ticker']} {r['date']} {r['q']}: {r['bz_match_win']}/{r['n_bz']} | poly: {r['prim_titles'][:1]}")
print("\n-- MISSES: grader read Benzinga items, Polygon (window) had none matching")
for r in hb:
    if not r["bz_match_win"]:
        print(f"  {r['ticker']} {r['date']} {r['q']} type={r['type']} sec={r['sec'][:28]!r} n_poly={r['n_poly']} prim={r['n_poly_prim']} | bz: {r['bz'][:2]}")
print("\n-- no Benzinga item at all (grader had SEC/web only)")
for r in rows:
    if r["n_bz"] == 0:
        print(f"  {r['ticker']} {r['date']} {r['q']} sec={r['sec'][:28]!r} n_poly={r['n_poly']} | {r['catalyst'][:100]}")
if ap:
    print("\n-- Alpaca pull for the same windows:", sum(1 for r in rows if (r['ticker'], r['date']) in ap))
