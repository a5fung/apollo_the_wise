#!/usr/bin/env python3
"""EP RANKING v2 — feature 3 RE-DEFINED (F3_DEFINITION.md, pre-registered before this ran), scored exactly as
docs/analysis/ep_rank_v2_prereg_2026-11-03.md scores features.

Research only: $0, local files only, no network / server / prod. Reuses ../build/rank_v2.py's loaders,
populations A/B/C, day pools, composite and bars VERBATIM (rv2.load()); the only swap is the 'held' feature,
replaced by f3_def.f3_new. The 11-03 'held' is kept as the sub-read 'held_old'. Output: rank_v2_f3.txt,
f3_features.tsv (this folder only).
"""
from __future__ import annotations

import csv
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rv2  # noqa: E402
from f3_def import STATED as F3_STATED, f3_new  # noqa: E402

ns = rv2.load()
P = ns["P"]
ns["OUT"].clear()
fmt, auc, boot_ci = ns["fmt"], ns["auc"], ns["boot_ci"]
CohortRead, score_both_directions = ns["CohortRead"], ns["score_both_directions"]
A_yes, A_no, B_his, C, pairs, rows_c = ns["A_yes"], ns["A_no"], ns["B_his"], ns["C"], ns["pairs"], ns["rows_c"]
TAIL, TOL, QUAL = ns["TAIL"], ns["TOL"], ns["QUAL"]
orig_features = ns["features"]

# the 11-03 run's stated values (one-at-a-time ± variants of vol_win are not part of this study)
STATED = dict(ns["STATED"], **F3_STATED)          # adr_mult 1.0, vol_win 252, pb_win 40, base_end 250 + new
assert ns["STATED"]["adr_mult"] == F3_STATED["adr_mult"] and ns["STATED"]["pb_win"] == F3_STATED["pb_win"] \
    and ns["STATED"]["base_end"] == F3_STATED["base_end"]
ORIG_KEYS = tuple(ns["STATED"])
ns["SUBREADS"][:] = list(ns["SUBREADS"]) + ["held_old", "into"]

_cache: dict = {}
DETAIL: dict = {}


def features_f3(t, d, prm=STATED):
    key = (t, d, tuple(sorted(prm.items())))
    if key in _cache:
        return _cache[key]
    f = dict(orig_features(t, d, {k: prm[k] for k in ORIG_KEYS}))
    f["null"] = [x for x in f["null"] if not x.startswith("F3:")]
    f["held_old"] = f["held"]
    f["held"] = f["into"] = f["dmin"] = None
    enc, days, ia = ns["encode1"](t, d)
    if enc.get("error"):
        r = dict(null="F1-3:" + enc["error"])
    else:
        r = f3_new(days, ia, ns["nbis"].adr20_pct(days, ia), prm)
        f["held"], f["into"], f["dmin"] = r["held"], r["into"], r["dmin"]
    if r.get("null"):
        f["null"].append("F3new:" + r["null"])
    DETAIL[key] = r
    _cache[key] = f
    return f


ns["features"] = features_f3
feat = lambda p, prm=STATED: features_f3(p["ticker"], p["date"], prm)  # noqa: E731


def det(p, prm=STATED):
    features_f3(p["ticker"], p["date"], prm)
    return DETAIL[(p["ticker"], p["date"], tuple(sorted(prm.items())))]


def c_split(prm, key="held"):
    """Feature alone on C: held=1 vs held=0 on the matured rows, the running read's tail test."""
    out = {}
    for tag, mat, xk in (("5d", 6, "x5"), ("20d", 21, "x20")):
        pop = [r for r in rows_c if r["sess"] >= mat and r[xk] is not None]
        v = {(r["tk"], r["date"]): features_f3(r["tk"], r["date"], prm)[key] for r in pop}
        g1 = [r for r in pop if v[(r["tk"], r["date"])] == 1]
        g0 = [r for r in pop if v[(r["tk"], r["date"])] == 0]
        gn = [r for r in pop if v[(r["tk"], r["date"])] is None]
        mk = lambda g: CohortRead(len(g), sum(1 for r in g if r[xk] >= TAIL), sum(1 for r in g if r["loser"]))  # noqa: E731
        out[tag] = dict(pop=len(pop), c1=mk(g1), c0=mk(g0), nnull=len(gn),
                        verdict=score_both_directions(mk(g1), mk(g0)),
                        tails=[(r["tk"], r["date"], r[xk], v[(r["tk"], r["date"])]) for r in pop if r[xk] >= TAIL])
    return out


