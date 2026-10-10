"""verify #655 scope — independent re-derivation from the ONE capture (capture.raw.gz via load.py). $0, offline.
Reuses only: load.py (parser), board.board_at/g3_inputs/g3 (the anchor-proven live maths), production helpers.
Everything else (option rules, fold selection, taken lists, growth cross, churn) is re-written here."""
import json, re, sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from board import B, NIGHTS, STORED, ordered_board, board_at, g3, g3_inputs, mac  # noqa: E402
from agents.market_intelligence.theme_engine import (parent_industry_overlap, parent_word_similarity,  # noqa: E402
                                                     ASSIGN_COMOVE_BAR, PARENT_PASS_MIN_INDUSTRY_OVERLAP)

P = print
V = {d: {t["name"]: t for t in STORED[d]["g3"]["themes"]} for d in NIGHTS}

# ---------- A. stored-row facts ----------
P("== A. population + G3 share (stored 17:31 rows)")
P("nights:", [str(d) for d in NIGHTS])
fails = Counter(); judged = Counter()
for d in NIGHTS:
    for t in V[d].values():
        if t["cohesion"] is None: continue
        k = "2-3" if t["size"] <= 3 else "4+"
        judged[k] += 1; fails[k] += (not t["pass_g3"])
P(f"theme-nights judged {sum(judged.values())}; small {judged['2-3']}; G3 fails {sum(fails.values())}, of them 2-3-member {fails['2-3']}")
P(f"small pass {judged['2-3']-fails['2-3']}/{judged['2-3']}; 4+ pass {judged['4+']-fails['4+']}/{judged['4+']}")
sizes1 = [n for d in NIGHTS for n, t in V[d].items() if t["size"] < 2]
P("themes under 2 members on the board:", len(sizes1))

def night_rates(names, d, verd=None):
    verd = verd or V[d]
    j = [verd[n] for n in names if verd[n]["cohesion"] is not None]
    p = sum(bool(t["pass_g3"]) for t in j)
    sm = sum(1 for n in names if verd[n]["size"] < 3)
    return 100 * p / len(j), 100 * sm / len(names)

def summarize(tag, per_night):
    g3s = [x[0] for x in per_night]; g4s = [x[1] for x in per_night]
    P(f"  {tag}: G3 {sum(x >= 90 for x in g3s)}/10 ({min(g3s):.1f}-{max(g3s):.1f}) | G4 {sum(x <= 10 for x in g4s)}/10 ({min(g4s):.1f}-{max(g4s):.1f})")

summarize("baseline", [night_rates(list(V[d]), d) for d in NIGHTS])

# ---------- B. history ----------
hist = defaultdict(list)          # name -> [(d, size, stage, rs)]
for r in B["themes"]:
    if r["stage"] != "Retired" and r["tickers"]:
        hist[r["name"]].append((r["d"], len(r["tickers"]), r["stage"], r["rs_avg"]))
for v in hist.values(): v.sort()
def row_on(n, d):
    xs = [x for x in hist[n] if x[0] <= d]
    return xs[-1] if xs else None

# growers: born 07-01..09-25 at 2-3 under a name, reached >= 4 later (same name)
born_small = {n: h[0] for n, h in hist.items() if date(2026, 7, 1) <= h[0][0] <= date(2026, 9, 25) and h[0][1] in (2, 3)}
growers = {n for n, h in hist.items() if n in born_small and max(x[1] for x in h) >= 4}
P(f"\n== B. births 07-01..09-25 at 2-3 members: {len(born_small)} ({sum(v[1]==2 for v in born_small.values())} at 2); grew to 4+ same name: {len(growers)}")
ever4 = {n for n, h in hist.items() if max(x[1] for x in h) >= 4}

