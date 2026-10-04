"""#655 verify — nightly boards rebuilt the way db.get_active_themes builds them (latest row per
name within 7 calendar days, then drop Retired); B's G4 over every night; A simulated night by
night WITHOUT look-ahead (excess masked to sessions <= the board date)."""
import pickle, sys, collections
from datetime import date, timedelta
import numpy as np
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence import theme_correctness as tc
S = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/"
d = pickle.load(open(S + "655_capture.pkl", "rb"))
scores, sector, excess, hist = d["scores"], d["sector"], d["excess"], d["history"]
sess = [date.fromisoformat(s) for s in d["sessions"]]
ret_dates = sess[1:]   # excess[i] = return ending sessions[i+1] (assumption; off-by-one at most)
assert len(ret_dates) == 60
by_name = collections.defaultdict(list)
for r in hist: by_name[r["name"]].append(r)
for n in by_name: by_name[n].sort(key=lambda r: r["theme_date"])
dates = sorted({r["theme_date"] for r in hist})

def board(D, rule="active"):
    out = []
    for n, rows in by_name.items():
        rr = [r for r in rows if r["theme_date"] <= D and (rule == "today" or r["theme_date"] >= D - timedelta(days=7))]
        if rule == "today": rr = [r for r in rr if r["theme_date"] == D]
        if not rr: continue
        L = rr[-1]
        if L["stage"] == "Retired" or not L["tickers"]: continue
        out.append({"name": n, "stage": L["stage"], "tickers": list(L["tickers"]), "date": L["theme_date"]})
    return out

nightly = {date(2026, 9, 30): 129, date(2026, 10, 1): 131, date(2026, 10, 2): 133}
for D, n in nightly.items():
    print(f"board {D}: active-emulation {len(board(D))}  today-only {len(board(D,'today'))}  nightly {n}")

def masked(D):
    keep = np.array([rd < D for rd in ret_dates])   # strictly before the read date
    return {t: np.where(keep, v, np.nan) for t, v in excess.items()}, int(keep.sum())

nights = [D for D in dates if D >= date(2026, 9, 8)]
print("nights:", len(nights), nights[0], nights[-1])
g4b = g4a = 0
streak = collections.defaultdict(int); retired = {}
fails_by_night = {}
for D in nights:
    b = board(D)
    small = [t for t in b if len(t["tickers"]) < 3]
    Bset = {t["name"] for t in small if t["stage"] == "Fading"}
    n0 = len(b); s0 = len(small); n1 = n0 - len(Bset); s1 = s0 - len(Bset)
    g4b += (100 * s0 / n0 <= 10); g4a += (100 * s1 / n1 <= 10)
    ex, nses = masked(D)
    us = tc.usable_set(ex)
    g3 = tc.compute_g3(b, ex, us, scores, sector)
    fl = set(g3["fail_list"]); fails_by_night[D] = fl
    names = {t["name"] for t in b}
    for n in list(streak):
        if n not in names: streak[n] = 0
    for n in names:
        streak[n] = streak[n] + 1 if n in fl else 0
        if streak[n] == 3 and n not in retired:
            retired[n] = D
    print(f"{D} board {n0} small {s0} ({100*s0/n0:.1f}%) Fading-small {len(Bset)} -> after B {s1}/{n1} ({100*s1/n1:.1f}%) | G3 {g3['pass']}/{g3['n_judgeable']}={g3['rate_pct']} sessions<D {nses}")
print(f"G4 nights passing: baseline {g4b}/{len(nights)}, after B {g4a}/{len(nights)}")
# A: what became of each retired name afterwards (no-look-ahead G3 on 10-02 board)
last = nights[-1]; bl = {t["name"]: t for t in board(last)}
print(f"A (K=3, no look-ahead) retire events: {len(retired)}")
for n, D in sorted(retired.items(), key=lambda x: x[1]):
    rows = by_name[n]
    later_max = max([len(r["tickers"]) for r in rows if r["theme_date"] > D] or [0])
    on = n in bl; pas = on and n not in fails_by_night[last]
    print(f"   {D} {n[:55]:55} size@{len(next(t for t in board(D) if t['name']==n)['tickers'])} later_max {later_max} on10-02 {on} passes10-02 {pas}")
