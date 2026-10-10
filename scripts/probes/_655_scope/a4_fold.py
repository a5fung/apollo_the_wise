"""#655 scope Q-A option (iii): fold a 2-3-member theme into its closest same-ecosystem theme when its members
pass the membership test there. $0, capture only. PRE-STATED (written before the run):
  * Population: every board theme with 2-3 members on each of the 10 nightly reads (the stored audit board).
  * Candidates: other board themes in the SAME ecosystem (mi_theme_ecosystems e_code — today's mapping applied
    backward; it has no date column), e_code not E-UNASSIGNED, with >= 4 members (amended after the first run
    crashed on a chain — a 3-member target was itself being folded; no result had been read) of which >= 3 have
    usable history (the membership test's own basket minimum). Any stage.
  * Test: each member of the small theme vs the candidate's basket (market-adjusted, 60 sessions strictly before
    the night, mac.correlate; a member already in the candidate counts as passing) at ASSIGN_COMOVE_BAR 0.35.
  * STRICT fold: every member passes. MAJORITY fold: at least half pass (passing members move, the rest released).
  * Pick among qualifying candidates by the #505 closeness key: shared members, industry overlap, word
    similarity, size, name.
  * Two scopes: (iii-all) every qualifying small theme folds; (iii-fail) only small themes failing G3 that night.
  * G3 after the fold: the full night recomputed with the modified board (compute_g3), AND drift-free (unchanged
    themes keep stored verdicts; only targets that gained members take the recomputed verdict).
"""
from collections import Counter, defaultdict
from board import B, NIGHTS, STORED, ordered_board, g3, g3_inputs, mac
from agents.market_intelligence.theme_engine import (parent_word_similarity, parent_industry_overlap,
                                                     ASSIGN_COMOVE_BAR, PARENT_PASS_MIN_INDUSTRY_OVERLAP)
import sys as _sys0
MIN505 = "--min505" in _sys0.argv   # added after the advisor review: apply #505's minimum too

eco = B["eco"]
ind = {t: (v.get("industry") or None) for t, v in B["industry"].items()}

def comove(member, target_tickers, excess):
    if member in target_tickers:
        return True, None
    vec = excess.get(member)
    if vec is None:
        return None, None
    bs = mac.build_baskets([{"name": "_t", "stage": "_t", "tickers": target_tickers}], excess, stages=("_t",))
    if not bs:
        return None, None
    c, _, _ = mac.correlate(vec, bs[0])
    if c is None:
        return None, None
    return c >= ASSIGN_COMOVE_BAR, round(c, 3)

def run(scope, mode, log):
    res = []
    for d in NIGHTS:
        board, _, _ = ordered_board(d)
        excess, usable, *_ = g3_inputs(d)
        st = {t["name"]: t for t in STORED[d]["g3"]["themes"]}
        names = {t["name"]: t for t in board}
        small = [t for t in board if 2 <= len(t["tickers"]) <= 3]
        folds = {}
        stats = Counter()
        for s in small:
            if scope == "fail" and (st[s["name"]]["pass_g3"] is not False):
                continue
            if scope == "fail2":
                pv = [x for x in NIGHTS if x < d]
                if st[s["name"]]["pass_g3"] is not False or not pv or STORED[pv[-1]] is None or \
                        {t["name"]: t for t in STORED[pv[-1]]["g3"]["themes"]}.get(s["name"], {}).get("pass_g3") is not False:
                    continue
            stats["population"] += 1
            e = eco.get(s["name"])
            if not e or e == "E-UNASSIGNED":
                stats["no_ecosystem"] += 1
                continue
            cands = [t for t in board if t["name"] != s["name"] and eco.get(t["name"]) == e
                     and len(t["tickers"]) >= 4 and sum(1 for m in t["tickers"] if m in usable) >= 3]
            if not cands:
                stats["no_candidate"] += 1
                continue
            q = []
            for c in cands:
                v = [comove(m, c["tickers"], excess) for m in s["tickers"]]
                passed = [m for m, (ok, _) in zip(s["tickers"], v) if ok]
                need = len(s["tickers"]) if mode == "strict" else (len(s["tickers"]) + 1) // 2
                if len(passed) >= need:
                    shared = len(set(s["tickers"]) & set(c["tickers"]))
                    if MIN505 and shared == 0 and parent_industry_overlap(s, c, ind) < PARENT_PASS_MIN_INDUSTRY_OVERLAP:
                        continue  # the #505 minimum (his 10-09 yes): nothing shared, industries do not line up
                    key = (-shared, -parent_industry_overlap(s, c, ind), -parent_word_similarity(
                        {"name": s["name"], "description": s.get("desc")}, {"name": c["name"], "description": c.get("desc")}),
                        -len(c["tickers"]), c["name"])
                    q.append((key, c, passed))
            if not q:
                stats["members_fail_test"] += 1
                continue
            q.sort(key=lambda x: x[0])
            _, c, passed = q[0]
            folds[s["name"]] = (c["name"], passed)
            stats["folded"] += 1
        # modified board
        new = []
        gained = defaultdict(list)
        for s, (cn, passed) in folds.items():
            gained[cn] += [m for m in passed]
        for t in board:
            if t["name"] in folds:
                continue
            tk = list(t["tickers"]) + [m for m in gained.get(t["name"], []) if m not in t["tickers"]]
            new.append({**t, "tickers": tk})
        r = g3(new, d)
        rv = {x["name"]: x for x in r["themes"]}
        # drift-free
        j = p = 0
        for t in new:
            v = rv[t["name"]] if t["name"] in gained else st[t["name"]]
            if v["cohesion"] is None:
                continue
            j += 1; p += bool(v["pass_g3"])
        small_n = sum(1 for t in new if len(t["tickers"]) < 3)
        target_flips = [cn for cn in gained if st[cn]["pass_g3"] and not rv[cn]["pass_g3"]]
        res.append((d, stats, r["pass"], r["n_judgeable"], p, j, small_n, len(new), folds, target_flips))
        if log is not None:
            for s, (cn, passed) in sorted(folds.items()):
                log.append(f"{d} | {s} ({len(names[s]['tickers'])}, {st[s]['stage']}, G3 {'pass' if st[s]['pass_g3'] else 'FAIL'}) -> {cn} | moved {passed}")
    return res

import sys as _s
_scopes = [("fail2", "majority")] if "--fail2" in _s.argv else [("fail", "majority")] if "--min505" in _s.argv else [(a, m) for a in ("all", "fail") for m in ("strict", "majority")]
for scope, mode in _scopes:
    if True:
        log = []
        res = run(scope, mode, log)
        print(f"\n=== (iii-{scope}) {mode} fold")
        print("night | small population | no ecosystem | no candidate | members fail test | folded | G3 recomputed | G3 drift-free | G4 | target flipped to fail")
        tot = Counter(); folded_names = set()
        for d, s, rp, rj, p, j, sm, nb, folds, tf in res:
            print(f"{d} | {s['population']} | {s['no_ecosystem']} | {s['no_candidate']} | {s['members_fail_test']} | {s['folded']} | "
                  f"{rp}/{rj} {100*rp/rj:.1f}% | {p}/{j} {100*p/j:.1f}% | {sm}/{nb} {100*sm/nb:.1f}% | {len(tf)} {tf[:2]}")
            tot.update(s); folded_names |= set(folds)
        print("totals", dict(tot), "| distinct themes folded", len(folded_names))
        with open(f"a4_fold_{scope}_{mode}{'_min505' if MIN505 else ''}.log", "w") as f:
            f.write("\n".join(log) + "\n")