# ---------- C. options (i), (i-b), (ii), (iv) ----------
P("\n== C. options from stored verdicts")
taken = {}
def reached4(n, d): return any(x[1] >= 4 for x in hist[n] if x[0] <= d)
opt_i, opt_ib = [], []
t_i, t_ib = {}, {}
for d in NIGHTS:
    keep = [n for n in V[d] if reached4(n, d)]
    for n in set(V[d]) - set(keep): t_i.setdefault(n, d)
    opt_i.append(night_rates(keep, d))
    keep2 = [n for n in V[d] if reached4(n, d) or any(V[x].get(n, {}).get("size") == 3 and V[x][n]["pass_g3"] for x in NIGHTS if x <= d)]
    for n in set(V[d]) - set(keep2): t_ib.setdefault(n, d)
    opt_ib.append(night_rates(keep2, d))
summarize("(i) birth min 4", opt_i); summarize("(i-b) min 3 + co-move (in-window reads only)", opt_ib)
big = [night_rates([n for n in V[d] if V[d][n]["size"] >= 4], d)[0] for d in NIGHTS]
P(f"  (ii) G3 on 4+: {sum(x >= 90 for x in big)}/10 ({min(big):.1f}-{max(big):.1f})")
taken["(i)"] = t_i; taken["(i-b)"] = t_ib

def run_iv(seed_verdicts):
    streak = defaultdict(int); ret = {}; out = []
    for d, verd in seed_verdicts + [(d, V[d]) for d in NIGHTS]:
        for n, t in verd.items():
            if n in ret: continue
            streak[n] = streak[n] + 1 if (t["size"] <= 3 and t["cohesion"] is not None and not t["pass_g3"]) else 0
            if streak[n] >= 3: ret[n] = d
        if d in V:
            out.append(night_rates([n for n in V[d] if n not in ret], d))
    return out, {n: d for n, d in ret.items()}
iv, t_iv = run_iv([])
summarize("(iv) 3-night small probation, cold start 09-28", iv)
taken["(iv)"] = t_iv

# seed nights: recompute G3 for engine nights before 09-28 using the nearest score date (approx: order + scores)
import re as _re
def _coll(s): return _re.sub(r"[^0-9a-z]", "", s.lower())
seed = []
# anchor the ordering approximation on a stored night first
th, _, _ = ordered_board(NIGHTS[0])
alt = sorted(th, key=lambda t: _coll(t["name"]))
ra = {x["name"]: x["pass_g3"] for x in g3(alt, NIGHTS[0])["themes"]}
P(f"  ordering check on {NIGHTS[0]}: approx-collation order reproduces {sum(ra[n] == V[NIGHTS[0]][n]['pass_g3'] for n in ra)}/{len(ra)} stored verdicts")
for d in [date(2026, 9, 24), date(2026, 9, 25)]:
    bd = sorted([r for r in board_at(d) if r["tickers"]], key=lambda t: _coll(t["name"]))
    sd = [x for x in B["scores"] if x <= d]
    if not sd:
        B["scores"][d] = B["scores"][min(B["scores"])]   # approximation: nearest later score date
    r = g3(bd, d)
    seed.append((d, {x["name"]: {**x, "size": len(next(t for t in bd if t["name"] == x["name"])["tickers"])} for x in r["themes"]}))
    P(f"  seed night {d}: board {len(bd)} G3 {r['pass']}/{r['n_judgeable']}")
iv_s, t_iv_s = run_iv(seed)
summarize("(iv) seeded with 09-24/09-25", iv_s)
taken["(iv) seeded"] = t_iv_s

# ---------- D. fold (iii) re-implemented ----------
eco = B["eco"]; ind = {t: (v.get("industry") or None) for t, v in B["industry"].items()}
def corr_ok(m, tickers, excess):
    if m in tickers: return True, "shared"
    if excess.get(m) is None: return None, None
    bs = mac.build_baskets([{"name": "x", "stage": "x", "tickers": tickers}], excess, stages=("x",))
    if not bs: return None, None
    c, _, _ = mac.correlate(excess[m], bs[0])
    return (None, None) if c is None else (c >= ASSIGN_COMOVE_BAR, "tape")

