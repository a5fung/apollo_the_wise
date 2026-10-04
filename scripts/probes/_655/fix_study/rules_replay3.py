"""#655 — part 3: (i) Rule A sensitivity to K (information for the operator's ruling, NOT a tuning —
K=3 stays the pre-declared value); (ii) Rule B: of the 48 shell regrowths, how many became a theme
that then lived >= 5 non-Fading nights; (iii) 1-member rows in history (the #491 remnant hole)."""
import pickle, sys, collections
from datetime import date
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence import theme_correctness as tc
SCRATCH = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/"
OUT = SCRATCH + "655_study/"
d = pickle.load(open(SCRATCH + "655_capture.pkl", "rb"))
themes, meta, scores, sector, excess, history = d["themes"], d["board_meta"], d["scores"], d["sector"], d["excess"], d["history"]
meta_by = {m["name"]: m for m in meta}; usable = tc.usable_set(excess)
now_pass = {r["name"]: r["pass_g3"] for r in d["report"]["g3"]["themes"]}
lines = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); lines.append(s)
by_date = collections.defaultdict(list); hist = collections.defaultdict(dict)
for r in history: by_date[r["theme_date"]].append(r); hist[r["name"]][r["theme_date"]] = r
all_dates = sorted(by_date); sim_dates = [x for x in all_dates if x >= date(2026, 9, 8)]
def board_at(dt):
    return [{"name": r["name"], "stage": r["stage"], "tickers": list(r["tickers"] or [])} for r in by_date[dt] if r["stage"] != "Retired"]
verdict = {}
for dt in sim_dates:
    for r in tc.compute_g3(board_at(dt), excess, usable, scores, sector)["themes"]:
        verdict[(r["name"], dt)] = r["pass_g3"]

P("################ RULE A — sensitivity to K (pre-declared K=3; others are information for his ruling)")
for K in (2, 3, 4, 5):
    streak = collections.defaultdict(int); retired = {}
    for dt in sim_dates:
        for t in board_at(dt):
            n = t["name"]
            if n in retired: continue
            v = verdict.get((n, dt))
            if v is False:
                streak[n] += 1
                if streak[n] >= K: retired[n] = dt
            elif v is True: streak[n] = 0
    false_kills = [n for n in retired if now_pass.get(n)]
    boardA = [t for t in themes if t["name"] not in retired]
    rep = tc.build_correctness_report(boardA, excess, scores, sector)
    nights_pass = 0
    for dt in sim_dates[-3:]:
        b = [t for t in board_at(dt) if not (t["name"] in retired and retired[t["name"]] < dt)]
        r = tc.build_correctness_report(b, excess, scores, sector)
        nights_pass += bool(r["g3"]["pass_bar"])
    P(f"  K={K}: retire events {len(retired)} | false kills (on board + pass G3 now) {len(false_kills)} {false_kills} | "
      f"10-02 board: G3 {rep['g3']['rate_pct']}% {'PASS' if rep['g3']['pass_bar'] else 'FAIL'} G4 {rep['g4']['rate_pct']}% | G3 passes on last 3 nights: {nights_pass}/3")

P("\n################ RULE B — of the shell regrowths, which became a theme that then lived >= 5 non-Fading nights?")
rec = []
for name, rows in hist.items():
    ds = sorted(rows); i = 0
    while i < len(ds):
        r = rows[ds[i]]
        if r["stage"] == "Fading" and 0 < len(r["tickers"] or []) < 3:
            j = i
            while j < len(ds) and rows[ds[j]]["stage"] == "Fading" and 0 < len(rows[ds[j]]["tickers"] or []) < 3: j += 1
            if j < len(ds) and rows[ds[j]]["stage"] != "Retired" and rows[ds[j]]["tickers"]:
                later = [rows[x] for x in ds[j:]]
                nonfading = sum(1 for x in later if x["stage"] not in ("Fading", "Retired"))
                maxsz = max(len(x["tickers"] or []) for x in later)
                rec.append((name, ds[i], j - i, nonfading, maxsz, name in meta_by and meta_by[name]["stage"] != "Fading"))
            i = j
        else: i += 1
P(f"  regrowth episodes {len(rec)}; afterwards >=5 non-Fading nights: {sum(1 for e in rec if e[3] >= 5)}; "
  f"afterwards >=4 members: {sum(1 for e in rec if e[4] >= 4)}; non-Fading on today's board: {sum(1 for e in rec if e[5])}")
for e in sorted(rec, key=lambda x: -x[3])[:15]: P("    ", e)
P("  shell-nights before regrowth for the >=5-non-Fading-night survivors:", sorted(collections.Counter(e[2] for e in rec if e[3] >= 5).items()))

P("\n################ 1-member rows (the remnant a #491 move out of a pair leaves; no guard drops it)")
one = [r for r in history if len(r["tickers"] or []) == 1]
P(f"  1-member rows in 60 days: {len(one)}; stages {collections.Counter(r['stage'] for r in one)}; distinct themes {len({r['name'] for r in one})}")
open(OUT + "rules_replay3.txt", "w").write("\n".join(lines) + "\n")
