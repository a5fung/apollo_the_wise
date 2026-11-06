#!/usr/bin/env python3
"""Compare the blind recount (recount.json, PRIMARY reading) with read_482.out, field by field.
Tolerance: read_482 prints 2 decimals (engine 4) -> |diff| <= 0.006 is a match."""
from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
txt = (HERE.parent / "read_482.out").read_text().splitlines()
mine = json.loads((HERE / "recount.json").read_text())
P = mine["PRIMARY"]

num = r"([+-]?\d+\.\d+|n/a)"
theirs: dict = {}
arm = era = None
for ln in txt:
    m = re.match(r"^ARM (\S+)", ln)
    if m:
        arm, era = m.group(1), None
        continue
    m = re.match(r"^  era ([CDE]): paired n \(R_cap set\) = (\d+)\s+\| R_own set n = (\d+)\s+\| no-entry \(0 in R_cap\) = (\d+)\s+\| rcap_uncomputable = (\d+)\s+\| excluded: (\{.*\})\s+-> (.*)$", ln)
    if m and arm:
        era = m.group(1)
        theirs.setdefault(arm, {})[era] = d = {}
        d.update(n_cap=int(m.group(2)), n_own=int(m.group(3)), readable=m.group(7).strip() == "READABLE")
        continue
    if arm is None or era is None:
        continue
    d = theirs[arm][era]
    m = re.match(r"^    TAIL  arm >=\+2R (\d+)  >=\+4R (\d+)  \| live >=\+2R (\d+)  >=\+4R (\d+)\s+\(entered-only: arm (\d+)/(\d+), live (\d+)/(\d+)\)", ln)
    if m:
        g = list(map(int, m.groups()))
        d.update(a2=g[0], a4=g[1], l2=g[2], l4=g[3], eo_a2=g[4], eo_a4=g[5], eo_l2=g[6], eo_l4=g[7])
        continue
    m = re.match(rf"^\s+max R_own: arm\s+{num}\s+live\s+{num}\s+\| <= -1\.5R: arm (\d+)\s+live (\d+)", ln)
    if m:
        d.update(amax=m.group(1), lmax=m.group(2), a15=int(m.group(3)), l15=int(m.group(4)))
        continue
    for unit in ("cap", "own"):
        m = re.match(rf"^    R_{unit} delta: sum\s+{num}\s+median\s+{num}\s+better/worse/tie (\d+)/(\d+)/(\d+)\s+drop-best\s+{num}", ln)
        if m:
            d.update({f"{unit}_sum": m.group(1), f"{unit}_med": m.group(2),
                      f"{unit}_bwt": [int(m.group(3)), int(m.group(4)), int(m.group(5))], f"{unit}_db": m.group(6)})
    m = re.match(r"^    tail-clip (\d+) \(of (\d+) .*rescues (\d+) \(of (\d+)", ln)
    if m:
        d.update(tailclip=int(m.group(1)), tailclip_base=int(m.group(2)), rescue=int(m.group(3)), rescue_base=int(m.group(4)))
    m = re.match(rf"^    engine check: sum\(arm - live_replay\) R_cap\s+{num} on (\d+) both-settled fills -> sign (\w+)", ln)
    if m:
        d.update(eng_sum=m.group(1), eng_n=int(m.group(2)), eng_agree=m.group(3) == "AGREES")
    m = re.match(rf"^    context: pct delta sum\s+{num} median\s+{num} \(n (\d+)\)\s+\| adr delta sum\s+{num} median\s+{num} \(n (\d+)\)", ln)
    if m:
        d.update(pct_sum=m.group(1), pct_med=m.group(2), adr_sum=m.group(4), adr_med=m.group(5), adr_n=int(m.group(6)))
    m = re.match(r"^    WON test: .* -> (WON|LOST|n/a.*)$", ln)
    if m:
        d.update(won=m.group(1) == "WON")

labels = {}
in5 = False
for ln in txt:
    if "FINAL LABEL per arm" in ln:
        in5 = True
        continue
    if in5:
        m = re.match(r"^    (\S+)\s+(.+?)\s*$", ln)
        if m and not ln.strip().startswith("I"):
            labels[m.group(1)] = m.group(2)
        if not ln.strip():
            in5 = False


def close(a, b, tol=0.006):
    if a is None or b in (None, "n/a"):
        return (a is None) == (b in (None, "n/a"))
    return abs(float(a) - float(b)) <= tol


FIELDS = ["n_cap", "n_own", "readable", "a2", "a4", "l2", "l4", "amax", "lmax", "a15", "l15",
          "cap_sum", "cap_med", "cap_bwt", "cap_db", "own_sum", "own_med", "own_bwt", "own_db",
          "tailclip", "tailclip_base", "rescue", "rescue_base", "eng_sum", "eng_n", "eng_agree",
          "pct_sum", "pct_med", "adr_sum", "adr_med", "won"]
mism = []
nchk = 0
for a, per in theirs.items():
    for e, d in per.items():
        mm = P[a][e]
        for k in FIELDS:
            if k not in d:
                continue
            nchk += 1
            tv, mv = d[k], mm.get(k)
            if k == "won" and not mm["readable"]:
                mv = False  # read_482 prints n/a for an unreadable era
            ok = close(mv, tv) if isinstance(tv, str) else (list(mv) == tv if isinstance(tv, list) else mv == tv)
            if not ok:
                mism.append((a, e, k, tv, mv))