def runs(r):
    return "-" if r.get("run_pct") is None else f"{r['run_pct'] * 100:.0f}%"


def rate(a, b):
    return "-" if not b else f"{a}/{b} ({a / b:.0%})"


# ════════════════════════════════════════════════════════════════════════════════════════
P("=" * 100)
P("EP RANKING v2 — FEATURE 3 RE-DEFINED (build_f3/F3_DEFINITION.md), scored as the 11-03 pre-registration")
P("=" * 100)
P("  P = highest high of sessions 41-250 before D · S = lowest low of the 60 sessions before P · shelf = highest")
P("  high of the 45 sessions ending at S · run >= 30% and P > shelf, else held = 0 · the 2 lowest swing lows of")
P("  the last 40 sessions (R3) each >= shelf - 1 ADR20 -> held = 1. Sub-reads: into (|d| <= 1 ADR both),")
P("  held_old (the 11-03 feature). KOD 2026-09-28 is the only calibration (kod_check.txt: shelf 2025-12-24 $31.18).")

S = ns["run"](STATED, "stated", True)
sa = S["sa"]

P("\n[0] REPRODUCTION — the untouched features must read exactly as the 11-03 run (rank_v2.txt [2])")
want = dict(zones_cleared=(0.672, 17, 37), vol_ratio=(0.619, 17, 29), tight_eod=(0.356, 17, 37),
            held_old=(0.512, 17, 28))
allok = True
for k, (a0, y0, n0) in want.items():
    ok = abs(sa[k]["auc"] - a0) < 0.0006 and sa[k]["ny"] == y0 and sa[k]["nn"] == n0
    allok &= ok
    P(f"  {k:<14} P(yes>no) {sa[k]['auc']:.3f} n {sa[k]['ny']}/{sa[k]['nn']}  (11-03: {a0:.3f} n {y0}/{n0})"
      f"  {'same' if ok else 'DIFFERENT'}")
P(f"  -> {'REPRODUCED' if allok else 'NOT REPRODUCED — stop'}")
assert allok

P("\n[1] COVERAGE of the new feature (stated thresholds) — every pair")
nul = defaultdict(list)
struct = defaultdict(lambda: defaultdict(int))
for p in pairs:
    g = p["source"] if p["source"] != "B" else ("B" if p["label"] == "operator" else "B2")
    r = det(p)
    if feat(p)["held"] is None:
        nul[g].append(f"{p['ticker']} {p['date']} ({r.get('null')})")
    else:
        struct[g][r["structure"].split("(")[0]] += 1
P(f"  held NULL {sum(len(v) for v in nul.values())}/{len(pairs)}: " +
  " | ".join(f"{g} {len(v)}" for g, v in sorted(nul.items())))
for g, v in sorted(nul.items()):
    P(f"      {g}: " + "; ".join(v))
P("  structure among non-NULL: " + " | ".join(
    f"{g}: " + ", ".join(f"{k}={n}" for k, n in sorted(d.items())) for g, d in sorted(struct.items())))

P("\n[2] POPULATION A — each feature's chance a yes (GOOD/OKISH) ranks above a no (BAD); 0.5 = nothing")
P(f"  {'feature':<17} {'role':<9} {'P(yes>no)':>9} {'score':>6} {'direction':<11} {'n yes/no':>9}  90% boot CI")
for k in ns["PRIMARY"] + ns["SUBREADS"]:
    r = sa[k]
    yv = [x for x in (feat(p)[k] for p in A_yes) if x is not None]
    nv = [x for x in (feat(p)[k] for p in A_no) if x is not None]
    ci = boot_ci(yv, nv)
    role = "PRIMARY" if k in ns["PRIMARY"] else "sub-read"
    flag = ("  QUALIFIES" if role == "PRIMARY" else "  (>=0.65, sub-read: not eligible)") \
        if (r["score"] is not None and r["score"] >= QUAL - TOL) else ""
    name = "held (NEW F3)" if k == "held" else k
    P(f"  {name:<17} {role:<9} {fmt(r['auc']):>9} {fmt(r['score']):>6} {(r['direction'] or ''):<11} "
      f"{r['ny']:>4}/{r['nn']:<4}  {'' if ci is None else f'[{ci[0]:.2f}, {ci[1]:.2f}]'}{flag}")
