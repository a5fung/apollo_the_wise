#!/usr/bin/env python3
"""#717: run the rating on the 757 buys -> ratings.tsv + counts + the declared checks 1, 2 and 4.

    python3 scripts/probes/_717_qm_confidence_1111/01_rate.py > scripts/probes/_717_qm_confidence_1111/01_rate.out"""
import sys
from collections import Counter

sys.path.insert(0, "scripts/probes/_717_qm_confidence_1111")
import rating as R  # noqa: E402

B = R.load()
res = [(b, R.rate(b)) for b in B]
with open("scripts/probes/_717_qm_confidence_1111/ratings.tsv", "w") as f:
    f.write("set\teid\tsym\tticker\tlo\thi\ttier\treason\tbuy_point\tday_cleared\trange_len\tpath\tclosed_above\tvol_up\t"
            "tier_before_override\this_label\tbig_winner\n")
    for b, r in res:
        lv = "" if r["level"] is None else f"{r['level']:.4g}"
        day = "" if r["level"] is None else b["dates"][r["t"]].isoformat()
        f.write("\t".join(str(x) for x in (b["set"], b["eid"], b["sym"], b["ticker"], b["lo"], b["hi"], r["tier"], r["reason"], lv, day,
                                           "" if r["len"] is None else r["len"], r["path"], "" if r["closed"] is None else int(r["closed"]),
                                           int(r["vol"]), r["base_tier"], b["row"].get("his_label", ""), b["row"].get("big_winner", ""))) + "\n")

print("=== TIER COUNTS ===")
for s in ("dated", "widened"):
    n = sum(b["set"] == s for b, _ in res)
    c = Counter(r["tier"] for b, r in res if b["set"] == s)
    print(f"{s:8s} n = {n}: " + ", ".join(f"{t} {c[t]} ({c[t] / n:.0%})" for t in R.TIERS))
print("\n=== REASON by tier and set ===")
for s in ("dated", "widened"):
    for t in R.TIERS:
        c = Counter(r["reason"] for b, r in res if b["set"] == s and r["tier"] == t)
        print(f"{s:8s} {t:7s} " + ", ".join(f"{k} {v}" for k, v in c.most_common()))
print("\n=== what the trend overrides demoted (tier before the override -> Low) ===")
for cat in ("downtrend", "bounce"):
    for s in ("dated", "widened"):
        c = Counter(r["base_tier"] for b, r in res if b["set"] == s and r["reason"] == cat)
        print(f"{cat:10s} {s:8s} " + ", ".join(f"was {k} {v}" for k, v in sorted(c.items())))
nh = [(b, R.rate(b, use_holds=False)) for b in B]
for s in ("dated", "widened"):
    was = Counter((r0["tier"], r1["tier"]) for (b, r0), (_, r1) in zip(res, nh) if b["set"] == s and r0["tier"] != r1["tier"])
    print(f"holds-its-gains OFF, {s}: tier moves (with -> without) " + ", ".join(f"{a}->{c} {v}" for (a, c), v in sorted(was.items())))

print("\n=== CHECK 1: the named examples ===")
want_up = [("BILI", "2021-01-20"), ("ALB", "2021-05-27"), ("AXSM", "2019-12-27"), ("AAPL", "2020-07-23")]
for tk, d in want_up:
    hit = [(b, r) for b, r in res if b["ticker"] == tk and b["lo"] <= d <= b["hi"]] or [(b, r) for b, r in res if b["ticker"] == tk and abs((R.date.fromisoformat(b["hi"]) - R.date.fromisoformat(d)).days) <= 7]
    for b, r in hit:
        print(f"  must not be Low/Not: {tk} {b['set']} {b['lo']}..{b['hi']} -> {r['tier']} ({r['reason']}) level {r['level']} len {r['len']}  {'OK' if r['tier'] in ('High', 'Medium') else 'FAIL'}")
    if not hit:
        print(f"  {tk} {d}: NOT FOUND")
key = [x.strip().split("|") for x in open("scripts/probes/_717_shape_gates_1111/qm_widened_missed_sheet.png.key_do_not_show.txt") if x.count("|") >= 5][1:]
for L, sym, tk, lo, hi, *_ in key:
    b, r = next((b, r) for b, r in res if b["set"] == "widened" and b["ticker"] == tk and b["lo"] == lo)
    flag = "FAIL" if (tk in ("GAN", "ABNB", "AGQ", "BA", "GPOR", "VSTM", "FCEL") and r["tier"] == "High") else ""
    print(f"  sheet {L} {tk:6s} {lo}..{hi} -> {r['tier']:6s} ({r['reason']}) {flag}")

print("\n=== CHECK 2: his labels on the dated buys (cross-check only) ===")
def grp(lab):
    lab = lab.lower()
    if not lab:
        return None
    if lab.startswith("no") or "likely no" in lab:
        return "no"
    if "ep" in lab.split() or lab.startswith("ep") or "ep look" in lab or "like ep" in lab:
        return "EP-like"
    if "earlier" in lab or "ealier" in lab or "late" in lab:
        return "ok but earlier"
    return "good/ok"
tab = Counter((grp(b["row"]["his_label"]), r["tier"]) for b, r in res if b["set"] == "dated" and grp(b["row"]["his_label"]))
for g in ("good/ok", "ok but earlier", "EP-like", "no"):
    print(f"  {g:15s} n = {sum(tab[(g, t)] for t in R.TIERS):3d}: " + ", ".join(f"{t} {tab[(g, t)]}" for t in R.TIERS))
bw = Counter(r["tier"] for b, r in res if b["set"] == "dated" and b["row"]["big_winner"] == "1")
print(f"  big winners n = {sum(bw.values())}: " + ", ".join(f"{t} {bw[t]}" for t in R.TIERS))

print("\n=== CHECK 4: sensitivity (reported, not picked from) — High count dated / widened ===")
for ml in (8, 10, 15):
    for ra in (1 / 3, 0.5, 2 / 3):
        c = Counter((b["set"], R.rate(b, min_len=ml, ratio=ra)["tier"]) for b in B)
        print(f"  range >= {ml:2d}, gives back <= {ra:.2f}: High {c[('dated', 'High')]:3d} / {c[('widened', 'High')]:3d}   Medium {c[('dated', 'Medium')]:3d} / {c[('widened', 'Medium')]:3d}")
