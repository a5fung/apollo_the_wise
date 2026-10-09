"""#505 parent picker — offline replay, $0, no DB, no model calls.

Replays today's candidate-parent ranking and the new CLOSENESS ranking (his ruling
2026-10-09) over the saved 10-08 board, on the 9 live parent links of that board.

Inputs (captured once):
  ../_505/pull_2026-10-09/q3_board.out   the 10-08 board (names, stages, members, descriptions)
  ../_505/pull_2026-10-09/q4_eco.out     theme -> ecosystem
  ../_505/pull_2026-10-09/q2_cooldowns.out  pair cooldowns
  q8_industry.out                        mi_ticker_overrides sector/industry for every board member
Output: replay_out.txt
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from agents.market_intelligence import theme_engine as te  # noqa: E402
from agents.market_intelligence.theme_merge_arm import pair_key  # noqa: E402
from agents.market_intelligence.theme_ecosystems import E_UNASSIGNED  # noqa: E402

D = HERE.parent / "_505" / "pull_2026-10-09"
board = json.load(open(D / "q3_board.out"))["rows"]
for t in board:
    t["tickers"] = t["tickers"] or []
eco = {r["name"]: r["e"] for r in json.load(open(D / "q4_eco.out"))}
live_cool = {pair_key(r["a"], r["b"]) for r in json.load(open(D / "q2_cooldowns.out")) if r["live"]}
industry = {r["t"]: r["i"] for r in json.load(open(HERE / "q8_industry.out")) if r.get("i")}

# Score functions come from the engine when built; fall back to local copies for the pre-build replay.
industry_overlap = getattr(te, "parent_industry_overlap", None)
word_similarity = getattr(te, "parent_word_similarity", None)
SCORER_SOURCE = "engine"
if industry_overlap is None or word_similarity is None:
    sys.path.insert(0, str(HERE))
    from closeness import parent_industry_overlap as industry_overlap, parent_word_similarity as word_similarity  # noqa: E402
    SCORER_SOURCE = "probe closeness.py (pre-build)"

out: list[str] = []
P = out.append


def eligible_candidates(c, themes, *, ignore_stage=False, ignore_cooldown=False):
    """Mirror of propose_parent_candidates' per-child eligibility (the child itself is
    treated as childless). Returns (list of candidate dicts, reasons the real parent is out)."""
    bad = ("Retired",) if ignore_stage else ("Retired", "Fading")
    live = [t for t in themes if t.get("stage") not in bad and t.get("tickers")]
    parent_of = {t["name"]: t["parent_theme"] for t in live if t.get("parent_theme") and t["name"] != c["name"]}
    code = eco.get(c["name"])
    res = []
    for p in live:
        if p["name"] == c["name"] or eco.get(p["name"]) != code:
            continue
        if len(p["tickers"]) <= len(c["tickers"]):
            continue
        if not ignore_cooldown and pair_key(c["name"], p["name"]) in live_cool:
            continue
        if c["name"] in te._containment_ancestors(p["name"], parent_of):
            continue
        res.append(p)
    return res


def why_out(c, p, ignore_stage=False):
    r = []
    if not ignore_stage and c["stage"] == "Fading":
        r.append("child Fading")
    if p["stage"] == "Retired" or (not ignore_stage and p["stage"] == "Fading"):
        r.append(f"parent {p['stage']}")
    if eco.get(p["name"]) != eco.get(c["name"]):
        r.append("different ecosystem")
    if len(p["tickers"]) <= len(c["tickers"]):
        r.append(f"parent not broader ({len(p['tickers'])} vs {len(c['tickers'])})")
    if pair_key(c["name"], p["name"]) in live_cool:
        r.append("pair under cooldown")
    return r


def key_today(c, p):
    shared_tk = len(set(c["tickers"]) & set(p["tickers"]))
    shared_tok = len(te._name_tokens(c["name"]) & te._name_tokens(p["name"]))
    return (-shared_tk, -shared_tok, -len(p["tickers"]), p["name"])


def key_new(c, p):
    shared_tk = len(set(c["tickers"]) & set(p["tickers"]))
    return (-shared_tk, -round(industry_overlap(c, p, industry), 6),
            -round(word_similarity(c, p), 6), -len(p["tickers"]), p["name"])


by = {t["name"]: t for t in board}
links = [t for t in board if t.get("parent_theme") and t["stage"] != "Retired"]
all_members = {tk for t in board for tk in t["tickers"]}
missing = sorted(tk for tk in all_members if tk not in industry)
P(f"board 10-08: {len(board)} rows; live parent links: {len(links)}")
P(f"board members: {len(all_members)}; with an industry in mi_ticker_overrides: {len(all_members) - len(missing)}; "
  f"without: {len(missing)} {missing}")


def run(view, **kw):
    P(f"\n=== VIEW: {view} ===")
    hits_today = hits_new = 0
    worse = 0
    rows = []
    for c in links:
        p = by.get(c["parent_theme"])
        cands = eligible_candidates(c, board, **kw)
        names = [x["name"] for x in cands]
        child_out = (not kw.get("ignore_stage") and c["stage"] == "Fading")
        if p is None or p["name"] not in names or child_out:
            reasons = why_out(c, p, kw.get("ignore_stage", False)) if p else ["parent not on board"]
            rows.append((c["name"], p and p["name"], len(cands), None, None, "; ".join(reasons) or "?"))
            continue
        rt = sorted(cands, key=lambda x: key_today(c, x))
        rn = sorted(cands, key=lambda x: key_new(c, x))
        a = [x["name"] for x in rt].index(p["name"]) + 1
        b = [x["name"] for x in rn].index(p["name"]) + 1
        hits_today += a == 1
        hits_new += b == 1
        worse += b > a
        rows.append((c["name"], p["name"], len(cands), a, b, ""))
        P(f"\n  {c['name']} -> {p['name']}  (eligible candidates {len(cands)})")
        P(f"    real parent: industry overlap {industry_overlap(c, p, industry):.2f}, word sim {word_similarity(c, p):.3f}")
        P(f"    today top-3: {[x['name'] for x in rt[:3]]}")
        P(f"    new top-3:   " + str([(x['name'], round(industry_overlap(c, x, industry), 2), round(word_similarity(c, x), 3)) for x in rn[:3]]))
    P(f"\n  {'child':58} {'real parent':55} {'n':>3} today new  note")
    for r in rows:
        P(f"  {r[0][:58]:58} {str(r[1])[:55]:55} {r[2]:>3} {str(r[3] or '-'):>5} {str(r[4] or '-'):>3}  {r[5]}")
    P(f"  real parent ranked FIRST: today {hits_today}/{len(links)}, new {hits_new}/{len(links)}; "
      f"links where new ranks it LOWER than today: {worse}")
    return hits_today, hits_new, worse


strict = run("STRICT — the engine's own eligibility on the 10-08 board (the pre-set bar)")
relaxed = run("STAGE IGNORED — Fading treated as live (stages at link time differ); all other rules kept",
              ignore_stage=True)
P(f"\nBAR (pre-set): new first on >=5 of 9 AND never lower than today. "
  f"STRICT: new {strict[1]}/9, lower-than-today {strict[2]} -> {'MET' if strict[1] >= 5 and strict[2] == 0 else 'NOT MET'}")

# SUPPLEMENTARY (not the bar): tonight's whole childless queue — which first pick changes?
P("\n=== SUPPLEMENTARY: first pick per childless theme on the 10-08 board, today vs new (Arm-B deferral not applied) ===")
live_now = [t for t in board if t.get("stage") not in ("Retired", "Fading") and t.get("tickers")]
changed = same = 0
ex = []
for c in live_now:
    if c.get("parent_theme") or eco.get(c["name"]) in (None, E_UNASSIGNED):
        continue
    cands = eligible_candidates(c, board)
    if not cands:
        continue
    t1 = min(cands, key=lambda x: key_today(c, x))
    n1 = min(cands, key=lambda x: key_new(c, x))
    if t1["name"] == n1["name"]:
        same += 1
    else:
        changed += 1
        ex.append((c["name"], t1["name"], n1["name"], industry_overlap(c, t1, industry), industry_overlap(c, n1, industry),
                   word_similarity(c, n1), len(cands)))
P(f"  childless themes with >=1 eligible candidate: {same + changed}; first pick unchanged {same}, changed {changed}")
for e in ex:
    P(f"  {e[0]}  [{e[6]} cands]\n     today: {e[1]} (industry {e[3]:.2f})\n     new:   {e[2]} (industry {e[4]:.2f}, words {e[5]:.3f})")
P(f"\nscorers: {SCORER_SOURCE}")
(HERE / "replay_out.txt").write_text("\n".join(out) + "\n")
print("\n".join(out))
