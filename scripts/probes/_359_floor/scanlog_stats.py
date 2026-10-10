"""#359 Read B (scan log) — the real EP scan population (mi_ep_scan_log 2026-06-08..09-03, #623 master, safeguard-blocked and
filtered rows included), walked under era D by #545p2 (cell era_d_ladder, submit 09:31). Stage-matched comparison:
BELOW = rejected by the market-cap floor (so it had passed every earlier gate: universe floors, shortlist, rvol,
cooldown, extension, ADV$, ATR); ABOVE = cleared check_filters (reached scoring, or rejected only post-grade)."""
import json, csv, statistics
from collections import Counter
from pathlib import Path
H = Path(__file__).parent; PR = H.parent
m = {(r["ticker"], r["scan_date"]): r for r in map(json.loads, open(PR / "_623_master.jsonl"))}
walk = {}
for r in csv.DictReader(open(PR / "_545p2_623_era_walk.tsv"), delimiter="|"):
    if r["cell"] == "era_d_ladder":
        walk[(r["ticker"], r["alert_date"])] = r
out = open(H / "scanlog_stats_out.txt", "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.write(s + "\n")
POST = ("M&A/buyout", "routine catalyst", "pre-mkt volume")
def stage(r):
    f = r["nearest_filter_reason"] or ""
    if "mcap_too_small" in f: return "below_floor_only"
    if r["ever_scored"] or f.startswith(POST): return "cleared_quality"
    return "other"
def band(c):
    if c is None: return None
    for lo, hi, lab in ((0, 250e6, "<250M"), (250e6, 5e8, "250-500M"), (5e8, 1e9, "500M-1B"), (1e9, 2e9, "1-2B"), (2e9, 1e18, ">2B")):
        if lo <= c < hi: return lab
P("# Read B (scan log) — population: _623_master.jsonl (3458 ticker-days, nearest-09:31 tick) joined to era_d_ladder (_545p2_623_era_walk.tsv)")
P(f"joined: {sum(k in walk for k in m)} of {len(m)}")
for st in ("below_floor_only", "cleared_quality"):
    P(f"\n## {st}")
    P("band | n rows | cap source (column/parse/proxy) | entered | settled | open@horizon | >=3R | >=8R | mean R (settled) | mean ex-best-2 | median R | top | median $ traded by 09:31")
    for b in ("<250M", "250-500M", "500M-1B", "1-2B", ">2B"):
        rs = [r for r in m.values() if stage(r) == st and band(r["market_cap"]) == b]
        if not rs: continue
        ws = [walk.get((r["ticker"], r["scan_date"])) for r in rs]
        sett = [(r, float(w["realized_r"])) for r, w in zip(rs, ws) if w and w["status"] == "settled" and w["realized_r"]]
        opn = [(r, float(w["mark_r"])) for r, w in zip(rs, ws) if w and w["status"] == "open_at_horizon" and w["mark_r"]]
        R = sorted((x for _, x in sett), reverse=True)
        src = Counter(r["market_cap_source"] for r in rs)
        top = ", ".join(f"{r['ticker']} {r['scan_date']} {x:+.1f}" for r, x in sorted(sett, key=lambda z: -z[1])[:3])
        dv = [r["dollar_volume_0931"] for r in rs if r.get("dollar_volume_0931")]
        P(f"{b} | {len(rs)} | {src.get('column',0)}/{src.get('filter_reason_parse',0)}/{src.get('proxy_shares_x_price',0)} | "
          f"{sum(1 for w in ws if w and w['entered']=='True')} | {len(R)} | {len(opn)} (marks {[round(x,1) for _,x in opn]}) | "
          f"{sum(x>=3 for x in R)} | {sum(x>=8 for x in R)} | {statistics.mean(R) if R else float('nan'):+.2f} | "
          f"{statistics.mean(R[2:]) if len(R)>2 else float('nan'):+.2f} | {statistics.median(R) if R else float('nan'):+.2f} | {top} | "
          f"${statistics.median(dv)/1e6 if dv else float('nan'):.2f}M")
near = [r for r in m.values() if stage(r) in ("below_floor_only", "cleared_quality") and r["market_cap"] and 4e8 <= r["market_cap"] < 6e8]
P(f"\nboundary $400-600M rows in the two stages: {len(near)}; of those proxy-capped: {sum(r['market_cap_source']=='proxy_shares_x_price' for r in near)}")
out.close()
