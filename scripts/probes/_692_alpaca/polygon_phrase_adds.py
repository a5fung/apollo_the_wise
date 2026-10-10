"""$0, offline (#692 10-10 review fix): the Polygon-side candidates the seven deal-wire phrases ADD.

The paid check asked only Alpaca-sourced headlines (47 original + 41 phrase adds). The phrases also
widen the POLYGON candidate pick (same list). This lists those, reading news_pull.jsonl only, with the
REAL ma_filter functions, over the 151 ticker-day cells (Polygon items only, published by the day's end).
Run: python scripts/probes/_692_alpaca/polygon_phrase_adds.py > scripts/probes/_692_alpaca/polygon_phrase_adds_out.txt
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from agents.market_intelligence import ma_filter as mf  # noqa: E402

pull = [json.loads(line) for line in open(HERE / "news_pull.jsonl")]
cells = [p for p in pull if p["kind"] == "cell"]
NEW = mf._MNA_CANDIDATE_KEYWORDS


def polygon_only(kwlist):
    mf._MNA_CANDIDATE_KEYWORDS = kwlist
    out = {}
    for c in cells:
        t, day = c["ticker"], c["day"]
        poly = [i for i in c["polygon"] if (i.get("published_utc") or "") <= f"{day}T23:59:59Z"]
        merged = mf._merge_headline_sources(poly, [])
        for item, mp, kw, _r in mf._candidate_articles(t, merged, company_name=None):
            out.setdefault((t, mf._norm_title(item["title"])), {
                "ticker": t, "title": item["title"], "days": [], "match_path": mp, "kw": kw})["days"].append(day)
    return out


old = polygon_only(mf._MNA_KEYWORDS)
new = polygon_only(NEW)
added = {k: v for k, v in new.items() if k not in old}
print(f"Polygon-side candidates (unique ticker, headline) under ORIGINAL list: {len(old)}; "
      f"with the 7 phrases: {len(new)}; ADDED: {len(added)}")
for k, v in sorted(added.items()):
    print(f"   {v['ticker']:6} {v['days'][0]} [{v['match_path'][:5]}] kw={v['kw']!r:22} {v['title'][:110]!r}")
