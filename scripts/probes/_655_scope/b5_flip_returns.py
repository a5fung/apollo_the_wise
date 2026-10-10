"""#655 scope Q-B: for each same-name flip — members before exit vs on return, return source, G3 verdict on the
return night (stored audit row, when that night has one). Sizes the cost of a 're-mint cooldown'. $0."""
import re
from collections import Counter, defaultdict
from datetime import date
from load import load
b = load()
on = defaultdict(dict)
for r in b["themes"]:
    if r["stage"] != "Retired" and r["tickers"]:
        on[r["d"]][r["name"]] = r
nights = sorted(on)
g3 = {date.fromisoformat(r["et"][:10]): {t["name"]: t for t in r["detail"]["g3"]["themes"]}
      for r in b["correctness"] if r["et"][11:16] == "17:31"}
rows = []
for ln in open("b1_churn.out"):
    m = re.match(r"  (.*?) \| (\d{4}-\d\d-\d\d) \| (.*?) \| (\d{4}-\d\d-\d\d)$", ln.rstrip())
    if not m: continue
    n, off, c, back = m.group(1), date.fromisoformat(m.group(2)), m.group(3), date.fromisoformat(m.group(4))
    full = next(x for x in on[[d for d in nights if d < off][-1]] if x.startswith(n))
    before = len(on[[d for d in nights if d < off][-1]][full]["tickers"])
    r = on[back][full]; after = len(r["tickers"])
    v = g3.get(back, {}).get(full)
    rows.append((c, full, before, after, r["source"], None if v is None else v["pass_g3"], r["stage"], r["rs_avg"]))
tab = defaultdict(Counter)
for c, n, bf, af, src, p, stg, rs in rows:
    k = "cap >= 3 judged (ruling (a))" if c.startswith("cap: >= 3") else c
    tab[k]["flips"] += 1; tab[k]["back via promote lane"] += src == "shadow_promoted"
    tab[k]["back with MORE members"] += af > bf; tab[k]["back passing G3"] += p is True; tab[k]["back failing G3"] += p is False
for k, v in tab.items(): print(k, "|", dict(v))
print()
for x in sorted(rows): print("  ", x[0][:28], "|", x[1][:55], "|", f"{x[2]} -> {x[3]}", "|", x[4], "| G3 on return", x[5], "|", x[6], x[7] and round(x[7]))
