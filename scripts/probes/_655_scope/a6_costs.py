"""#655 scope Q-A: one cost table across options — distinct themes each option takes off the board in the 10 nights,
how many of them passed G3 on >= 1 night of the window (a co-moving group, i.e. a real theme lost), and how many
were Nascent/Mainstream with RS >= 80 when taken (the early strong class). Plus option (i)'s delay. $0."""
import re
from collections import defaultdict
from datetime import date
from board import B, NIGHTS, STORED

verd = {d: {t["name"]: t for t in STORED[d]["g3"]["themes"]} for d in NIGHTS}
row = defaultdict(dict)
for r in B["themes"]:
    if r["stage"] != "Retired":
        row[r["name"]][r["d"]] = r

def taken_profile(taken):  # taken: {name: first night taken}
    real = [n for n in taken if any(verd[d].get(n, {}).get("pass_g3") for d in NIGHTS)]
    strong = []
    for n, d in taken.items():
        r = row[n].get(d) or row[n][max(x for x in row[n] if x <= d)]
        if r["stage"] in ("Nascent", "Mainstream", "Accelerating") and (r["rs_avg"] or 0) >= 80:
            strong.append(n)
    nascent = [n for n in strong if (row[n].get(taken[n]) or {}).get("stage") == "Nascent"]
    return len(taken), len(real), len(strong), len(nascent), sorted(real)

out = {}
# (i) and (i-b)
hist = defaultdict(list)
for r in B["themes"]:
    if r["stage"] != "Retired" and r["tickers"]:
        hist[r["name"]].append((r["d"], len(r["tickers"])))
def r4(n, d): return any(k >= 4 for dd, k in hist[n] if dd <= d)
def c3(n, d): return any(verd[x].get(n, {}).get("size") == 3 and verd[x][n]["pass_g3"] for x in NIGHTS if x <= d)
t_i, t_ib = {}, {}
for d in NIGHTS:
    for n in verd[d]:
        if not r4(n, d): t_i.setdefault(n, d)
        if not (r4(n, d) or c3(n, d)): t_ib.setdefault(n, d)
out["(i) birth min 4"] = t_i; out["(i-b) birth min 3 + co-move"] = t_ib
# (iv)
streak = defaultdict(int); t_iv = {}
for d in NIGHTS:
    for n, t in verd[d].items():
        if n in t_iv: continue
        streak[n] = streak[n] + 1 if (t["size"] <= 3 and t["cohesion"] is not None and not t["pass_g3"]) else 0
        if streak[n] >= 3: t_iv[n] = d
out["(iv) small-only 3-night probation"] = t_iv
# (iii) from logs
for tag in ("fail_majority", "fail_majority_min505", "fail2_majority", "fail_strict", "all_strict", "all_majority"):
    t = {}
    for ln in open(f"a4_fold_{tag}.log"):
        if not ln.strip(): continue
        d = date.fromisoformat(ln[:10]); n = re.match(r"\S+ \| (.*) \(\d, ", ln).group(1)
        t.setdefault(n, d)
    out[f"(iii-{tag})"] = t
print("option | distinct themes taken | of which passed G3 on >= 1 window night | strong-RS (>= 80) live-stage when taken | of which Nascent")
for k, t in out.items():
    a, b_, c, e, real = taken_profile(t)
    print(f"{k} | {a} | {b_} | {c} | {e}")
    print("     real ones:", "; ".join(x[:60] for x in real))
    print("     strong early (Nascent, RS >= 80) when taken:", "; ".join(sorted(n[:60] for n in t if (row[n].get(t[n]) or {}).get("stage") == "Nascent" and ((row[n].get(t[n]) or {}).get("rs_avg") or 0) >= 80)))

# (i) delay: births 07-01..09-25 born at 2-3 that later reached 4 — engine nights from birth to first 4+ night
nights_all = sorted({r["d"] for r in B["themes"]})
delays = []
for n, h in hist.items():
    h.sort()
    if not (date(2026, 7, 1) <= h[0][0] <= date(2026, 9, 25)) or h[0][1] >= 4: continue
    f4 = next((d for d, k in h if k >= 4), None)
    if f4: delays.append(sum(1 for x in nights_all if h[0][0] < x <= f4))
delays.sort()
print(f"\n(i) delay for the {len(delays)} small-born themes that reached 4: engine nights birth->4 members median {delays[len(delays)//2]}, "
      f"quartiles {delays[len(delays)//4]}..{delays[3*len(delays)//4]}, max {delays[-1]}; within 1 night {sum(x<=1 for x in delays)}, > 5 nights {sum(x>5 for x in delays)}")
