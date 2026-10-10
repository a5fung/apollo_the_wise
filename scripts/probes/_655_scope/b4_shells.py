"""#655 scope Q-B parked item (3): same-name re-mint shells — Pass-1 protect-strip rows where a newborn and the
incumbent carry the SAME name, 14 nights 2026-09-22..10-09, and whether the name left the board that night. $0."""
import re
from collections import defaultdict
from datetime import date
from load import load
b = load()
on = defaultdict(set)
for r in b["themes"]:
    if r["stage"] != "Retired" and r["tickers"]:
        on[r["d"]].add(r["name"])
nights = sorted(on)
n_same = n_empty = 0; left = []
for e in b["events"]:
    d = date.fromisoformat(e["et"][:10])
    if e["event_type"] != "theme_pass1_protect_strip" or d < date(2026, 9, 22): continue
    det = e["detail"]
    i = re.search(r"i='(.*?)' i_protected", det).group(1); j = re.search(r"j='(.*?)' j_protected", det).group(1)
    if i != j: continue
    n_same += 1
    emp = "EMPTY_AFTER_STRIP" in det
    n_empty += emp
    prev = [x for x in nights if x < d][-1]
    gone = i in on[prev] and i not in on[d]
    print(f"{d} | {i[:60]} | {'empty shell' if emp else 'partial'} | name left the board that night: {gone} | {det[det.find('stripped='):][:60]}")
    if gone: left.append((d, i))
print(f"same-name strips {n_same}, of which empty shells {n_empty}; name left the board on {len(left)} of them: {left}")
