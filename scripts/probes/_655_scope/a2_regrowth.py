"""#655 scope Q-A step 2: do 2-3-member themes grow? Births 2026-07-01..09-25 (>= 10 nights to watch),
first non-Retired row per name; outcome watched to 10-09. $0, capture only."""
from collections import Counter, defaultdict
from datetime import date, timedelta
from load import load
b = load()
rows = b["themes"]
by_name = defaultdict(list)
for r in rows:
    by_name[r["name"]].append(r)
for v in by_name.values():
    v.sort(key=lambda r: (r["d"], r["id"]))
by_date = defaultdict(list)
for r in rows:
    if r["stage"] != "Retired" and r["tickers"]:
        by_date[r["d"]].append(r)
nights = sorted(by_date)

births = []
for n, v in by_name.items():
    live = [r for r in v if r["stage"] != "Retired" and r["tickers"]]
    if not live:
        continue
    f = live[0]
    if not (date(2026, 7, 1) <= f["d"] <= date(2026, 9, 25)):
        continue
    births.append((n, f, live))

def cohort_grew(f, within=30):
    F = set(f["tickers"])
    for d in nights:
        if f["d"] < d <= f["d"] + timedelta(days=within):
            for r in by_date[d]:
                if len(r["tickers"]) >= 4 and len(F & set(r["tickers"])) >= max(2, (len(F) + 1) // 2):
                    return r, d
    return None, None

tab = defaultdict(Counter)
named = defaultdict(list)
for n, f, live in births:
    sz = len(f["tickers"])
    k = "2" if sz == 2 else "3" if sz == 3 else "4+" if sz >= 4 else "1"
    grew_same = max(len(r["tickers"]) for r in live) >= 4 and sz < 4
    nights_live = len({r["d"] for r in live})
    cr, cd = cohort_grew(f) if sz < 4 else (None, None)
    tab[k]["births"] += 1
    tab[k]["nascent_at_birth"] += f["stage"] == "Nascent"
    tab[k]["grew_same_name"] += grew_same
    tab[k]["cohort_in_4plus_theme_30d"] += cr is not None
    tab[k]["cohort_in_4plus_OTHER_name"] += (cr is not None and cr["name"] != n)
    tab[k]["lived_10plus_nights"] += nights_live >= 10
    if grew_same:
        top = max(live, key=lambda r: len(r["tickers"]))
        named[k].append(f"{n} | born {f['d']} {f['stage']} {sz} -> max {len(top['tickers'])} on {top['d']} ({top['stage']}, rs {top['rs_avg'] and round(top['rs_avg'])}) | nights live {nights_live}")
for k in ("1", "2", "3", "4+"):
    print(k, dict(tab[k]))
for k in ("2", "3"):
    print(f"\n== born with {k} members and later reached >= 4 under the SAME name ({len(named[k])})")
    for x in sorted(named[k]):
        print("  ", x)
# source of births
print("\nsource at birth by size:", Counter((min(len(f['tickers']),4), f['source']) for n, f, l in births))
