"""#655 scope Q-B option 2 sized: a re-mint cooldown — a returning cohort (same name, or a new name with Jaccard >= 0.5
to the removed roster) within 5 engine nights of its removal is BLOCKED unless it carries >= 1 member the removed
roster did not have. Flips whose cause ruling (a) / the 10-07 self-comparison fix already remove, renames, and same-
night new-name replacements are left out. $0, reads b1_churn.out / b5_flip_returns.out inputs again from the capture."""
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
def idx(d): return nights.index(d)
blocked = []; allowed = []
def judge(kind, old, off, new, back, cause):
    prev = nights[idx(off) - 1]
    O = set(on[prev][old]["tickers"]); N = set(on[back][new]["tickers"])
    gap = idx(back) - idx(off) + 1
    grew = bool(N - O)
    v = g3.get(back, {}).get(new)
    rec = (kind, cause, old[:50], new[:50], off, back, gap, len(O), len(N), grew, None if v is None else v["pass_g3"])
    (allowed if grew or gap > 5 else blocked).append(rec)
skip = ("cap: >= 3", "rename")
for ln in open("b1_churn.out"):
    m = re.match(r"  (.*?) \| (\d{4}-\d\d-\d\d) \| (.*?) \| (\d{4}-\d\d-\d\d)$", ln.rstrip())
    if m:
        n, off, c, back = m.group(1), date.fromisoformat(m.group(2)), m.group(3), date.fromisoformat(m.group(4))
        if c.startswith(skip): continue
        if c.startswith("cap: < 3") and off == date(2026, 10, 7): continue   # self-comparison bug, fixed 10-09
        full = next(x for x in on[nights[idx(off) - 1]] if x.startswith(n))
        judge("same-name", full, off, full, back, c); continue
    m = re.match(r"  (.*?) \| (\d{4}-\d\d-\d\d) \| (.*?) \| (.*?) \| (\d{4}-\d\d-\d\d) \| ([\d.]+)$", ln.rstrip())
    if m:
        o, off, c, nn, back = m.group(1), date.fromisoformat(m.group(2)), m.group(3), m.group(4), date.fromisoformat(m.group(5))
        if c.startswith(skip) or back == off: continue    # same-night replacement = a rename in effect, not churn
        full = next(x for x in on[nights[idx(off) - 1]] if x.startswith(o))
        newf = next(x for x in on[back] if x.startswith(nn))
        judge("new-name", full, off, newf, back, c)
print(f"blocked by the cooldown: {len(blocked)} | allowed (grew, or > 5 nights): {len(allowed)}")
print("blocked by cause:", dict(Counter((r[0], r[1]) for r in blocked)))
print("blocked that came back passing G3:", sum(r[10] is True for r in blocked), "| failing:", sum(r[10] is False for r in blocked), "| no read (before 09-28):", sum(r[10] is None for r in blocked))
for r in blocked + [("--allowed--",)] + allowed: print("  ", r)
