"""$0, offline: where the CANDIDATE keyword list (not the decision rule) misses a deal headline the Alpaca feed carries.

Reads news_pull.jsonl only. Two blocks:
  1. the five names the 10-05 board rejected as pinned buyouts (weekly cells): every Alpaca title with a
     deal word, and whether the CURRENT keyword list would make it a candidate.
  2. a MEASURE of one proposed widening (NOT shipped — his decision, Known-limitations item 8): how many more
     Alpaca titles become candidates across the 151 ticker-day cells, so he can price the choice.
Run: python scripts/probes/_692_alpaca/keyword_gap.py > scripts/probes/_692_alpaca/keyword_gap_out.txt
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from agents.market_intelligence import ma_filter as mf  # noqa: E402

pull = [json.loads(l) for l in open(HERE / "news_pull.jsonl")]
DEALISH = re.compile(r"acquir|merge|merger|buyout|take.?over|private|tender|business combination|"
                     r"definitive|agreement to|offer|buy", re.I)
PROPOSED = ("to merge", "merge with", "merges with", "business combination", "agreement to acquire",
            "to acquire", "agrees to buy", "inks agreement")

print("1. the five names — Alpaca titles with a deal word, 06-19 .. 10-09 (weekly pull)")
for t in ("ARX", "BWIN", "CBZ", "DV", "ITGR"):
    seen = {}
    for p in pull:
        if p["kind"] == "weekly" and p["ticker"] == t:
            for it in mf._alpaca_to_scan_items(p["alpaca"], t):
                if DEALISH.search(it["title"]):
                    seen[mf._norm_title(it["title"])] = it
    print(f"  {t}: {len(seen)} deal-word titles")
    for it in sorted(seen.values(), key=lambda i: i["published_utc"]):
        cur = mf.matches_mna_keywords(it["title"])
        print(f"     {it['published_utc'][:10]} current-keyword={cur!r:22} {it['title'][:105]!r}")

print("\n2. MEASURE of one proposed widening (not shipped): titles that match", PROPOSED)
cells = [p for p in pull if p["kind"] == "cell"]
titles = {}
for c in cells:
    for it in mf._alpaca_to_scan_items(c["alpaca"], c["ticker"]):
        titles.setdefault(mf._norm_title(it["title"]), (c["ticker"], c["day"], it["title"]))
cur = [v for v in titles.values() if mf.matches_mna_keywords(v[2])]
new = [v for v in titles.values() if not mf.matches_mna_keywords(v[2])
       and any(k in v[2].lower() for k in PROPOSED)]
print(f"  distinct Alpaca titles over the 151 ticker-day cells: {len(titles)}")
print(f"  already candidates under the CURRENT list: {len(cur)}")
print(f"  ADDED by the widening: {len(new)}")
for v in new:
    print(f"     {v[0]:6} {v[1]} {v[2][:110]!r}")