for k in ("held", "into"):
    y1 = sum(1 for p in A_yes if feat(p)[k] == 1)
    n1 = sum(1 for p in A_no if feat(p)[k] == 1)
    yn = sum(1 for p in A_yes if feat(p)[k] is not None)
    nn = sum(1 for p in A_no if feat(p)[k] is not None)
    P(f"  {k} = 1 on: yes {rate(y1, yn)} · no {rate(n1, nn)}")
yv = [feat(p)["dmin"] for p in A_yes if feat(p)["dmin"] is not None]
nv = [feat(p)["dmin"] for p in A_no if feat(p)["dmin"] is not None]
P(f"  descriptive (not eligible): lower pullback low vs the NEW shelf, in ADR — yes median "
  f"{st.median(yv):+.2f} (n={len(yv)}) · no median {st.median(nv):+.2f} (n={len(nv)}) · P(yes>no) {auc(yv, nv):.3f}")
P("\n  per-pair (A):")
P(f"    {'ticker':<6} {'date':<10} {'label':<12} {'old':>3} {'NEW':>3} {'into':>4} {'d1':>6} {'d2':>6}  "
  f"{'shelf':<20} {'S (run start)':<20} {'P (peak)':<20} {'run':>5}  structure / null")
for p in sorted(A_yes + A_no, key=lambda p: (p["label"] not in ns["YES"], p["label"], p["date"])):
    f, r = feat(p), det(p)
    sh = f"{r['shelf_date']} {r['shelf']:.2f}" if r.get("shelf") else "-"
    ss = f"{r['s_date']} {r['s_low']:.2f}" if r.get("s_low") else "-"
    pp = f"{r['p_date']} {r['p_high']:.2f}" if r.get("p_high") else "-"
    P(f"    {p['ticker']:<6} {p['date']:<10} {p['label']:<12} {fmt(f['held_old']):>3} {fmt(f['held']):>3} "
      f"{fmt(f['into']):>4} {fmt(r.get('d1'), 1):>6} {fmt(r.get('d2'), 1):>6}  {sh:<20} {ss:<20} {pp:<20} "
      f"{runs(r):>5}  "
      f"{r.get('structure') or ''}{(' NULL:' + r['null']) if r.get('null') else ''}")

P("\n[3] POPULATION B — his 8 labelled real EPs (all 8 read held = 0 under the 11-03 definition)")
for p in B_his:
    f, r = feat(p), det(p)
    sh = f"shelf {r['shelf_date']} ${r['shelf']:.2f}" if r.get("shelf") else "shelf -"
    P(f"    {p['ticker']:<5} {p['date']}  held_old {fmt(f['held_old'])} · NEW held {fmt(f['held'])} · into "
      f"{fmt(f['into'])} · d {fmt(r.get('d1'), 1)}/{fmt(r.get('d2'), 1)} ADR · {sh} · run "
      f"{runs(r)} · "
      f"{r.get('structure') or ''}{(' NULL:' + r['null']) if r.get('null') else ''}")
bh = [feat(p)["held"] for p in B_his]
P(f"  NEW held = 1 on {sum(1 for x in bh if x == 1)} of {sum(1 for x in bh if x is not None)} non-NULL "
  f"({sum(1 for x in bh if x is None)} NULL)")

