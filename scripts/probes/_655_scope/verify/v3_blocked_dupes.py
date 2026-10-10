"""verify #655: of the cooldown's blocked returns that came back passing G3, how many have >= half their members
already in ANOTHER live theme on the return night (the doc's 'mostly duplicates' claim). $0."""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from collections import defaultdict
from datetime import date
from load import load
B = load()
on = defaultdict(dict)
for r in B["themes"]:
    if r["stage"] != "Retired" and r["tickers"]:
        on[r["d"]][r["name"]] = r
cases = [("Gold & Silver Miners Not Yet Classified (Mid-Tier", date(2026,10,8)), ("AI Data Services & GPU Cloud Platforms", date(2026,10,2)),
         ("Offshore Drilling Rig Contractors", date(2026,9,29)), ("Semiconductor Process Instruments & RF/PCB Electro", date(2026,10,7)),
         ("Appalachian Natural Gas Producers", date(2026,10,2)), ("Small Modular Reactor & Advanced Nuclear Fission T", date(2026,10,8))]
for pre, d in cases:
    n = next(x for x in on[d] if x.startswith(pre)); T = set(on[d][n]["tickers"])
    best = max(((len(T & set(r["tickers"])), m) for m, r in on[d].items() if m != n), default=(0, None))
    print(f"{n[:55]} | back {d} | {len(T)} members | most shared with another live theme: {best[0]} ({str(best[1])[:50]})")
