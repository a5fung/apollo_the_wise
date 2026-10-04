"""Pass 1 — facts per failing theme (G3 fail ∪ G4 small) from the 655 capture. Read-only."""
import pickle, sys, json, collections, re
from datetime import date
import numpy as np
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence import theme_correctness as tc
from agents.market_intelligence import market_adjusted_correlation as mac

CAP = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/655_capture.pkl"
ROWS = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/655_rows.txt"
OUT = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/655_study/"
d = pickle.load(open(CAP, "rb"))
themes, meta, scores, sector, excess, history, report = (
    d["themes"], d["board_meta"], d["scores"], d["sector"], d["excess"], d["history"], d["report"])
meta_by = {m["name"]: m for m in meta}
th_by = {t["name"]: t for t in themes}
g3rows = {r["name"]: r for r in report["g3"]["themes"]}
g3fail = set(report["g3"]["fail_list"]); g4small = set(report["g4"]["list"])
union = sorted(g3fail | g4small)
print("G3 fail", len(g3fail), "G4 small", len(g4small), "union", len(union), "both", len(g3fail & g4small))

# prior nightly lists
txt = open(ROWS).read()
nights = re.findall(r"(\d{4}-\d{2}-\d{2}) \d\d:.*?\n  G3 fail: (\[.*?\])\n  G4 small: (\[.*?\])", txt, re.S)
prior = {}
for dt, g3, g4 in nights:
    prior[dt] = (set(eval(g3)), set(eval(g4)))
print("prior nights", sorted(prior))

# history per theme
hist = collections.defaultdict(dict)  # name -> date -> (stage, tickers, source)
for r in history:
    hist[r["name"]][r["theme_date"]] = (r["stage"], list(r["tickers"] or []), r["source"])
all_hist_dates = sorted({r["theme_date"] for r in history})
print("history span", all_hist_dates[0], all_hist_dates[-1], len(all_hist_dates), "dates")

usable = tc.usable_set(excess)
g12 = tc.compute_g1_g2(themes, excess)
mrows = collections.defaultdict(list)
for r in g12["rows"]:
    mrows[r.theme].append(r)

# overlap with other live themes
homes = collections.defaultdict(set)
for t in themes:
    for m in t["tickers"]:
        homes[m].add(t["name"])

out = []
for n in union:
    t = th_by[n]; m = meta_by[n]; g3 = g3rows[n]
    h = hist[n]; dates = sorted(h)
    first = dates[0] if dates else None
    sizes = [(dd.isoformat(), len(h[dd][1]), h[dd][0]) for dd in dates]
    maxsize = max((len(h[dd][1]) for dd in dates), default=0)
    # members that left: present in any history row but not now
    ever = set();
    for dd in dates: ever |= set(h[dd][1])
    left = sorted(ever - set(t["tickers"]))
    # when each left (last date seen)
    left_when = {}
    for tk in left:
        last = max(dd for dd in dates if tk in h[dd][1])
        left_when[tk] = last.isoformat()
    # joined after birth
    founders = set(h[dates[0]][1]) if dates else set()
    joined = sorted(set(t["tickers"]) - founders)
    # gaps in history (dates missing vs all_hist_dates between first and last)
    span = [dd for dd in all_hist_dates if dates and dates[0] <= dd <= dates[-1]]
    gaps = len(span) - len(dates)
    stages_hist = collections.Counter(h[dd][0] for dd in dates)
    pers = sum(1 for dt in prior if n in prior[dt][0] or n in prior[dt][1])
    pers_g3 = sum(1 for dt in prior if n in prior[dt][0]); pers_g4 = sum(1 for dt in prior if n in prior[dt][1])
    members = []
    for r in mrows[n]:
        members.append({"tk": r.ticker, "sector": scores.get(r.ticker, {}).get("sector") or sector.get(r.ticker),
                        "rs": scores.get(r.ticker, {}).get("rs"), "usable": r.ticker in usable,
                        "own": None if r.own is None else round(r.own, 2),
                        "best_other": None if r.best_other is None else round(r.best_other, 2),
                        "best_other_theme": r.best_other_theme, "misfiled": r.misfiled,
                        "other_homes": sorted(homes[r.ticker] - {n})})
    overlap = collections.Counter()
    for tk in t["tickers"]:
        for o in homes[tk] - {n}: overlap[o] += 1
    out.append({
        "name": n, "size": len(t["tickers"]), "stage": t["stage"], "source": m["source"],
        "days_active": m["days_active"], "first_seen": first.isoformat() if first else None,
        "n_hist_rows": len(dates), "gaps": gaps, "max_size": maxsize, "rs_avg": m["rs_avg"], "score": m["score"],
        "parent": m["parent_theme"], "pct_above_20sma": m["pct_above_20sma"],
        "cohesion": g3["cohesion"], "c1_p95": g3["c1_p95"], "pass_g3": g3["pass_g3"],
        "g3_fail": n in g3fail, "g4_small": n in g4small,
        "persist_nights(of3)": pers, "persist_g3": pers_g3, "persist_g4": pers_g4,
        "stages_hist": dict(stages_hist), "size_path": sizes, "left": left_when, "joined_after_birth": joined,
        "members": members, "overlap_other_themes": dict(overlap),
        "n_usable": sum(1 for x in members if x["usable"]),
        "desc": (m["description"] or "")[:200],
    })
json.dump(out, open(OUT + "pass1.json", "w"), indent=1, default=str)

# compact print
print(f"\n{'name':62s} sz st  src  dA  first      maxsz coh    p95    pers  stagesHist")
for o in out:
    coh = "None" if o["cohesion"] is None else f"{o['cohesion']:.3f}"
    p95 = "None" if o["c1_p95"] is None else f"{o['c1_p95']:.3f}"
    print(f"{o['name'][:62]:62s} {o['size']:2d} {o['stage'][:2]} {o['source'][:4]} {o['days_active']:3d} {o['first_seen']} {o['max_size']:3d}  {coh:6s} {p95:6s} {o['persist_nights(of3)']}/3  {o['stages_hist']}")
print()
for o in out:
    print("==", o["name"], f"size={o['size']} stage={o['stage']} first={o['first_seen']} rows={o['n_hist_rows']} gaps={o['gaps']} rs_avg={o['rs_avg']} parent={o['parent']}")
    print("   size path:", [(s[0][5:], s[1], s[2][:2]) for s in o["size_path"]])
    print("   left:", o["left"], "| joined after birth:", o["joined_after_birth"])
    for mm in o["members"]:
        print(f"   {mm['tk']:6s} {str(mm['sector'])[:22]:22s} rs={mm['rs']} usable={mm['usable']} own={mm['own']} best_other={mm['best_other']} -> {mm['best_other_theme']} misfiled={mm['misfiled']} also_in={mm['other_homes']}")
    print("   overlap:", o["overlap_other_themes"])
    print("   desc:", o["desc"])