P("\n[4] POPULATION C — the feature alone on the shadow tail: held = 1 vs held = 0 (matured rows, >= 8 x ADR)")
cs = c_split(STATED)
for tag, x in cs.items():
    c1, c0 = x["c1"], x["c0"]
    P(f"  [{tag}] matured n={x['pop']} (NULL {x['nnull']}) | held=1 n={c1.n} tail winners {rate(c1.winners_admitted, c1.n)}"
      f" losers {rate(c1.losers_admitted, c1.n)} | held=0 n={c0.n} winners {rate(c0.winners_admitted, c0.n)} "
      f"losers {rate(c0.losers_admitted, c0.n)}")
    P(f"        score_both_directions(held=1, held=0): {x['verdict']}")
    P("        tails: " + ", ".join(f"{t} {d} {v:.2f}x held={fmt(h)}" for t, d, v, h in x["tails"]))

P("\n[5] THE v2 COMPOSITE (the 11-03 rule: features >= 0.65 on A enter)")
P("  included: " + ", ".join(f"{k} ({d})" for k, d in S["included"]))
if "held" not in [k for k, _ in S["included"]]:
    P(f"  the NEW feature 3 scores {sa['held']['score']:.3f} on A (< 0.65) -> it does NOT enter; the composite is"
      " the 11-03 one (zones cleared alone) and the bars below must equal rank_v2.txt [3].")
ns["report_bars"](S, False)
v, i_ok, ii_ok, iii_ok = ns["verdict_of"](S)
P(f"  -> (i) {'PASS' if i_ok else 'FAIL'} · (ii) {'PASS' if ii_ok else 'FAIL'} · (iii) {'PASS' if iii_ok else 'FAIL'}"
  f" -> {v}")

P("\n[6] PLATEAU — each F3 threshold at -50% / +50%, one at a time (others stated)")
VARS = [("adr_mult", 0.5), ("adr_mult", 1.5), ("pb_win", 20), ("pb_win", 60), ("base_end", 125),
        ("base_end", 375), ("run_win", 30), ("run_win", 90), ("shelf_win", 22), ("shelf_win", 68),
        ("run_min", 0.15), ("run_min", 0.45)]
kod = next(p for p in A_yes if p["ticker"] == "KOD")
P(f"  {'variant':<15} {'held A':>7} {'CI90':<13} {'n y/n':>7} {'=1 yes/no':>11} {'into A':>7} {'B=1':>5} {'KOD':>4} | "
  f"included | (i) lit/rank | (ii) | (iii) 5d/20d | C held=1 vs 0 (5d · 20d) | verdict")
plat = []
for name, over in [("stated", {})] + [(f"{k}={v_}", {k: v_}) for k, v_ in VARS]:
    prm = dict(STATED, **over)
    R = S if not over else ns["run"](prm, name, False)
    s2 = R["sa"]
    yv = [x for x in (feat(p, prm)["held"] for p in A_yes) if x is not None]
    nv = [x for x in (feat(p, prm)["held"] for p in A_no) if x is not None]
    ci = boot_ci(yv, nv)
    inc = "+".join(k for k, _ in R["included"])
    vv = ns["verdict_of"](R)[0]
    plat.append((name, s2["held"]["score"], vv))
    cc = c_split(prm)
    cstr = " · ".join(f"{cc[h]['c1'].winners_admitted}w{cc[h]['c1'].losers_admitted}L/{cc[h]['c1'].n} vs "
                      f"{cc[h]['c0'].winners_admitted}w{cc[h]['c0'].losers_admitted}L/{cc[h]['c0'].n}" for h in ("5d", "20d"))
    P(f"  {name:<15} {s2['held']['auc']:>7.3f} {('[%.2f, %.2f]' % ci) if ci else '-':<13} "
      f"{s2['held']['ny']:>3}/{s2['held']['nn']:<3} {sum(yv)}/{len(yv)}·{sum(nv)}/{len(nv):<3} "
      f"{s2['into']['auc']:>7.3f} {sum(1 for p in B_his if feat(p, prm)['held'] == 1):>3}/8 "
      f"{fmt(feat(kod, prm)['held']):>4} | {inc} | {fmt(R['i_all'][0], 2)}/{fmt(R['i_rank'][0], 2)} | "
      f"{R['ii']['top']}/{R['ii']['elig']} | "
      + "/".join("PASS" if R["iii"][(h, "c_eod")]["passed"] else "fail" for h in ("5d", "20d"))
      + f" | {cstr} | {vv}")
