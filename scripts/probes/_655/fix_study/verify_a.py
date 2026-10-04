"""#655 adversarial verify — independent re-derivation of the diagnosis/replay numbers."""
import pickle, sys, re, collections, statistics
from datetime import date, timedelta
import numpy as np
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence import theme_correctness as tc
S = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/"
d = pickle.load(open(S + "655_capture.pkl", "rb"))
themes, meta, scores, sector, excess, hist = d["themes"], d["board_meta"], d["scores"], d["sector"], d["excess"], d["history"]
M = {m["name"]: m for m in meta}

def rep(th, ex=excess):
    r = tc.build_correctness_report(th, ex, scores, sector)
    return r
def fmt(r):
    g3 = r["g3"]; g4 = r["g4"]
    return (f"G1 {r['g1']['pass']}/{r['g1']['n']}={r['g1']['rate_pct']} G2 {r['g2']['flagged']}/{r['g2']['n']}={r['g2']['rate_pct']} "
            f"G3 {g3['pass']}/{g3['n_judgeable']}={g3['rate_pct']} {'PASS' if g3['pass_bar'] else 'FAIL'} "
            f"G4 {g4['small']}/{g4['n_board']}={g4['rate_pct']} {'PASS' if g4['pass_bar'] else 'FAIL'}")

base = rep(themes)
print("V1 baseline:", fmt(base))
bt = {r["name"]: r for r in base["g3"]["themes"]}
# V2 size breakdown
bys = collections.defaultdict(list)
for r in base["g3"]["themes"]:
    k = r["size"]; bys[2 if k == 2 else 3 if k == 3 else 4].append(r)
for k in (2, 3, 4):
    rs = bys[k]
    print(f"V2 k={'>=4' if k==4 else k}: pass {sum(r['pass_g3'] for r in rs)}/{len(rs)} median p95 {statistics.median(r['c1_p95'] for r in rs):.3f}")
for k in (2, 3, 8):
    xs = [r["c1_p95"] for r in base["g3"]["themes"] if r["size"] == k]
    if xs: print(f"   size {k}: median p95 {statistics.median(xs):.3f} n={len(xs)}")
print("V2 tape-blind size<=3:", sum(1 for t in themes if len(t["tickers"]) <= 3))
# near chance
near = sorted((r["cohesion"] - r["c1_p95"], r["name"][:40], r["pass_g3"]) for r in base["g3"]["themes"] if abs(r["cohesion"] - r["c1_p95"]) <= 0.05)
print("V2 within +-0.05 of p95:", len(near)); [print("   ", f"{x[0]:+.3f}", x[1], x[2]) for x in near]

# nightly lists
txt = open(S + "655_rows.txt").read()
nights = {}
for dt, g3, g4 in re.findall(r"(\d{4}-\d{2}-\d{2}) \d\d:.*?\n  G3 fail: (\[.*?\])\n  G4 small: (\[.*?\])", txt, re.S):
    nights[date.fromisoformat(dt)] = (set(eval(g3)), set(eval(g4)))
D30, D01, D02 = date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)
capfail = set(base["g3"]["fail_list"])
A_nightly = nights[D30][0] & nights[D01][0] & nights[D02][0]
A_cap = nights[D30][0] & nights[D01][0] & capfail
print("V3 A set (3 nightly lists):", len(A_nightly), "| with capture as night 3:", len(A_cap), "| same:", A_nightly == A_cap)
for n in sorted(A_cap): print("    ", n[:55], len(M[n] and next(t for t in themes if t['name']==n)['tickers']), M[n]["stage"], M[n]["rs_avg"])
B_set = {t["name"] for t in themes if t["stage"] == "Fading" and len(t["tickers"]) < 3}
print("V4 B set:", len(B_set), sorted(n[:30] for n in B_set))
print("   B set with rs_avg (scored Fading):", [n[:30] for n in B_set if M[n]["rs_avg"] is not None])

def after(removed, label):
    th = [t for t in themes if t["name"] not in removed]
    r = rep(th)
    flips = [(x["name"][:35], bt[x["name"]]["pass_g3"], x["pass_g3"]) for x in r["g3"]["themes"] if x["pass_g3"] != bt[x["name"]]["pass_g3"]]
    g3 = r["g3"]
    net = sum(1 for x in g3["themes"] if bt[x["name"]]["pass_g3"])  # drift-free = baseline verdicts on survivors
    print(f"V4 {label}: removes {len(removed)} -> {fmt(r)}")
    print(f"     drift flips {len(flips)}: {flips}")
    print(f"     drift-free G3 (baseline verdicts on survivors): {net}/{g3['n_judgeable']} = {100*net/g3['n_judgeable']:.1f}")
    return r
after(A_cap, "A")
after(B_set, "B")
after(A_cap | B_set, "A+B")
# B weak-path only
after({n for n in B_set if M[n]["rs_avg"] is None}, "B weak-only")