def fold_night(d, which, min505=True, prev_fail=None):
    board, _, _ = ordered_board(d)
    excess, usable, *_ = g3_inputs(d)
    folds = {}; zero_move = 0
    for s in board:
        k = len(s["tickers"])
        if not 2 <= k <= 3: continue
        if which == "fail" and V[d][s["name"]]["pass_g3"]: continue
        if which == "prevfail" and s["name"] not in prev_fail: continue
        e = eco.get(s["name"])
        if not e or e == "E-UNASSIGNED": continue
        best = None
        for c in board:
            if c["name"] == s["name"] or eco.get(c["name"]) != e or len(c["tickers"]) < 4: continue
            if sum(m in usable for m in c["tickers"]) < 3: continue
            res = [corr_ok(m, c["tickers"], excess) for m in s["tickers"]]
            ok = [m for m, (v, _) in zip(s["tickers"], res) if v]
            if len(ok) < (k + 1) // 2: continue
            sh = len(set(s["tickers"]) & set(c["tickers"]))
            io = parent_industry_overlap(s, c, ind)
            if min505 and sh == 0 and io < PARENT_PASS_MIN_INDUSTRY_OVERLAP: continue
            key = (-sh, -io, -parent_word_similarity({"name": s["name"], "description": s.get("desc")},
                                                     {"name": c["name"], "description": c.get("desc")}), -len(c["tickers"]), c["name"])
            if best is None or key < best[0]: best = (key, c["name"], ok)
        if best:
            folds[s["name"]] = (best[1], best[2])
            zero_move += all(m in next(t for t in board if t["name"] == best[1])["tickers"] for m in best[2])
    gained = defaultdict(list)
    for s, (h, ok) in folds.items(): gained[h] += ok
    new = [{**t, "tickers": list(t["tickers"]) + [m for m in dict.fromkeys(gained.get(t["name"], [])) if m not in t["tickers"]]}
           for t in board if t["name"] not in folds]
    r = g3(new, d)
    rv = {x["name"]: x for x in r["themes"]}
    j = [x for x in r["themes"] if x["cohesion"] is not None]
    g3p = 100 * sum(bool(x["pass_g3"]) for x in j) / len(j)
    g4p = 100 * sum(len(t["tickers"]) < 3 for t in new) / len(new)
    flips = [h for h in gained if V[d][h]["pass_g3"] and not rv[h]["pass_g3"]]
    return g3p, g4p, folds, zero_move, flips

P("\n== D. fold (iii) re-implemented")
for tag, which, m5 in [("(iii) fail-only, #505 min", "fail", True), ("(iii) fold every small, #505 min", "all", True),
                       ("(iii) fold every small, no min", "all", False)]:
    per = []; t = {}; nf = 0; zm = 0; fl = 0
    for d in NIGHTS:
        a, b_, folds, z, flips = fold_night(d, which, m5)
        per.append((a, b_)); nf += len(folds); zm += z; fl += len(flips)
        for n in folds: t.setdefault(n, d)
    summarize(tag, per)
    P(f"     folds {nf} theme-nights, {len(t)} distinct; folds moving NO new stock into the home {zm}; home flipped to fail {fl}")
    taken[tag] = t
# prior-night verdict variant (rule acts on yesterday's read; 09-28 uses the seeded 09-25 read)
prev = {NIGHTS[0]: {n for n, x in seed[-1][1].items() if x["cohesion"] is not None and not x["pass_g3"]}}
for i in range(1, len(NIGHTS)):
    prev[NIGHTS[i]] = {n for n, x in V[NIGHTS[i - 1]].items() if not x["pass_g3"]}
per = []; t = {}
for d in NIGHTS:
    a, b_, folds, _, _ = fold_night(d, "prevfail", True, prev[d])
    per.append((a, b_)); [t.setdefault(n, d) for n in folds]
summarize("(iii) acting on LAST night's fail, #505 min", per)
taken["(iii) prev-night"] = t