print(f"fields compared: {nchk}; arms {len(theirs)}; mismatches: {len(mism)}")
for a, e, k, tv, mv in mism:
    print(f"  MISMATCH {a:28} {e} {k:12} read_482={tv}  recount={mv if not isinstance(mv, float) else round(mv, 4)}")
print()
print("labels: read_482 FINAL vs recount PRIMARY (unreadable-first) / recount precedence=not_won_first")
for a, lab in labels.items():
    p = mine["_labels"]["PRIMARY"][a]
    g = mine["_labels"]["g:precedence=not_won_first"][a]
    flag = "" if lab == p else ("  (= recount under not_won_first precedence)" if lab == g else "  MISMATCH")
    print(f"  {a:28} {lab:18} | {p:18} | {g}{flag}")

# ── PART 2: the RESULT section of PREREG.md (a hand transcription of read_482.out) vs the recount ──
print()
print("PART 2 — PREREG.md '## RESULT' tables vs recount PRIMARY (tolerance 0.006 on 2-dp cells, 0.00006 on engine)")
res = (HERE.parent / "PREREG.md").read_text().split("## RESULT", 1)[1].splitlines()
rows = [ln for ln in res if re.match(r"^\| `\w+` \| [CDE] \|", ln)]
cells_chk, bad = 0, []
for ln in rows:
    c = [x.strip() for x in ln.strip().strip("|").split("|")]
    a, e = c[0].strip("`"), c[1]
    m = P[a][e]
    n = int(re.match(r"(\d+)", c[2]).group(1))
    ne = re.search(r"\((\d+) no-entry\)", c[2])
    a2, a4 = map(int, c[3].split("/"))
    l2, l4 = map(int, c[4].split("/"))
    sg = re.match(r"(agrees|disagrees) \(([+-]?\d+\.\d+)\)", c[9])
    checks = {
        "n": (n, m["n_cap"]), "no_entry": (int(ne.group(1)) if ne else 0, m["ex"].get("no_entry_scored_0", 0)),
        "a2": (a2, m["a2"]), "a4": (a4, m["a4"]), "l2": (l2, m["l2"]), "l4": (l4, m["l4"]),
        "cap_sum": (float(c[5]), m["cap_sum"]), "cap_db": (float(c[6]), m["cap_db"]),
        "own_sum": (float(c[7]), m["own_sum"]), "tailclip": (int(c[8]), m["tailclip"]),
        "eng_agree": (sg.group(1) == "agrees", m["eng_agree"]), "eng_sum": (float(sg.group(2)), m["eng_sum"]),
        "result": (c[10], "not readable" if not m["readable"] else ("WON" if m["won"] else "LOST")),
    }
    for k, (tv, mv) in checks.items():
        cells_chk += 1
        if isinstance(tv, float):
            ok = abs(tv - mv) <= (0.00006 if k == "eng_sum" else 0.006)
        else:
            ok = tv == mv
        if not ok:
            bad.append((a, e, k, tv, mv))
print(f"  per-arm-per-era table: {len(rows)} rows, {cells_chk} cells; mismatches {len(bad)}")
for b in bad:
    print("   MISMATCH", b)
lab_rows = [ln for ln in res if re.match(r"^\| `\w+` \| (NOT A CANDIDATE|WATCH|UNREADABLE)", ln)]
lbad = []
for ln in lab_rows:
    c = [x.strip() for x in ln.strip().strip("|").split("|")]
    a, lab, nread = c[0].strip("`"), c[1], int(c[2])
    m = P[a]
    mine_n = sum(1 for e in "CDE" if m[e]["readable"])
    per = dict(re.findall(r"([CDE]) (LOST|WON|unreadable) \(n(\d+)\)", c[3]) and
               [(x[0], (x[1], int(x[2]))) for x in re.findall(r"([CDE]) (LOST|WON|unreadable) \(n(\d+)\)", c[3])])
    for e in "CDE":
        want = ("unreadable" if not m[e]["readable"] else ("WON" if m[e]["won"] else "LOST"), m[e]["n_cap"])
        if per.get(e) != want:
            lbad.append((a, e, per.get(e), want))
    if nread != mine_n:
        lbad.append((a, "readable_eras", nread, mine_n))
    if lab != mine["_labels"]["g:precedence=not_won_first"][a]:
        lbad.append((a, "label(I1)", lab, mine["_labels"]["g:precedence=not_won_first"][a]))
    if lab != mine["_labels"]["PRIMARY"][a]:
        print(f"   label differs from recount's unreadable-first precedence only: {a} RESULT={lab} recount={mine['_labels']['PRIMARY'][a]} (I1, disclosed)")
print(f"  labels table: {len(lab_rows)} arms; mismatches vs recount under I1 precedence: {len(lbad)}")
for b in lbad:
    print("   MISMATCH", b)
# population / disappoints numbers quoted in RESULT bullets
txtres = "\n".join(res)
quoted = {"OKTA": "-1.4402", "VICR": "-1.1119", "KOD": "-0.2902", "CLS": "+1.1504"}
print("  population bullets: paired C6/D6/E4 =", all(f"C 6 / D 6 / E 4" in txtres for _ in [0]),
      "| pending 6 =", "Pending rows: 6" in txtres, "| abstain 4 =", "Abstain rows: 4" in txtres,
      "| fidelity diffs quoted:", {k: (v.replace('-', '−') in txtres or v in txtres) for k, v in quoted.items()})
