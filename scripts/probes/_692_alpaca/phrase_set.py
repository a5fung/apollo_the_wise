"""$0, offline (#692 phrases, 2026-10-10): reproduce the 35 and build the paid-check set.

Reads news_pull.jsonl only. With the REAL ma_filter functions, selects the Alpaca-sourced candidates
(headline not already in the cell's Polygon items) under (a) the ORIGINAL keyword list and (b) the
list with the 7 deal-wire phrases appended, over the 151 ticker-day cells. The paid-check set is
the unique (ticker, headline) union of (a) [the 45 as built] and the extra ones (b) adds.
Run: python scripts/probes/_692_alpaca/phrase_set.py > scripts/probes/_692_alpaca/phrase_set_out.txt
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from agents.market_intelligence import ma_filter as mf  # noqa: E402

ORIG = mf._MNA_KEYWORDS
SEVEN = ("to merge", "merge with", "business combination", "agreement to acquire", "to acquire",
         "agrees to buy", "inks agreement")
assert mf._MNA_DEAL_WIRE_PHRASES == SEVEN
NEW = mf._MNA_CANDIDATE_KEYWORDS
pull = [json.loads(l) for l in open(HERE / "news_pull.jsonl")]
cells = [p for p in pull if p["kind"] == "cell"]


def alpaca_only(kwlist):
    mf._MNA_CANDIDATE_KEYWORDS = kwlist
    out = {}
    for c in cells:
        t, day = c["ticker"], c["day"]
        poly = [i for i in c["polygon"] if (i.get("published_utc") or "") <= f"{day}T23:59:59Z"]
        alp = [i for i in mf._alpaca_to_scan_items(c["alpaca"])
               if (i.get("published_utc") or "") <= f"{day}T23:59:59Z"]
        merged = mf._merge_headline_sources(poly, alp)
        for item, mp, kw, _r in mf._candidate_articles(t, merged, company_name=None):
            if item.get("news_source") == "alpaca":
                out.setdefault((t, mf._norm_title(item["title"])), {
                    "ticker": t, "title": item["title"], "published_utc": item["published_utc"],
                    "days": [], "match_path": mp, "kw": kw, "publisher": item.get("publisher"),
                    "description": item.get("description") or "", "tickers": item.get("tickers")})["days"].append(day)
    return out


a_old = alpaca_only(ORIG)
a_new = alpaca_only(NEW)
only_new = {k: v for k, v in a_new.items() if k not in a_old}
print(f"Alpaca-only candidate rows (ticker-day, headline) under ORIGINAL list: "
      f"{sum(len(v['days']) for v in a_old.values())} rows / {len(a_old)} unique (ticker, headline)")
print(f"under ORIGINAL + 7 phrases: {sum(len(v['days']) for v in a_new.values())} rows / {len(a_new)} unique")
print(f"ADDED unique (ticker, headline) by the 7 phrases: {len(only_new)}")
for k, v in sorted(only_new.items()):
    print(f"   {v['ticker']:6} {v['days'][0]} [{v['match_path'][:5]}] kw={v['kw']!r:22} {v['title'][:100]!r}")
json.dump(sorted(a_new.values(), key=lambda v: (v["ticker"], v["published_utc"])),
          open(HERE / "paid_check_set.json", "w"), indent=1)
print(f"\nPAID-CHECK SET (unique ticker+headline, old-list Alpaca-only + phrase adds): {len(a_new)}")
