"""#505 10-09 read — offline replay of propose_parent_candidates over the captured 10-08 board. $0, no DB.
Reads pull_2026-10-09/*.out (captured once). Writes offline_queue_2026-10-09.txt."""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from agents.market_intelligence import theme_engine as te
from agents.market_intelligence.theme_merge_arm import pair_key, propose_merge_pairs
from agents.market_intelligence.theme_ecosystems import E_UNASSIGNED
D = Path(__file__).parent / "pull_2026-10-09"
b = json.load(open(D / "q3_board.out")); board = b["rows"]
eco = {r["name"]: r["e"] for r in json.load(open(D / "q4_eco.out"))}
cool = json.load(open(D / "q2_cooldowns.out"))
live_cool = {pair_key(r["a"], r["b"]) for r in cool if r["live"]}
sect = {r["t"]: r["s"] for r in json.load(open(D / "q5_sect.out"))}
for t in board: t["tickers"] = t["tickers"] or []
out = []; P = out.append
live = [t for t in board if t["stage"] != "Retired" and t["tickers"]]
arm_b = {pair_key(a["name"], o["name"]) for a, o in propose_merge_pairs(live, cooldown_pairs=live_cool, sectors_by_ticker=sect, max_pairs=None)}
q = te.propose_parent_candidates(board, eco, cooldown_pairs=live_cool, arm_b_pairs=arm_b, cap=None)
P(f"board {b['theme_date']}: {len(board)} rows, {len(live)} non-Retired with members; stages {Counter(t['stage'] for t in board)}")
P(f"live cooldown pairs {len(live_cool)} (all rows {len(cool)}); arm-B territory pairs {len(arm_b)}")
P(f"TONIGHT'S UNCAPPED QUEUE (one candidate per child): {len(q)}")
for c in q: P(f"  {c['child']!r} -> {c['parent']!r}  {c['why']}")
# full un-adjudicated pair space: every (child, broader same-eco live theme) pair not cooled, not a cycle
elig = [t for t in board if t["stage"] not in ("Retired","Fading") and t["tickers"]]
parent_of = {t["name"]: t["parent_theme"] for t in elig if t.get("parent_theme")}
pairs = []; per_child = Counter()
childless = [c for c in elig if not c.get("parent_theme") and eco.get(c["name"]) not in (None, E_UNASSIGNED)]
for c in childless:
    for p in elig:
        if p is c or eco.get(p["name"]) != eco.get(c["name"]) or len(p["tickers"]) <= len(c["tickers"]): continue
        if c["name"] in te._containment_ancestors(p["name"], parent_of): continue
        k = pair_key(c["name"], p["name"])
        pairs.append((c["name"], p["name"], k in live_cool, k in arm_b, len(set(c["tickers"]) & set(p["tickers"]))))
        if k not in live_cool: per_child[c["name"]] += 1
un = [x for x in pairs if not x[2]]
P(f"\nchildless non-Fading themes in a real ecosystem: {len(childless)}")
P(f"ALL candidate pairs (child x every broader same-ecosystem theme): {len(pairs)}; under live cooldown {sum(x[2] for x in pairs)}; NOT yet adjudicated {len(un)} (of which Arm-B territory {sum(x[3] for x in un)})")
P(f"  un-adjudicated pairs sharing >=1 ticker: {sum(1 for x in un if x[4]>0)}")
P(f"  nights at cap {te.PARENT_PASS_CAP_PER_NIGHT} to ask them all (ignoring new births/cooldown expiry): {-(-len(un)//te.PARENT_PASS_CAP_PER_NIGHT)}")
P(f"  per-child remaining depth: {sorted(per_child.values(), reverse=True)}")
# catch-all
ua = [t for t in board if t["stage"] != "Retired" and t["tickers"] and eco.get(t["name"], E_UNASSIGNED) == E_UNASSIGNED]
P(f"\nE-UNASSIGNED / unmapped non-Retired themes: {len(ua)}")
for t in ua: P(f"  {t['name']!r} stage={t['stage']} parent={t.get('parent_theme')} mapped={t['name'] in eco} members={len(t['tickers'])} {t['tickers']}")
P(f"\nparented non-Retired on board: {[ (t['name'], t['parent_theme'], t['stage']) for t in board if t.get('parent_theme') and t['stage']!='Retired']}")
P(f"\necosystem sizes among eligible: {Counter(eco.get(t['name'],'NONE') for t in elig).most_common()}")
Path(__file__).with_suffix(".txt").write_text("\n".join(out) + "\n")
print("\n".join(out))
# signal split of the un-adjudicated pair space
def _tok(a,b): return len(te._name_tokens(a) & te._name_tokens(b))
sig = Counter(("tk>0" if x[4] else "tk=0", min(_tok(x[0], x[1]), 2)) for x in un)
extra = f"\nun-adjudicated pairs by (shared tickers, shared name tokens capped at 2): {sorted(sig.items())}"
print(extra)
with open(Path(__file__).with_suffix(".txt"), "a") as f: f.write(extra + "\n")
