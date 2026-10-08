"""#655 rule A hold-out — step 3: the HOLD-OUT read ($0, local, read-only).

Verdict source = the LIVE `theme_correctness_check` rows (per-theme G3 verdicts survived the detail
budget intact — checked), so no recompute: the hold-out nights are exactly what the nightly check said.
Board = the row's own g3.themes list (the board `get_active_themes` returned at 17:31 ET).

Framings (pre-stated in docs/analysis/655_rule_a_holdout_2026-10-07.md):
  (a) switched on Mon 10-05 — streaks start at zero on 10-05;
  (b) running since 09-08 — streaks + retired set carried from the discovery anchor (a_discovery_anchor.pkl).
Later-real = retired in the window AND on the final night's board AND passing G3 that night (verify_c).
G3 after rule = drift-free: passing survivors / judgeable survivors.
"""
import collections
import json
import pickle
from datetime import date

S = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/"
HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_655/rule_a_holdout/"
pull = pickle.load(open(S + "655_holdout_pull.pkl", "rb"))
anc = pickle.load(open(HERE + "a_discovery_anchor.pkl", "rb"))
lines = []


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    lines.append(s)


# ── live nightly verdicts ─────────────────────────────────────────────────────────────────────────
live = {}
for a in pull["audit"]:
    ts = a["created_at"]
    if ts.hour < 12:          # the 09-28 04:12 UTC row is the manual first run on Sunday night, not a scheduled night
        continue
    D = ts.date()
    j = json.loads(a["detail"])
    rows = j["g3"]["themes"]
    live[D] = {"verdict": {r["name"]: r["pass_g3"] for r in rows},
               "size": {r["name"]: r["size"] for r in rows},
               "stage": {r["name"]: r["stage"] for r in rows},
               "fails": set(j["g3"]["fail_list"]),
               "headline": (j["g3"]["pass"], j["g3"]["n_judgeable"], j["g3"]["rate_pct"])}
HO = [date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)]
for D in HO:
    assert D in live, D
P("HOLD-OUT live rows:", ", ".join(f"{D.isoformat()[5:]} G3 {live[D]['headline'][0]}/{live[D]['headline'][1]}={live[D]['headline'][2]}%" for D in HO))

# rs_avg per (name, date) from mi_themes for the profile of anything retired
rs = {(r["name"], r["theme_date"]): r["rs_avg"] for r in pull["hist"]}
hist_by = collections.defaultdict(dict)
for r in pull["hist"]:
    hist_by[r["name"]][r["theme_date"]] = r


def latest_rs(n, D):
    ds = [d for d in hist_by.get(n, {}) if d <= D]
    return hist_by[n][max(ds)]["rs_avg"] if ds else None


# ── verdict-source check on the overlap nights the study rebuilt (09-28..10-02) ──────────────────
P("\nSOURCE CHECK — study's rebuilt verdicts vs live rows on the 5 overlap nights:")
for D in anc["nights"]:
    if D not in live:
        continue
    rb, lv = anc["verdict"][D], live[D]["verdict"]
    both = [n for n in rb if n in lv and rb[n] is not None and lv[n] is not None]
    agree = sum(1 for n in both if rb[n] == lv[n])
    P(f"  {D}: themes in both {len(both)}, same verdict {agree} ({100*agree/len(both):.1f}%) | fails rebuilt {len(anc['fails'][D])} live {len(live[D]['fails'])}")


def g3_after(D, retired):
    v = live[D]["verdict"]
    surv = [n for n in v if n not in retired and v[n] is not None]
    p = sum(1 for n in surv if v[n])
    return 100 * p / len(surv), p, len(surv)


out = {}
for K in (3, 5):
    for framing in ("a", "b"):
        if framing == "a":
            streak, retired = collections.defaultdict(int), {}
        else:
            streak = collections.defaultdict(int, anc["res"][K]["streak_end"])
            retired = dict(anc["res"][K]["retired"])
        new = {}
        per = []
        for D in HO:
            names = set(live[D]["verdict"])
            for n in names:
                streak[n] = streak[n] + 1 if n in live[D]["fails"] else 0
            for n in names:
                if streak[n] >= K and n not in retired:
                    retired[n] = D
                    new[n] = D
            per.append((D, *g3_after(D, retired)))
        last = HO[-1]
        real = [n for n in new if n in live[last]["verdict"] and live[last]["verdict"][n]]
        key = f"A{K}{framing}"
        out[key] = {"new": new, "real": real, "per": per}
        lab = {"a": "switched on Mon 10-05", "b": "running since 09-08"}[framing]
        P(f"\n{key} ({lab}): retires {len(new)} in the hold-out | later-real at 10-07 {len(real)} {real}")
        P("   G3 after rule by night:", " | ".join(f"{D.isoformat()[5:]} {r:.1f}% ({p}/{n}) {'PASS' if r >= 90 else 'FAIL'}" for D, r, p, n in per))
        if framing == "b":
            removed_from_board = {D: sorted(n for n in live[D]["verdict"] if n in anc["res"][K]["retired"]) for D in HO}
            P("   of which already retired in discovery and still on the live board:",
              {D.isoformat()[5:]: len(v) for D, v in removed_from_board.items()})
        for n, D in sorted(new.items(), key=lambda x: (x[1], x[0])):
            P(f"   {D} retire {n[:62]:62s} size {live[D]['size'][n]:2d} {live[D]['stage'][n] or '':12s} rs_avg {latest_rs(n, D)}"
              f" | 10-07: {'on board, ' + ('PASS' if live[last]['verdict'].get(n) else 'fail') if n in live[last]['verdict'] else 'off board'}")

# ── the forward check on the study's cost claim ──────────────────────────────────────────────────
P("\nFORWARD CHECK — discovery-window retirements re-judged on the hold-out nights (on board? passing G3?)")
for K in (3, 5):
    ret = anc["res"][K]["retired"]
    real02 = set(anc["res"][K]["real_1002"])
    real07 = [n for n in ret if n in live[HO[-1]]["verdict"] and live[HO[-1]]["verdict"][n]]
    P(f"  A{K}: {len(ret)} discovery retirements | later-real at 10-02 (study) {len(real02)} | later-real at 10-07 {len(real07)}")
    for n in sorted(ret, key=lambda x: (x not in real02, x)):
        cells = []
        for D in HO:
            v = live[D]["verdict"]
            cells.append(("PASS" if v[n] else "fail") + f"/{live[D]['size'][n]}" if n in v else "--")
        tag = ("REAL@10-02" if n in real02 else "          ") + (" REAL@10-07" if n in real07 else "")
        P(f"    {n[:58]:58s} {tag:22s} 10-05 {cells[0]:8s} 10-06 {cells[1]:8s} 10-07 {cells[2]:8s}")
    out[f"A{K}_real07"] = real07

pickle.dump(out, open(HERE + "c_holdout.pkl", "wb"))
open(HERE + "c_holdout.out", "w").write("\n".join(lines) + "\n")