# ---------- E. cost per option: co-moving, strong early (Nascent RS>=80), later grew ----------
P("\n== E. themes taken per option")
for tag, t in taken.items():
    real = [n for n in t if any(V[d].get(n, {}).get("pass_g3") for d in NIGHTS)]
    strong = []
    for n, d in t.items():
        r = row_on(n, d)
        if r and r[2] == "Nascent" and (r[3] or 0) >= 80: strong.append(n)
    smalls = [n for n in t if n in born_small]
    P(f"  {tag}: taken {len(t)} | co-moving on >=1 night {len(real)} | strong early {len(strong)} | "
      f"born small 07-01..09-25 {len(smalls)}, of them grew to 4+ {len([n for n in smalls if n in growers])} | ever 4+ (any date) {len([n for n in t if n in ever4])}")
    if len(strong) <= 3: P("     strong early:", strong)

# ---------- F. churn re-derivation ----------
P("\n== F. churn, 14 engine nights")
on = defaultdict(dict)
for r in B["themes"]:
    if r["stage"] != "Retired" and r["tickers"]: on[r["d"]][r["name"]] = r
nights = sorted(on); W = nights[-14:]; S = [nights[-15]] + W
exits = []; rets = []
for i in range(1, len(S)):
    for n in on[S[i - 1]]:
        if n not in on[S[i]]:
            back = next((x for x in S[i + 1:] if n in on[x]), None)
            exits.append((n, S[i], back)); back and rets.append((n, S[i], back))
P(f"  window {W[0]}..{W[-1]}: exits {len(exits)}, same-name returns {len(rets)} ({len({r[0] for r in rets})} names)")
# board-based (get_active_themes(7)) versions
bset = {d: {r['name'] for r in board_at(d) if r['tickers']} for d in S}
bex = [(n, S[i]) for i in range(1, len(S)) for n in bset[S[i - 1]] if n not in bset[S[i]]]
bret = [(n, S[i]) for i in range(1, len(S)) for n in bset[S[i - 1]] if n not in bset[S[i]] and any(n in bset[x] for x in S[i + 1:])]
P(f"  board-based: exits {len(bex)}, same-name returns {len(bret)}")
P(f"  return-night source: {dict(Counter(on[b][n]['source'] for n, _, b in rets))}")
# events per night per name (raw, no precedence) to sanity-check the cause split
evn = defaultdict(lambda: defaultdict(set))
for e in B["events"]:
    d = date.fromisoformat(e["et"][:10]); blob = (e["summary"] or "") + " " + (e["detail"] or "")
    for n, off, back in rets:
        if d == off and (f"'{n}'" in blob or f'"{n}"' in blob or n in blob):
            evn[(n, off)][e["event_type"]].add(e["id"])
P("  same-name returns by event types naming them on the off night:")
for x in Counter(tuple(sorted(evn[(n, o)])) for n, o, _ in rets).most_common():
    P("    ", x)
# Appalachian 10-01 cap row + 10-07 cap rows
for e in B["events"]:
    if e["event_type"] in ("theme_sector_cap_not_absorbed",) and e["et"][:10] in ("2026-10-01", "2026-10-07"):
        j = json.loads(e["detail"]); m = j.get("members") or {}
        P(f"  cap row {e['et'][:10]}: source={j.get('source')[:45]!r} target={str(j.get('target'))[:45]!r} "
          f"members_in_row={len(m)} paths={dict(Counter(v.get('path') for v in m.values()))} verdicts={dict(Counter(v.get('verdict') for v in m.values()))}")
# Pass-1.5 removals re-made within a week
p15 = [(n, o) for n, o, _ in [(x[0], x[1], x[2]) for x in exits] if "theme_pass1_5_absorption" in
       {e["event_type"] for e in B["events"] if e["et"][:10] == str(o) and n in ((e["summary"] or "") + (e["detail"] or ""))}]
P(f"  Pass-1.5 exits (event names the theme that night): {len(p15)}")