best = max(plat, key=lambda x: x[1])
P(f"  held's score on A ranges {min(x[1] for x in plat):.3f} - {max(x[1] for x in plat):.3f} across the 13 settings"
  f" (best {best[0]}); qualifies (>= 0.65) at: "
  + (", ".join(n for n, s_, _ in plat if s_ >= QUAL - TOL) or "none"))

P("\n[7] NOT THE PRE-REGISTERED BAR — the new feature FORCED into the composite beside zones cleared")
P("  (shown only to say what his chart read would do to the ranking if it were let in; changes nothing above)")
_prim, _qual = list(ns["PRIMARY"]), ns["QUAL"]
ns["PRIMARY"][:] = ["zones_cleared", "held"]
ns["QUAL"] = min(sa["zones_cleared"]["score"], sa["held"]["score"]) - 1e-6
RF = ns["run"](STATED, "forced", False)
ns["PRIMARY"][:], ns["QUAL"] = _prim, _qual
P("  included: " + ", ".join(f"{k} ({d})" for k, d in RF["included"]))
P(f"  (i) literal {fmt(RF['i_all'][0])} (n {RF['i_all'][1]}/{RF['i_all'][2]}) · rankable-only {fmt(RF['i_rank'][0])} "
  f"(n {RF['i_rank'][1]}/{RF['i_rank'][2]}) — needs 0.70")
P(f"  (ii) {RF['ii']['top']} of {RF['ii']['elig']} rankable labelled EPs in the top half (needs 80%)")
for h in ("5d", "20d"):
    x = RF["iii"][(h, "c_eod")]
    P(f"  (iii) {h}: forced top n={x['cand'].n} winners {x['cand'].winners_admitted} losers "
      f"{x['cand'].losers_admitted}/{x['cand'].n} vs old top n={x['base'].n} winners {x['base'].winners_admitted} "
      f"losers {x['base'].losers_admitted}/{x['base'].n} -> {x['verdict']}")
P(f"  forced verdict (not binding): {ns['verdict_of'](RF)[0]}")

P("\n[8] VERDICT (the pre-registration's own words)")
P(f"  NEW feature 3 on A: {sa['held']['auc']:.3f} (n {sa['held']['ny']} yes / {sa['held']['nn']} no) -> "
  f"{'qualifies' if sa['held']['score'] >= QUAL - TOL else 'does not reach 0.65 — does not enter'}")
P(f"  v2 composite: {', '.join(k for k, _ in S['included'])} · (i) {'PASS' if i_ok else 'FAIL'} · (ii) "
  f"{'PASS' if ii_ok else 'FAIL'} · (iii) {'PASS' if iii_ok else 'FAIL'} -> {v}")

# ── per-pair table ──
cols = ["ticker", "date", "source", "label", "held_new", "into", "held_old", "d1_adr", "d2_adr", "dmin_adr",
        "shelf", "shelf_date", "s_low", "s_date", "p_high", "p_date", "run_pct", "structure", "null",
        "low1_date", "low1", "low2_date", "low2", "adr20_pct"]
with open(HERE / "f3_features.tsv", "w", newline="") as fh:
    w = csv.writer(fh, delimiter="\t")
    w.writerow(cols)
    for p in pairs:
        f, r = feat(p), det(p)
        g = lambda x, n=4: "" if x is None else (f"{x:.{n}f}" if isinstance(x, float) else str(x))  # noqa: E731
        lows = (r.get("lows") or []) + [("", None), ("", None)]
        w.writerow([p["ticker"], p["date"], p["source"], p["label"], g(f["held"]), g(f["into"]), g(f["held_old"]),
                    g(r.get("d1")), g(r.get("d2")), g(r.get("dmin")), g(r.get("shelf")), r.get("shelf_date") or "",
                    g(r.get("s_low")), r.get("s_date") or "", g(r.get("p_high")), r.get("p_date") or "",
                    g(r.get("run_pct")), r.get("structure") or "", r.get("null") or "",
                    lows[0][0], g(lows[0][1]), lows[1][0], g(lows[1][1]), g(f["adr20"])])
(HERE / "rank_v2_f3.txt").write_text("\n".join(ns["OUT"]) + "\n", encoding="utf-8")
