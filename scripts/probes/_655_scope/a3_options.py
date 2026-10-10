"""#655 scope Q-A step 3: options (i), (i-b), (ii), (iv) on the 10 nights, DRIFT-FREE (every surviving theme
keeps its stored verdict — the anchor reproduced 1,237 of 1,237 stored verdicts, a0_anchor.out). $0.
PRE-STATED RULES (written before running):
 (i)   birth minimum 4: a theme is on the board on night d only if, under its name, it had >= 4 members on some
       night <= d (approximates 'born later, when it reached 4' — OPTIMISTIC: such themes grew by assignment
       INTO an existing theme, which would not exist).
 (i-b) birth minimum 3 + co-movement: on the board if (i) holds, OR it had exactly 3 members on an in-window
       night <= d whose stored G3 verdict passed (the only tape read a 3-member group has; see doc).
 (ii)  measurement: G3 scored on themes with >= 4 members; 2-3-member themes reported separately.
 (iv)  small-theme probation: a theme with 2-3 members that fails G3 on 3 consecutive nightly reads (rule A's
       streak logic, ONLY counting nights it had 2-3 members; a 4+ night resets) is retired; once retired stays off.
"""
from collections import defaultdict
from datetime import date
from board import B, NIGHTS, STORED

rows = B["themes"]
hist = defaultdict(list)
for r in rows:
    if r["stage"] != "Retired" and r["tickers"]:
        hist[r["name"]].append((r["d"], len(r["tickers"]), r["stage"], r["rs_avg"]))

def reached4_by(name, d):
    return any(n >= 4 for dd, n, *_ in hist[name] if dd <= d)

verd = {d: {t["name"]: t for t in STORED[d]["g3"]["themes"]} for d in NIGHTS}
board_names = {d: list(verd[d]) for d in NIGHTS}

def ok3comove_by(name, d):
    return any(verd[x].get(name, {}).get("size") == 3 and verd[x][name]["pass_g3"] for x in NIGHTS if x <= d)

def rate(names, d):
    j = [verd[d][n] for n in names if verd[d][n]["cohesion"] is not None]
    p = sum(t["pass_g3"] for t in j)
    small = sum(1 for n in names if verd[d][n]["size"] < 3)
    return p, len(j), small, len(names)

print("night | baseline G3 | G4 | (i) G3 | G4 | removed | (i-b) G3 | G4 | removed | (ii) G3 on 4+ | small reported apart | (iv) G3 | G4 | retired so far")
streak = defaultdict(int); retired = set(); tot = defaultdict(set)
for d in NIGHTS:
    names = board_names[d]
    out = []
    p, j, s, n = rate(names, d); out.append(f"{p}/{j} {100*p/j:.1f}% | {s}/{n} {100*s/n:.1f}%")
    keep_i = [x for x in names if reached4_by(x, d)]
    rem_i = set(names) - set(keep_i); tot["i"] |= rem_i
    p, j, s, n = rate(keep_i, d); out.append(f"{p}/{j} {100*p/j:.1f}% | {s}/{n} {100*s/n:.1f}% | {len(rem_i)}")
    keep_ib = [x for x in names if reached4_by(x, d) or ok3comove_by(x, d)]
    rem_ib = set(names) - set(keep_ib); tot["ib"] |= rem_ib
    p, j, s, n = rate(keep_ib, d); out.append(f"{p}/{j} {100*p/j:.1f}% | {s}/{n} {100*s/n:.1f}% | {len(rem_ib)}")
    big = [x for x in names if verd[d][x]["size"] >= 4]
    sm = [x for x in names if verd[d][x]["size"] <= 3]
    p, j, _, _ = rate(big, d); ps, js, _, _ = rate(sm, d)
    out.append(f"{p}/{j} {100*p/j:.1f}% | {ps}/{js} {100*ps/js:.1f}%")
    # (iv)
    for x in names:
        t = verd[d][x]
        if x in retired:
            continue
        if t["size"] <= 3 and t["cohesion"] is not None and not t["pass_g3"]:
            streak[x] += 1
        else:
            streak[x] = 0
        if streak[x] >= 3:
            retired.add(x)
    keep_iv = [x for x in names if x not in retired]
    p, j, s, n = rate(keep_iv, d); out.append(f"{p}/{j} {100*p/j:.1f}% | {s}/{n} {100*s/n:.1f}% | {len(retired)}")
    print(d, "|", " | ".join(out))

def describe(names):
    outl = []
    for x in sorted(names):
        h = hist[x]
        last = max(h)
        mx = max(n for _, n, *_ in h)
        outl.append(f"  {x} | first {h[0][0]} at {h[0][1]} | max {mx} | last {last[0]} {last[2]} n={last[1]} rs={last[3] and round(last[3])}")
    return "\n".join(outl)

print(f"\n(i) themes removed on >= 1 night: {len(tot['i'])}")
print(describe(tot["i"]))
print(f"\n(i-b) themes removed on >= 1 night: {len(tot['ib'])}")
print(f"\n(iv) themes retired by the 3-night small-only streak: {len(retired)}")
print(describe(retired))
# who among retired later passed / grew
last = NIGHTS[-1]
for x in sorted(retired):
    passes_later = [d for d in NIGHTS if x in verd[d] and verd[d][x]["pass_g3"]]
    print("   ", x[:70], "| nights passing G3 in window:", [str(d)[5:] for d in passes_later])
