#!/usr/bin/env python3
"""Independent recount of the #705 context-rules RUN (docs/analysis/cb_context_rules_prereg_2026-10-26.md).

Written from the doc's definitions only.  Does NOT import 01_ctx.py (or its frozen copy), reads no price bar,
opens no replay/ or his_exits/ folder, reads nothing dated after 2024-12-31.  Inputs: the run printout, the per-trade
files under out/, the rule-mix tag files (the +-0 reference), the doc's pins under the FREEZE marker.
Run from the repo root:  python3 scripts/probes/_705_context_1026/verify/recount_run.py
"""
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path.cwd()
D = ROOT / "scripts/probes/_705_context_1026"
OUT = D / "out"
VER = D / "verify"
DOC = ROOT / "docs/analysis/cb_context_rules_prereg_2026-10-26.md"
TAGS = Path("/Users/alvinfung/apollo_data/cb702/qm_streams/holdings_1024/rule_mix")
RUN = D / "01_ctx_run.txt"

LINES = []


def say(s=""):
    print(s)
    LINES.append(s)


RES = []          # (check id, ok)
ATOMS = [0]       # atomic comparisons made
NOTES = []


def rec(cid, ok, msg):
    RES.append((cid, ok))
    say(f"[{cid}] {'MATCH' if ok else 'MISMATCH'} - {msg}")


def atom(n=1):
    ATOMS[0] += n


def t10(x):
    """printed percent string / float -> integer tenths"""
    return int(round(float(str(x).rstrip("%")) * 10))


def pct1(frac):
    """fraction -> printed one-decimal percent as tenths, the way the run formats (f'{100*x:.1f}')"""
    return int(round(float(f"{100.0 * frac:.1f}") * 10))


def fl(x):
    return np.nan if x == "" else float(x)


TOLMAP = {"the bracket (primary)": "bracket", "B1 re-cross": "B1", "B2 hit-or-ballpark": "B2",
          "±1c (primary)": "pm1c", "±0": "pm0", "±1 symmetric": "pm1", "±2": "pm2"}
PRIMARY = {"ENTER": "bracket", "STOP": "pm1c", "EXIT": "pm1c"}
LIB = {
    "ENTER": ["L1", "L8", "L2", "L7", "L3", "L9", "L4"],
    "STOP": ["S1-T", "S10-T", "S10-H", "S10-C", "S9-T", "S9-H", "S9-C", "S1-H", "S1-C", "S3-T", "S3-H", "S3-C",
             "S4-T", "S4-H", "S4-C"],
    "EXIT": ["M-1", "M-2", "M-3", "M-4", "M-5", "M-9", "M-6", "M-2s", "M-11", "M-7", "M-8", "M-10"],
}
BLOCKS = ["2020", "2021-22", "untouched"]

# ------------------------------------------------------------------ loaders
TAG = {d: pd.read_csv(TAGS / f"tags_{d.lower()}.tsv", sep="\t", dtype=str, keep_default_na=False) for d in LIB}
for d in LIB:
    cols = [c[:-7] for c in TAG[d].columns if c.endswith("_bucket")]
    assert cols == LIB[d], (d, cols)          # library order (tie-break) = the tag files' column order = doc 5a
GR = pd.read_csv(OUT / "groups.tsv", sep="\t", dtype=str, keep_default_na=False)
CX = pd.read_csv(OUT / "contexts.tsv", sep="\t", dtype=str, keep_default_na=False)
MP = pd.read_csv(OUT / "maps.tsv", sep="\t", dtype=str, keep_default_na=False)
CT = pd.read_csv(OUT / "controls.tsv.gz", sep="\t", dtype=str, keep_default_na=False)
for df in (GR, CX):
    df["eid"] = df["eid"].astype(str)
for d in TAG:
    TAG[d]["eid"] = TAG[d]["eid"].astype(str)

# pins under the freeze marker
PINS = {}
_txt = DOC.read_text().split("<!-- FREEZE -->")[1]
for ln in _txt.splitlines():
    m = re.match(r"^- (ctx_const_\S+): (\S+)$", ln)
    if m:
        PINS[m.group(1)] = m.group(2)


def pin_f(k):
    return float(PINS[k])


def pin_b(k):
    return PINS[k] == "True"


# ------------------------------------------------------------------ populations (from the tag files alone)
def scorable(dec):
    t = TAG[dec]
    if dec == "ENTER":
        m = (t.tagged == "True") & ((t.dated == "True") | (t.flicker == "False"))
    elif dec == "STOP":
        m = (t.status == "scorable") & (t.room == "True") & (t.loser == "True")
    else:
        m = (t.status == "scorable") & (t.room == "True")
    return t[m].copy()


def beside_enter():
    t = TAG["ENTER"]
    return t[(t.dated == "False") & (t.flicker == "True")].copy()


POP = {d: scorable(d) for d in LIB}
BESIDE = beside_enter()


# ------------------------------------------------------------------ CLOSE matrices (from the tag buckets alone)
def close_matrices(dec, tol, rows):
    """(lower, upper) bool arrays (n x rules).  +-0 / bracket: bucket == EXPLAINS (exact; lower == upper).
    Widened STOP/EXIT tolerances derived from the doc's 4a: +-0 bucket, booked session (booked_j), event session
    (first_j), the window.  UNRESOLVED -> CLOSE upgrades (needs missing-session facts the tag files do not carry)
    are the only cells the derivation cannot decide: lower excludes them, upper includes every UNRESOLVED cell whose
    booked session lies in the widened window."""
    rules = LIB[dec]
    n = len(rows)
    lo_m = np.zeros((n, len(rules)), bool)
    up_m = np.zeros((n, len(rules)), bool)
    if dec == "ENTER" or tol == "pm0":
        for j, r in enumerate(rules):
            lo_m[:, j] = (rows[r + "_bucket"].to_numpy() == "EXPLAINS")
        return lo_m, lo_m.copy()
    lo_s = rows["exit_lo_j"].astype(float).to_numpy()
    hi_s = rows["exit_hi_j"].astype(float).to_numpy()
    for j, r in enumerate(rules):
        b0 = rows[r + "_bucket"].to_numpy()
        fj = rows[r + "_first_j"].map(fl).to_numpy(float)
        bj = rows[r + "_booked_j"].map(fl).to_numpy(float)
        lo_m[:, j] = (b0 == "EXPLAINS")
        up_m[:, j] = lo_m[:, j]
        if tol == "pm1c":
            same = (bj == fj)
            wlo = np.where(same, lo_s - 1, lo_s)
            whi = np.where(same, hi_s, hi_s + 1)
        elif tol == "pm1":
            wlo, whi = lo_s - 1, hi_s + 1
        elif tol == "pm2":
            wlo, whi = lo_s - 2, hi_s + 2
        else:
            raise ValueError(tol)
        inwin = (~np.isnan(bj)) & (bj >= wlo) & (bj <= whi)
        lo_m[:, j] |= inwin & ((b0 == "MISS-EARLY") | (b0 == "NEITHER"))
        up_m[:, j] = lo_m[:, j] | (inwin & (b0 == "UNRESOLVED"))
    return lo_m, up_m


def blk(rows):
    return rows["block"].to_numpy()


# ------------------------------------------------------------------ the printout parser
def parse_run():
    txt = RUN.read_text().splitlines()
    chunks, cur = [], None
    for ln in txt:
        if ln.startswith("decision "):
            cur = {"lines": [ln]}
            chunks.append(cur)
        elif cur is not None and ln.strip() == "":
            cur = None
        elif cur is not None:
            cur["lines"].append(ln)
    out = []
    hre = re.compile(r"^decision (\w+) — tolerance (.+?) — n (\d+) / (\d+) / (\d+); the chosen map: (.*); m (\d+); "
                     r"trees searched (\d+)$")
    for c in chunks:
        m = hre.match(c["lines"][0])
        assert m, c["lines"][0]
        ch = {"dec": m.group(1), "tol": TOLMAP[m.group(2)], "n": (int(m.group(3)), int(m.group(4)), int(m.group(5))),
              "mapdesc": m.group(6), "m": int(m.group(7)), "trees": int(m.group(8)), "rows": {}, "arms": [], "groups": [],
              "beside": [], "raw": c["lines"], "label": None}
        for ln in c["lines"][1:]:
            if ln.startswith("  group ["):
                gm = re.match(r"^  group \[(.*?)\] rule (\S+): 2020 n (\d+) -> ([\d.]+)?%?-? \(dated (\d+), EP (\d+);.*?\) \| "
                              r"2021-22 n (\d+) -> ([\d.]+%|-) \(dated (\d+), EP (\d+);.*?\) \| untouched n (\d+) -> "
                              r"([\d.]+%|-) \(dated (\d+), EP (\d+);", ln)
                if not gm:   # the share cell can be '-' for n 0
                    gm = re.match(r"^  group \[(.*?)\] rule (\S+): 2020 n (\d+) -> ([\d.]+%|-) \(dated (\d+), EP (\d+);.*?\) \| "
                                  r"2021-22 n (\d+) -> ([\d.]+%|-) \(dated (\d+), EP (\d+);.*?\) \| untouched n (\d+) -> "
                                  r"([\d.]+%|-) \(dated (\d+), EP (\d+);", ln)
                assert gm, ln
                g = gm.groups()
                # the first regex can mis-split; re-parse robustly
                gm2 = re.match(r"^  group \[(.*?)\] rule (\S+): 2020 n (\d+) -> ([\d.]+%|-) \(dated (\d+), EP (\d+);.*?\) \| "
                               r"2021-22 n (\d+) -> ([\d.]+%|-) \(dated (\d+), EP (\d+);.*?\) \| untouched n (\d+) -> "
                               r"([\d.]+%|-) \(dated (\d+), EP (\d+);", ln)
                g = gm2.groups()
                ch["groups"].append({"desc": g[0], "rule": g[1],
                                     "n": (int(g[2]), int(g[6]), int(g[10])),
                                     "sh": (g[3], g[7], g[11]),
                                     "dated": (int(g[4]), int(g[8]), int(g[12])),
                                     "ep": (int(g[5]), int(g[9]), int(g[13]))})
            elif ln.startswith("  -> context helps"):
                lm = re.match(r"^  -> context helps: (\w+) \(2020 (\w+), 2021-22 (\w+)\) \| beats chance .*?: (\w+) \| "
                              r"SUMMARY.*?: (.+)$", ln)
                assert lm, ln
                ch["label"] = {"helps": lm.group(1), "h20": lm.group(2), "h22": lm.group(3), "beats": lm.group(4),
                               "summary": lm.group(5)}
            elif ln.startswith("  beside"):
                ch["beside"].append(ln)
            elif ln.startswith("  controls:") or ln.startswith("  missing per context"):
                ch.setdefault("misc", []).append(ln)
            elif "|" in ln and ln.startswith("  "):
                cells = [x.strip() for x in ln.split("|")]
                lab = cells[0]
                if lab.startswith("---") or lab.startswith("line") or lab.startswith("+-"):
                    continue
                am = re.match(r"^\((c-[12])\) (.*)$", lab)
                if am and "largest arm" not in lab:
                    arm = []
                    for cell in cells[1:3]:
                        mm = re.match(r"^MAP ([\d.]+)% / BEST ([\d.]+)% -> net gain ([+-][\d.]+)$", cell)
                        assert mm, cell
                        arm.append((mm.group(1), mm.group(2), mm.group(3)))
                    ch["arms"].append({"kind": am.group(1), "name": am.group(2), "cells": arm})
                else:
                    ch["rows"][lab if not lab.startswith("BEST") else "BEST"] = cells[1:]
                    if lab.startswith("BEST"):
                        ch["best_rule"] = re.match(r"^BEST \((.*)\)$", lab).group(1)
        out.append(ch)
    return out, txt


CH, RUNTXT = parse_run()


def getch(dec, tol):
    for c in CH:
        if c["dec"] == dec and c["tol"] == tol:
            return c
    raise KeyError((dec, tol))


# ------------------------------------------------------------------ groups.tsv helpers
def gmap(dec, tol, mp):
    s = GR[(GR.decision == dec) & (GR.tolerance == tol) & (GR["map"] == mp)].copy()
    return s


def share_by_set(df):
    """{set: (close_count, n)} from a groups.tsv slice"""
    o = {}
    for st, s in df.groupby("set"):
        o[st] = (int((s.close == "True").sum()), len(s))
    return o


def frac_str(num, den):
    return "-" if den == 0 else f"{100.0 * num / den:.1f}%"


say("# #705 CONTEXT RULES - independent RECOUNT of the RUN (written from the doc's definitions; the module under test is NOT imported)")
say("# inputs: 01_ctx_run.txt (claims) | out/groups.tsv, contexts.tsv, maps.tsv, controls.tsv.gz | rule-mix tags_{enter,stop,exit}.tsv (+-0 buckets) | doc pins under the FREEZE marker")
say("# bucket vocabulary: confirmed in the rule-mix doc docs/analysis/cb_rule_mix_prereg_2026-10-25.md (EXPLAINS defined at l.215 for ENTER, l.249 for the window unit; MISS-EARLY / NEITHER / UNRESOLVED in its 4a table) and as seen in the tag files: "
    + ", ".join(sorted(set(TAG["EXIT"]["M-1_bucket"]) - {""})) + " ; CLOSE at +-0 = EXPLAINS (identity-tested row for row in check 3)")
say(f"# pins parsed under the marker: {len(PINS)} ctx_const_* lines")
say("# populations rebuilt from the tag files' own label columns (ENTER: tagged & (dated | not flicker); STOP: scorable & room & loser; EXIT: scorable & room):")
for d in LIB:
    say(f"#   {d}: " + " / ".join(str(int((POP[d].block == b).sum())) for b in BLOCKS) + (
        f"   (ENTER beside, undated flickers: " + " / ".join(str(int((BESIDE.block == b).sum())) for b in BLOCKS) + ")" if d == "ENTER" else ""))
say()

# =========================================================================================================
say("=" * 110)
say("CHECK 0 - the populations: tag-file-derived sets vs the printed n, groups.tsv and contexts.tsv (denominators of every share)")
ok = True
for d in LIB:
    exp = tuple(int((POP[d].block == b).sum()) for b in BLOCKS)
    for ch in CH:
        if ch["dec"] == d:
            atom()
            if ch["n"] != exp:
                ok = False
                say(f"    {d} {ch['tol']}: printed n {ch['n']} vs tag-derived {exp}")
    eids_tags = set(POP[d].eid)
    eids_ctx = set(CX[(CX.decision == d) & (CX.set == "scorable")].eid)
    eids_gr = set(GR[(GR.decision == d) & (~GR.set.str.contains("beside"))].eid)
    atom(2)
    if eids_tags != eids_ctx or eids_tags != eids_gr:
        ok = False
        say(f"    {d}: eid sets differ (tags {len(eids_tags)}, contexts {len(eids_ctx)}, groups {len(eids_gr)})")
bs = set(BESIDE.eid)
atom()
if bs != set(CX[(CX.decision == "ENTER") & (CX.set == "beside")].eid):
    ok = False
    say("    ENTER beside eid set differs")
rec("0", ok, "printed n, tag-derived populations, contexts.tsv and groups.tsv carry the same trade sets (ENTER 88/60/9 + beside 30/19/7, STOP 139/116/12, EXIT 333/229/44)")
say()

# =========================================================================================================
say("=" * 110)
say("CHECK 1 - every share the groups.tsv can reproduce: MAP / MAP-T1 / HW / SW / group n and share / beside lines; BEST where the tag files can reproduce it")
bad1 = []
n1 = 0


def cmp1(label, printed, mine):
    global n1
    n1 += 1
    atom()
    if printed != mine:
        bad1.append((label, printed, mine))


for ch in CH:
    dec, tol = ch["dec"], ch["tol"]
    # ---- MAP line
    s = share_by_set(gmap(dec, tol, "MAP")[lambda x: ~x.set.str.contains("beside")])
    mrow = ch["rows"]["MAP"]
    for i, b in enumerate(BLOCKS[:2]):
        cmp1(f"{dec} {tol} MAP {b}", mrow[i].split("%")[0] + "%", frac_str(*s[b]))
        cmp1(f"{dec} {tol} MAP {b} n", re.search(r"\(n (\d+)\)", mrow[i]).group(1), str(s[b][1]))
    cmp1(f"{dec} {tol} MAP untouched n", re.search(r"\(n (\d+)\)", mrow[2]).group(1), str(s["untouched"][1]))
    # ---- group lines
    gdf = gmap(dec, tol, "MAP")
    for gi, g in enumerate(ch["groups"]):
        sub = gdf[(gdf.group == str(gi)) & (~gdf.set.str.contains("beside"))]
        cmp1(f"{dec} {tol} group{gi} desc", g["desc"], sub.group_desc.iloc[0] if len(sub) else None)
        cmp1(f"{dec} {tol} group{gi} rule", g["rule"], sub.rule.iloc[0] if len(sub) else None)
        for i, b in enumerate(BLOCKS):
            ss = sub[sub.set == b]
            cmp1(f"{dec} {tol} group{gi} {b} n", str(g["n"][i]), str(len(ss)))
            cmp1(f"{dec} {tol} group{gi} {b} share", g["sh"][i], frac_str(int((ss.close == "True").sum()), len(ss)))
    # ---- dated counts per group (tags 'dated' column)
    tg = TAG[dec].set_index("eid")
    for gi, g in enumerate(ch["groups"]):
        sub = gdf[(gdf.group == str(gi)) & (~gdf.set.str.contains("beside"))]
        for i, b in enumerate(BLOCKS):
            ss = sub[sub.set == b]
            nd = int(sum(tg.loc[e, "dated"] == "True" for e in ss.eid))
            cmp1(f"{dec} {tol} group{gi} {b} dated", str(g["dated"][i]), str(nd))
    # ---- beside one-liners (MAP-T1, HW-*, SW-*) and the undated flickers / losers lines
    for ln in ch["beside"]:
        bm = re.match(r"^  beside (MAP-T1|HW-[A-Z]'?|SW-[ab]) — .*?: 2020 ([\d.]+)% / 2021-22 ([\d.]+)% / untouched ([\d.]+)% "
                      r"vs its BEST ([\d.]+)% / ([\d.]+)%", ln)
        if bm:
            nm = bm.group(1)
            s2 = share_by_set(gmap(dec, tol, nm))
            for i, b in enumerate(BLOCKS):
                cmp1(f"{dec} {tol} {nm} {b}", bm.group(2 + i) + "%", frac_str(*s2[b]))
            continue
        um = re.match(r"^  beside, the undated flickers .*?: 2020 n (\d+): MAP ([\d.]+)% / BEST ([\d.]+)%; 2021-22 n (\d+): MAP "
                      r"([\d.]+)% / BEST ([\d.]+)%; untouched n (\d+): MAP ([\d.]+)% / BEST ([\d.]+)%$", ln)
        if um:
            gb = gmap(dec, tol, "MAP")
            for i, b in enumerate(BLOCKS):
                ss = gb[gb.set == b + "|beside"]
                cmp1(f"{dec} {tol} flicker {b} n", um.group(1 + 3 * i), str(len(ss)))
                cmp1(f"{dec} {tol} flicker {b} MAP", um.group(2 + 3 * i) + "%", frac_str(int((ss.close == "True").sum()), len(ss)))
            if tol == "bracket":     # BEST = L1 at the bracket == EXPLAINS: the tag file
                for i, b in enumerate(BLOCKS):
                    t = BESIDE[BESIDE.block == b]
                    cmp1(f"{dec} {tol} flicker {b} BEST(L1)", um.group(3 + 3 * i) + "%",
                         frac_str(int((t["L1_bucket"] == "EXPLAINS").sum()), len(t)))
            continue
        lm = re.match(r"^  beside, losers / non-losers: (.*)$", ln)
        if lm:
            gb = gmap(dec, tol, "MAP")
            tg2 = TAG[dec].set_index("eid")
            for part in lm.group(1).split("; "):
                pm = re.match(r"^(2020|2021-22|untouched) (losers|non-losers) n (\d+): MAP ([\d.]+)% / BEST ([\d.]+)%$", part)
                assert pm, part
                b, kind = pm.group(1), pm.group(2)
                ss = gb[gb.set == b]
                ls = np.array([tg2.loc[e, "loser"] == "True" for e in ss.eid])
                ss = ss[ls] if kind == "losers" else ss[~ls]
                cmp1(f"{dec} {tol} {kind} {b} n", pm.group(3), str(len(ss)))
                cmp1(f"{dec} {tol} {kind} {b} MAP", pm.group(4) + "%", frac_str(int((ss.close == "True").sum()), len(ss)))
rec("1a", not bad1, f"{n1} printed MAP / group n+share+rule+desc / dated counts / MAP-T1 / HW / SW / undated-flicker MAP / losers-non-losers MAP values recomputed from groups.tsv"
    + ("" if not bad1 else f"; {len(bad1)} differ"))
for b in bad1[:30]:
    say(f"    printed {b[1]!r} vs recount {b[2]!r}  [{b[0]}]")
say()

# ---- 1b: BEST / UNION / ORACLE-1 (tag-derived)
say("CHECK 1b - BEST, UNION and ORACLE-1 shares recounted from the tag-file buckets (+-0 / bracket exact; widened tolerances via the derived +-1c/+-1/+-2 window, lower & upper bound)")
bad1b, n1b, wide_notes = [], 0, []
DER = {}     # (dec, tol) -> (rows df, lower, upper)
for dec in LIB:
    for tol in (["bracket"] if dec == "ENTER" else ["pm0", "pm1c", "pm1", "pm2"]):
        rows = POP[dec]
        lo_m, up_m = close_matrices(dec, tol, rows)
        DER[(dec, tol)] = (rows, lo_m, up_m)
        ch = getch(dec, tol)
        bl = blk(rows)
        cnt20 = lo_m[bl == "2020"].sum(0)
        bi = int(np.argmax(cnt20))                     # first max = library order tie-break
        brule = LIB[dec][bi]
        n1b += 1
        atom()
        if brule != ch["best_rule"]:
            # if the upper bound would pick the printed rule, note it
            bad1b.append((f"{dec} {tol} BEST rule", ch["best_rule"], brule))
        pbest = ch["rows"]["BEST"]
        # use the PRINTED rule's column so a rule mismatch does not hide the share comparison
        bj = LIB[dec].index(ch["best_rule"]) if ch["best_rule"] in LIB[dec] else bi
        for i, b in enumerate(BLOCKS):
            m_lo = lo_m[bl == b][:, bj].sum(); m_up = up_m[bl == b][:, bj].sum(); n_b = int((bl == b).sum())
            lo_s, up_s = frac_str(m_lo, n_b), frac_str(m_up, n_b)
            pr = pbest[i]
            n1b += 1
            atom()
            if pr != lo_s:
                if pr == up_s or (t10(lo_s) <= t10(pr) <= t10(up_s)):
                    wide_notes.append(f"{dec} {tol} BEST {b}: printed {pr} lies between derived lower {lo_s} and upper {up_s} (UNRESOLVED-upgrade cells)")
                else:
                    bad1b.append((f"{dec} {tol} BEST({ch['best_rule']}) {b}", pr, f"{lo_s}..{up_s}"))
        # UNION
        ucell = ch["rows"]["UNION"]
        for i, b in enumerate(BLOCKS[:2]):
            n_b = int((bl == b).sum())
            u_lo = lo_m[bl == b].any(1).sum(); u_up = up_m[bl == b].any(1).sum()
            pr = ucell[i].split("%")[0] + "%"
            n1b += 1
            atom()
            if pr != frac_str(u_lo, n_b):
                if t10(frac_str(u_lo, n_b)) <= t10(pr) <= t10(frac_str(u_up, n_b)):
                    wide_notes.append(f"{dec} {tol} UNION {b}: printed {pr} between derived {frac_str(u_lo, n_b)} and {frac_str(u_up, n_b)}")
                else:
                    bad1b.append((f"{dec} {tol} UNION {b}", pr, f"{frac_str(u_lo, n_b)}..{frac_str(u_up, n_b)}"))
        # ORACLE-1: 2021-22's own best single rule
        o = ch["rows"]["ORACLE-1"][1]
        om = re.match(r"^([\d.]+)% \((.*)\)$", o)
        c22 = lo_m[bl == "2021-22"].sum(0)
        oi = int(np.argmax(c22))
        n1b += 1
        atom()
        mine_o = f"{100.0 * c22[oi] / int((bl == '2021-22').sum()):.1f}% ({LIB[dec][oi]})"
        if mine_o != o:
            u22 = up_m[bl == "2021-22"].sum(0)
            bad1b.append((f"{dec} {tol} ORACLE-1", o, mine_o + f" [upper-bound rule counts max {int(u22.max())}]"))
rec("1b", not bad1b, f"{n1b} BEST rule+shares / UNION / ORACLE-1 recomputed from tag buckets ({'exact at +-0 and bracket' }; widened tolerances derived)"
    + ("" if not bad1b else f"; {len(bad1b)} differ"))
for b in bad1b[:30]:
    say(f"    printed {b[1]!r} vs recount {b[2]!r}  [{b[0]}]")
for w in wide_notes[:20]:
    say("    NOTE " + w)
say()

# ---- 1c: 'gap closed' = (MAP - BEST) / (UNION - BEST), from integer counts where the tag-derived matrices exist, else interval arithmetic on the printed one-decimal inputs
bad1c, n1c = [], 0
for ch in CH:
    dec, tol = ch["dec"], ch["tol"]
    mrow, brow, urow = ch["rows"]["MAP"], ch["rows"]["BEST"], ch["rows"]["UNION"]
    gdf_ = gmap(dec, tol, "MAP")
    for i in range(2):
        gm = re.search(r"gap closed (-?[\d.]+)%", urow[i]).group(1)
        n1c += 1
        atom()
        if (dec, tol) in DER:
            rows_, lo_m, up_m = DER[(dec, tol)]
            bl_ = blk(rows_)
            bj = LIB[dec].index(ch["best_rule"])
            nb = int((bl_ == BLOCKS[i]).sum())
            M = int((gdf_[gdf_.set == BLOCKS[i]].close == "True").sum())
            B = int(lo_m[bl_ == BLOCKS[i]][:, bj].sum())
            cands = set()
            for U in {int(lo_m[bl_ == BLOCKS[i]].any(1).sum()), int(up_m[bl_ == BLOCKS[i]].any(1).sum())}:
                cands.add("0.0" if U == B else f"{100.0 * (M - B) / (U - B):.1f}")
            if gm not in cands:
                bad1c.append((f"{dec} {tol} gap closed {BLOCKS[i]}", gm, sorted(cands)))
        else:
            # B1 / B2: BEST and UNION counts are not in the tag files; interval arithmetic over +-0.05 on each printed input
            M0, B0, U0 = (float(mrow[i].split("%")[0]), float(brow[i].rstrip("%")), float(urow[i].split("%")[0]))
            vals = [(m_ - b_) / (u_ - b_) * 100 for m_ in (M0 - .05, M0 + .05) for b_ in (B0 - .05, B0 + .05) for u_ in (U0 - .05, U0 + .05) if u_ != b_]
            if not vals or not (min(vals) - 0.06 <= float(gm) <= max(vals) + 0.06):
                bad1c.append((f"{dec} {tol} gap closed {BLOCKS[i]}", gm, f"interval {min(vals):.1f}..{max(vals):.1f}" if vals else "n/a"))
rec("1c", not bad1c, f"{n1c} 'gap closed' cells re-derived (integer counts where tag-derived; interval arithmetic on the printed inputs for ENTER B1/B2)"
    + ("" if not bad1c else f"; {len(bad1c)} differ"))
for b in bad1c[:20]:
    say(f"    printed {b[1]!r} vs recount {b[2]!r}  [{b[0]}]")
say()

# =========================================================================================================
say("=" * 110)
say("CHECK 2 - the group assignment: contexts.tsv + the pinned cuts + missing sides -> group, vs groups.tsv (every MAP line at every tolerance; MAP-T1 and HW-* too)")


def tok_eval(dec, tok, v, miss):
    """True when the (value, missing) satisfies one token of a group description."""
    m = re.match(r"^(C-[ESX]\d) (<=|>) (T1|T2) \(([-\d.e]+)\)$", tok)
    if m:
        ctx, op, cut, shown = m.groups()
        key = f"ctx_const_{dec}_{ctx}_{cut}"
        cv = pin_f(key)
        ml = pin_b(key + "_missing_left")
        TOK_SHOWN.append((key, shown, cv))
        if miss:
            return ml if op == "<=" else (not ml)
        return (v <= cv) if op == "<=" else (v > cv)
    m = re.match(r"^(C-[ESX]\d) = (\d)$", tok)
    if m:
        ctx, val = m.groups()
        ml = pin_b(f"ctx_const_{dec}_{ctx}_bin_missing_left")
        if miss:
            return ml if val == "0" else (not ml)
        return int(round(v)) == int(val)
    raise ValueError(tok)


TOK_SHOWN = []
CXI = CX.set_index(["eid", "decision", "set"])


def ctx_vals(dec, eid, st, ctxname):
    r = CXI.loc[(eid, dec, st)]
    mf = r[ctxname + "_missing"]
    v = r[ctxname]
    return (np.nan if v == "" else float(v)), (mf != "")


def tokens_of(desc):
    return [] if desc == "all" else desc.split(" & ")


bad2, n2 = [], 0
# 2a: MAP lines
for ch in CH:
    dec, tol = ch["dec"], ch["tol"]
    gdf = gmap(dec, tol, "MAP")
    descs = {}
    for r in gdf[["group", "group_desc"]].drop_duplicates().itertuples():
        descs[int(r.group)] = r.group_desc
    for r in gdf.itertuples():
        st = r.set.replace("|beside", "")
        cxset = "beside" if "beside" in r.set else "scorable"
        hit = []
        for gi, ds in descs.items():
            ok_all = True
            for tk in tokens_of(ds):
                ctxn = tk.split(" ")[0]
                v, ms = ctx_vals(dec, r.eid, cxset, ctxn)
                if not tok_eval(dec, tk, v, ms):
                    ok_all = False
                    break
            if ok_all:
                hit.append(gi)
        n2 += 1
        atom()
        if hit != [int(r.group)]:
            bad2.append((dec, tol, r.eid, r.set, int(r.group), hit))
rec("2a", not bad2, f"{n2} trade-in-group assignments of every MAP line (all tolerances, scorable + beside sets) re-derived from the descriptions; exactly one group must satisfy; {len(bad2)} disagreements"
    + ("" if not bad2 else f" e.g. {bad2[:3]}"))
# printed cut values equal the pins at the shown precision
badcut = [(k, s, c) for (k, s, c) in set(TOK_SHOWN) if f"{c:.4g}" != s]
rec("2b", not badcut, f"{len(set(TOK_SHOWN))} distinct (context, cut) tokens: the printed cut equals the pin at 4 significant digits" + ("" if not badcut else f"; differ: {badcut[:4]}"))
# 2c: the chosen PRIMARY maps spelled out
for dec in LIB:
    ch = getch(dec, PRIMARY[dec])
    gdf = gmap(dec, PRIMARY[dec], "MAP")
    say(f"    primary {dec} {PRIMARY[dec]}: {len(gdf)} trade rows over {gdf.group.nunique()} groups; disagreements in 2a restricted to this map: "
        f"{sum(1 for b in bad2 if b[0] == dec and b[1] == PRIMARY[dec])}")
# 2d: MAP-T1 (leaf list in maps.tsv desc) and HW maps
bad2d, n2d = [], 0
for ch in CH:
    dec, tol = ch["dec"], ch["tol"]
    for mp in ("MAP-T1", "HW-E", "HW-S", "HW-X", "HW-X'"):
        g = gmap(dec, tol, mp)
        if not len(g):
            continue
        desc = MP[(MP.decision == dec) & (MP.tolerance == tol) & (MP.line == mp)].desc.iloc[0]
        for r in g.itertuples():
            cxset = "beside" if "beside" in r.set else "scorable"
            if mp == "MAP-T1" and dec != "STOP":
                leaves = re.findall(r"\[(.*?)\] -> (\S+?)(?:;|$|:)", desc)
                hit = []
                for ds, rule in leaves:
                    ok_all = True
                    for tk in ds.split(" & "):
                        v, ms = ctx_vals(dec, r.eid, cxset, tk.split(" ")[0])
                        if not tok_eval(dec, tk, v, ms):
                            ok_all = False
                            break
                    if ok_all:
                        hit.append(rule)
                exp = hit[0] if len(hit) == 1 else None
            elif mp == "MAP-T1":     # STOP: the single tier-1 rule
                exp = "S1-T"
            else:
                cut = float(re.search(r"cut ([-\d.eE]+)", desc).group(1)) if "cut" in desc else None
                if mp == "HW-E":
                    v, ms = ctx_vals(dec, r.eid, cxset, "C-E1")
                    hi_r, lo_r = "L1", "L8"
                    cutv = pin_f("ctx_const_ENTER_C-E1_median")
                    exp = None if ms else (hi_r if v > cutv else lo_r)
                elif mp == "HW-S":
                    v, ms = ctx_vals(dec, r.eid, cxset, "C-S1")
                    if ms:
                        exp = "S1-T" if pin_b("ctx_const_STOP_C-S1_1.0_missing_left") else "S4-T"
                    else:
                        exp = "S1-T" if v <= 1.0 else "S4-T"
                elif mp == "HW-X":
                    v, ms = ctx_vals(dec, r.eid, cxset, "C-X1")
                    exp = "M-3" if v > pin_f("ctx_const_EXIT_C-X1_median") else "M-4"
                else:   # HW-X'
                    v, ms = ctx_vals(dec, r.eid, cxset, "C-X1")
                    exp = "M-3" if v > 0.0479 else "M-4"
            n2d += 1
            atom()
            if exp is not None and exp != r.rule:
                bad2d.append((dec, tol, mp, r.eid, r.set, r.rule, exp))
# HW-E missing side report
hwm = [r for r in gmap("ENTER", "bracket", "HW-E").itertuples()
       if ctx_vals("ENTER", r.eid, "beside" if "beside" in r.set else "scorable", "C-E1")[1]]
rec("2d", not bad2d, f"{n2d} trade-rule assignments of MAP-T1 / HW-E / HW-S / HW-X / HW-X' re-derived (HW-E's {len(hwm)} missing-C-E1 rows excluded: sides " f"{sorted(set(r.rule for r in hwm))} reported, not judged)"
    + ("" if not bad2d else f"; {len(bad2d)} disagreements e.g. {bad2d[:3]}"))
# 2e: tertile cuts and medians recomputed from contexts.tsv (2020 scorable, defined values)
bad2e = []
for dec, ctxs in (("ENTER", ["C-E1"]), ("STOP", ["C-S1", "C-S2"]), ("EXIT", ["C-X1", "C-X2", "C-X3"])):
    c20 = CX[(CX.decision == dec) & (CX.block == "2020") & (CX.set == "scorable")]
    for cn in ctxs:
        vals = np.sort(np.array([float(v) for v, mf in zip(c20[cn], c20[cn + "_missing"]) if v != "" and mf == ""]))
        n = len(vals)
        t1 = vals[math.ceil(n / 3) - 1]
        t2 = vals[math.ceil(2 * n / 3) - 1]
        med = vals[math.ceil(n / 2) - 1]
        for nm, mine in (("T1", t1), ("T2", t2)):
            k = f"ctx_const_{dec}_{cn}_{nm}"
            atom()
            if abs(mine - pin_f(k)) > 1e-12 * max(1, abs(mine)):
                bad2e.append((k, pin_f(k), mine))
        mk = f"ctx_const_{dec}_{cn}_median"
        if mk in PINS:
            atom()
            if abs(med - pin_f(mk)) > 1e-12 * max(1, abs(med)):
                bad2e.append((mk, pin_f(mk), med))
rec("2e", not bad2e, "the pinned tertile cuts T1/T2 (the ceil(n/3)-th and ceil(2n/3)-th smallest defined 2020 values) and the HW medians recomputed from contexts.tsv" + ("" if not bad2e else f"; differ: {bad2e}"))
# 2f: missing counts per context (printed 'missing per context' lines)
bad2f, n2f = [], 0
for ch in CH:
    for ln in ch.get("misc", []):
        if ln.startswith("  missing per context"):
            for cn, a, b, c in re.findall(r"(C-[ESX]\d) (\d+)/(\d+)/(\d+)", ln):
                for i, bk in enumerate(BLOCKS):
                    sub = CX[(CX.decision == ch["dec"]) & (CX.block == bk) & (CX.set == "scorable")]
                    mine = int((sub[cn + "_missing"] != "").sum())
                    n2f += 1
                    atom()
                    if str(mine) != (a, b, c)[i]:
                        bad2f.append((ch["dec"], ch["tol"], cn, bk, (a, b, c)[i], mine))
rec("2f", not bad2f, f"{n2f} printed 'missing per context' counts recounted from contexts.tsv's missing flags" + ("" if not bad2f else f"; differ: {bad2f[:4]}"))
say()

# =========================================================================================================
say("=" * 110)
say("CHECK 3 - +-0: every groups.tsv `close` equals the tag file's bucket for that trade's rule (CLOSE <=> EXPLAINS)")


def tag_close(dec, eid, rule):
    t = TAG[dec].set_index("eid")
    return t.loc[eid, rule + "_bucket"] == "EXPLAINS"


TI = {d: TAG[d].set_index("eid") for d in LIB}
for (dec, tol) in (("ENTER", "bracket"), ("STOP", "pm0"), ("EXIT", "pm0")):
    bad3, n3 = [], 0
    for mp in sorted(set(GR[(GR.decision == dec) & (GR.tolerance == tol)]["map"])):
        g = gmap(dec, tol, mp)
        if mp.startswith("SW"):
            continue          # composite rule, not a library rule: no bucket column
        for r in g.itertuples():
            n3 += 1
            atom()
            exp = TI[dec].loc[r.eid, r.rule + "_bucket"] == "EXPLAINS"
            if exp != (r.close == "True"):
                bad3.append((mp, r.eid, r.set, r.rule, r.close, TI[dec].loc[r.eid, r.rule + "_bucket"]))
    extra = ""
    if dec == "ENTER":
        extra = " (this is the claim that ENTER's primary 'bracket' IS the rule-mix EXPLAINS at +-0, doc 4b / 13 Q1)"
    rec(f"3.{dec}", not bad3, f"{dec} {tol}: {n3} (trade, rule) closes over all maps incl. beside sets vs tag bucket == EXPLAINS; {len(bad3)} disagreements{extra}"
        + ("" if not bad3 else f" e.g. {bad3[:3]}"))
# 3b: the widened tolerances against the derivation (validation of the derivation itself)
bad3b, n3b, up_cells = [], 0, 0
band_lines = []
for dec in ("STOP", "EXIT"):
    for tol in ("pm1c", "pm1", "pm2"):
        rows, lo_m, up_m = DER[(dec, tol)]
        idx = {e: i for i, e in enumerate(rows.eid)}
        for mp in sorted(set(GR[(GR.decision == dec) & (GR.tolerance == tol)]["map"])):
            if mp.startswith("SW"):
                continue
            nb_, ncell, nrunT = 0, 0, 0
            for r in gmap(dec, tol, mp).itertuples():
                i, j = idx[r.eid], LIB[dec].index(r.rule)
                n3b += 1
                ncell += 1
                atom()
                run_c = r.close == "True"
                if not (lo_m[i, j] <= run_c <= up_m[i, j]):
                    bad3b.append((dec, tol, mp, r.eid, r.rule, run_c, bool(lo_m[i, j]), bool(up_m[i, j])))
                inband = int(lo_m[i, j] != up_m[i, j])
                up_cells += inband
                nb_ += inband
                nrunT += inband * int(run_c)
            if mp == "MAP":
                band_lines.append(f"    {dec} {tol} MAP: {nb_} of {ncell} assigned (trade, rule) cells sit in the undecidable band ({nrunT} of them CLOSE in the run); the other {ncell - nb_} are exactly reproduced")
for bl_ in band_lines:
    say(bl_)
rec("3b", not bad3b, f"derived +-1c / +-1 / +-2 window (from +-0 bucket, first_j, booked_j, exit_lo_j, exit_hi_j) brackets every run `close` on {n3b} assigned (trade, rule) cells "
    f"({up_cells} of them fall in the undecidable UNRESOLVED-upgrade band); {len(bad3b)} outside the band" + ("" if not bad3b else f" e.g. {bad3b[:3]}"))
say()

# =========================================================================================================
say("=" * 110)
say("CHECK 4 - the 2020 search recounted: every depth<=2 tree over the candidate splits, floor m, leaf = best rule, max CLOSE; at bracket (ENTER) / +-0 (STOP, EXIT) from the tag buckets alone;")
say("          and (derived widening) at the primary +-1c, +-1, +-2 for STOP/EXIT")

SPLITS = {
    "ENTER": [("C-E1", "T1"), ("C-E1", "T2"), ("C-E2", "bin"), ("C-E3", "bin")],
    "STOP": [("C-S1", "1.0"), ("C-S1", "T1"), ("C-S1", "T2"), ("C-S2", "T1"), ("C-S2", "T2"), ("C-S3", "bin")],
    "EXIT": [("C-X1", "T1"), ("C-X1", "T2"), ("C-X2", "T1"), ("C-X2", "T2"), ("C-X3", "T1"), ("C-X3", "T2"), ("C-X4", "bin")],
}


class Split:
    def __init__(self, dec, ctx, cut):
        self.dec, self.ctx, self.cut = dec, ctx, cut
        key = f"ctx_const_{dec}_{ctx}_{cut}"
        self.miss_left = pin_b(key + "_missing_left")
        self.val = 1.0 if cut == "1.0" else (None if cut == "bin" else pin_f(key))

    def left(self, cx):
        # python float() (correctly rounded); pandas to_numeric can differ from it by one ULP at a tie with the pinned cut
        v = np.array([float(x) if x != "" else np.nan for x in cx[self.ctx]], dtype=float)
        miss = (cx[self.ctx + "_missing"] != "").to_numpy()
        base = (v <= 0.5) if self.cut == "bin" else (v <= self.val)
        return np.where(miss, self.miss_left, base)

    def name(self):
        if self.cut == "bin":
            return f"{self.ctx}=0"
        return f"{self.ctx}<={self.cut if self.cut != '1.0' else '1.0'}"


def ctx_frame(dec, rows, block=None):
    """context rows aligned to `rows` (tag rows) by eid"""
    c = CX[(CX.decision == dec) & (CX.set == "scorable")].set_index("eid")
    return c.loc[rows.eid.tolist()]


def enumerate_trees(splits, lefts, m, n):
    """all depth<=2 trees; each = (root, lopt, ropt, leaf masks)"""
    S = len(splits)
    trees = [(-1, -1, -1, [np.ones(n, bool)])]
    for r in range(S):
        lm, rm = lefts[r], ~lefts[r]
        if lm.sum() < m or rm.sum() < m:
            continue
        def opts(mask):
            o = [(-1, [mask])]
            for k in range(S):
                a, b = mask & lefts[k], mask & ~lefts[k]
                if a.sum() >= m and b.sum() >= m:
                    o.append((k, [a, b]))
            return o
        for lo_, ll in opts(lm):
            for ro_, rl in opts(rm):
                trees.append((r, lo_, ro_, ll + rl))
    return trees


def score_tree(tree, C):
    tot, rules = 0, []
    for mk in tree[3]:
        cnt = C[mk].sum(0)
        j = int(np.argmax(cnt))
        tot += int(cnt[j])
        rules.append(j)
    return tot, rules


def search(dec, tol, lower_only=True, which="lo", allowed=None):
    rows, lo_m, up_m = DER[(dec, tol)]
    C = lo_m if which == "lo" else up_m
    if allowed is not None:       # restricted library (MAP-T1): disallowed columns can never be CLOSE, library-first column is tier 1
        C = C & np.array([r in allowed for r in LIB[dec]])[None, :]
    cx = ctx_frame(dec, rows)
    bl = blk(rows)
    i20 = bl == "2020"
    cx20 = cx[i20]
    n = int(i20.sum())
    m = max(15, math.ceil(0.10 * n))
    raw = [Split(dec, c, k) for c, k in SPLITS[dec]]
    kept, lefts, dropped = [], [], []
    for s in raw:
        l = s.left(cx20)
        dup = None
        for k2, l2 in zip(kept, lefts):
            if np.array_equal(l, l2):
                dup = k2
                break
        if dup is None:
            kept.append(s)
            lefts.append(l)
        else:
            dropped.append((s.name(), dup.name()))
    trees = enumerate_trees(kept, lefts, m, n)
    scored = []
    C20 = C[i20]
    for t in trees:
        tot, rules = score_tree(t, C20)
        ng = len(t[3])
        scored.append(((-tot, ng, t[0], t[1], t[2]), tot, rules, t))
    scored.sort(key=lambda x: x[0])
    best = scored[0]
    maxers = [s for s in scored if s[1] == best[1]]
    return dict(rows=rows, C=C, cx=cx, bl=bl, kept=kept, lefts=lefts, dropped=dropped, trees=trees, scored=scored,
                best=best, maxers=maxers, m=m, n=n)


def tree_assign(res, tree, rules):
    """per-trade (group, rule index) for the whole population (all blocks) by the tree"""
    kept = res["kept"]
    cx = res["cx"]
    nn = len(res["rows"])
    g = np.full(nn, -1)
    rr = np.full(nn, -1)
    r, lo_, ro_, leaves = tree
    if r == -1:
        g[:] = 0
        rr[:] = rules[0]
        return g, rr
    L = [s.left(cx) for s in kept]
    def child(mask, opt):
        return [mask] if opt == -1 else [mask & L[opt], mask & ~L[opt]]
    masks = child(L[r], lo_) + child(~L[r], ro_)
    for gi, mk in enumerate(masks):
        g[mk] = gi
        rr[mk] = rules[gi]
    return g, rr


def run_assign(dec, tol):
    """the run's own per-trade rule for MAP (scorable sets)"""
    g = gmap(dec, tol, "MAP")
    g = g[~g.set.str.contains("beside")]
    return dict(zip(g.eid, g.rule)), dict(zip(g.eid, g.close == "True")), g


bad4, n4 = [], 0
for dec, tols in (("ENTER", ["bracket"]), ("STOP", ["pm0", "pm1c", "pm1", "pm2"]), ("EXIT", ["pm0", "pm1c", "pm1", "pm2"])):
    for tol in tols:
        ch = getch(dec, tol)
        res = search(dec, tol, which="lo")
        resu = search(dec, tol, which="up")
        rows, bl = res["rows"], res["bl"]
        run_rule, run_close, rg = run_assign(dec, tol)
        run20 = sum(run_close[e] for e, b in zip(rows.eid, bl) if b == "2020")
        bt = res["best"]
        # the run's tree as a per-trade rule assignment: is it among my maximizers (same 2020 CLOSE count)?
        my_tot_lo, my_tot_up = bt[1], resu["best"][1]
        tc_ok = (res["trees"].__len__() == ch["trees"])
        # same-assignment test vs my canonical choice
        g_, rr_ = tree_assign(res, bt[3], bt[2])
        same_assign = all(LIB[dec][rr_[i]] == run_rule[e] for i, e in enumerate(rows.eid))
        in_max = any(
            all(LIB[dec][tree_assign(res, s[3], s[2])[1][i]] == run_rule[e] for i, e in enumerate(rows.eid)) for s in res["maxers"])
        # my chosen tree scored on 2021-22 / untouched, vs the run's printed
        sc = {}
        for b in BLOCKS:
            mk = bl == b
            sc[b] = (int(res["C"][mk][np.arange(mk.sum()), rr_[mk]].sum()), int(mk.sum()))
        prt = ch["rows"]["MAP"]
        sh22_mine = frac_str(*sc["2021-22"])
        sh22_prt = prt[1].split("%")[0] + "%"
        sh22_run = frac_str(sum(run_close[e] for e, b in zip(rows.eid, bl) if b == "2021-22"), int((bl == "2021-22").sum()))
        n4 += 1
        atom()
        ok_here = tc_ok and (my_tot_lo <= run20 <= my_tot_up) and (in_max or my_tot_lo != my_tot_up)
        flag = "MATCH" if ok_here else "MISMATCH"
        say(f"  {dec} {tol}: trees after dedupe+floor mine {len(res['trees'])} vs printed {ch['trees']} ({'dropped dup splits: ' + str(res['dropped']) if res['dropped'] else 'no duplicate split'}); "
            f"max 2020 CLOSE mine {my_tot_lo}" + (f" (upper bound {my_tot_up})" if my_tot_lo != my_tot_up else "") + f" vs run's chosen map {run20} "
            f"[{run20 / res['n']:.1%}]; maximizers (lower) {len(res['maxers'])}; run's tree {'IS' if in_max else 'is NOT'} among them; "
            f"my canonical tie-break {'reproduces' if same_assign else 'differs from'} the run's per-trade rules; "
            f"2021-22: my canonical {sh22_mine} / run's tree {sh22_run} / printed {sh22_prt} -> {flag}")
        if not ok_here:
            bad4.append((dec, tol, len(res["trees"]), ch["trees"], my_tot_lo, my_tot_up, run20))
        # 2021-22 share of the run's chosen tree (always compare to the printed)
        n4 += 1
        atom()
        if sh22_run != sh22_prt:
            bad4.append((dec, tol, "2021-22 share of run's tree", sh22_run, sh22_prt))
        # BEST (no-split) per decision at this tolerance: the 2020 count
        nos = [s for s in res["scored"] if s[3][0] == -1][0]
        say(f"      BEST (no split) mine: rule {LIB[dec][nos[2][0]]} 2020 CLOSE {nos[1]}/{res['n']} = {nos[1] / res['n']:.1%}; printed BEST {ch['best_rule']} {ch['rows']['BEST'][0]}")
        n4 += 1
        atom()
        if LIB[dec][nos[2][0]] != ch["best_rule"] or frac_str(nos[1], res["n"]) != ch["rows"]["BEST"][0]:
            # allow the upper-bound band for widened tolerances
            if not (tol in ("pm1c", "pm1", "pm2") and LIB[dec][nos[2][0]] == ch["best_rule"]):
                bad4.append((dec, tol, "BEST", LIB[dec][nos[2][0]], nos[1], ch["best_rule"], ch["rows"]["BEST"][0]))
rec("4", not bad4, f"{n4} comparisons: tree counts, max 2020 CLOSE, 2021-22 share of the run's tree, BEST (ENTER bracket, STOP/EXIT +-0 exact from tag buckets; +-1c/+-1/+-2 via the derived window with a lower/upper band)"
    + ("" if not bad4 else f"; {len(bad4)} differ: {bad4[:4]}"))
say()


# 4b: MAP-T1 (the same search restricted to the tier-1 rules, doc 5e): ENTER bracket, STOP pm1c (single rule S1-T), EXIT pm1c
TIER1 = {"ENTER": ["L1", "L8", "L2", "L7", "L3"], "STOP": ["S1-T"], "EXIT": ["M-1", "M-2", "M-3", "M-4", "M-5", "M-9", "M-6", "M-2s", "M-11"]}
bad4b = []
for dec, tol in (("ENTER", "bracket"), ("STOP", "pm1c"), ("EXIT", "pm1c")):
    ch = getch(dec, tol)
    res = search(dec, tol, which="lo", allowed=TIER1[dec])
    resu = search(dec, tol, which="up", allowed=TIER1[dec])
    rows, bl = res["rows"], res["bl"]
    bt = res["best"]
    g_, rr_ = tree_assign(res, bt[3], bt[2])
    mt = gmap(dec, tol, "MAP-T1")
    mt = mt[~mt.set.str.contains("beside")]
    run20 = int(((mt.set == "2020") & (mt.close == "True")).sum())
    sc22 = int(res["C"][bl == "2021-22"][np.arange(int((bl == "2021-22").sum())), rr_[bl == "2021-22"]].sum())
    prt = None
    for ln in ch["beside"]:
        bm = re.match(r"^  beside MAP-T1 \u2014 .*?: 2020 ([\d.]+)% / 2021-22 ([\d.]+)% / untouched ([\d.]+)% vs its BEST ([\d.]+)% / ([\d.]+)%", ln)
        if bm:
            prt = bm.groups()
    nos = [x for x in res["scored"] if x[3][0] == -1][0]
    n4b_ok = (res["n"] and bt[1] <= run20 <= resu["best"][1]) and frac_str(sc22, int((bl == "2021-22").sum())) == prt[1] + "%" \
        and frac_str(nos[1], res["n"]) == prt[3] + "%"
    atom(3)
    say(f"  MAP-T1 {dec} {tol}: my max 2020 CLOSE {bt[1]} (upper {resu['best'][1]}) vs run's MAP-T1 {run20}; my tree on 2021-22 {frac_str(sc22, int((bl == '2021-22').sum()))} vs printed {prt[1]}%; "
        f"BEST-T1 rule {LIB[dec][nos[2][0]]} 2020 {frac_str(nos[1], res['n'])} vs printed 'its BEST' {prt[3]}% -> {'MATCH' if n4b_ok else 'MISMATCH'}")
    if not n4b_ok:
        bad4b.append((dec, tol))
rec("4b", not bad4b, "MAP-T1 (search restricted to the tier-1 rules): max 2020 CLOSE, 2021-22 share of the chosen tree and the tier-1 BEST (`its BEST`) recounted for ENTER bracket, STOP +-1c, EXIT +-1c" + ("" if not bad4b else f"; differ: {bad4b}"))
say()
# =========================================================================================================
say("=" * 110)
say("CHECK 5 - the labels re-derived from the printed one-decimal numbers (helps, beats chance, SUMMARY) for every table and every beside line")


def label_from_table(ch):
    mrow, brow = ch["rows"]["MAP"], ch["rows"]["BEST"]
    sh = ch["rows"]["SHUF mean"]
    M = [t10(mrow[i].split("%")[0]) for i in range(2)]
    B = [t10(brow[i]) for i in range(2)]
    S = [t10(re.match(r"^([\d.]+)%", sh[i]).group(1)) for i in range(2)]
    help_b = [(M[i] >= B[i] + 100) and (M[i] >= S[i] + 100) for i in range(2)]
    helps = all(help_b)
    beats_blocks = [True, True]
    nets = []
    for a in ch["arms"]:
        for i in range(2):
            mp_, bp_, ng = a["cells"][i]
            net = (M[i] - B[i]) - (t10(mp_) - t10(bp_))
            nets.append((a["kind"], a["name"], i, net, round(float(ng) * 10)))
            if net < 100:
                beats_blocks[i] = False
    beats = all(beats_blocks)
    return helps, help_b, beats, nets


def summary_of(h, b):
    return "context map" if (h and b) else ("context helps, chance too" if h else "no context gain")


bad5, n5, bad5net = [], 0, []
for ch in CH:
    h, hb, b, nets = label_from_table(ch)
    lab = ch["label"]
    n5 += 1
    atom(3)
    yn = lambda x: "yes" if x else "no"
    exp = (yn(h), yn(hb[0]), yn(hb[1]), yn(b), summary_of(h, b))
    got = (lab["helps"], lab["h20"], lab["h22"], lab["beats"], lab["summary"])
    if exp != got:
        bad5.append((ch["dec"], ch["tol"], got, exp))
    for (k, nm, i, net, pnet) in nets:
        n5 += 1
        atom()
        if abs(net - pnet) > 2:          # three/four rounded inputs: allow 0.2 point
            bad5net.append((ch["dec"], ch["tol"], k, nm, BLOCKS[i], pnet / 10, net / 10))
rec("5a", not bad5, f"{len(CH)} full tables: helps (per block and both) / beats chance (every arm, both blocks, gains >= 10.0) / SUMMARY re-derived from the printed numbers"
    + ("" if not bad5 else f"; {len(bad5)} differ: {bad5}"))
rec("5b", not bad5net, f"{sum(len(ch['arms']) * 2 for ch in CH)} printed 'net gain' cells re-derived as (MAP-BEST) - (chance MAP - chance BEST) from the printed levels (allow 0.2 point for rounding)"
    + ("" if not bad5net else f"; {len(bad5net)} differ: {bad5net[:5]}"))
# closest-call margins, so a label sitting on a threshold is visible
close_calls = []
for ch in CH:
    h, hb, b, nets = label_from_table(ch)
    for (k, nm, i, net, pnet) in nets:
        if 80 <= net < 100 or 100 <= net <= 110:
            close_calls.append(f"{ch['dec']} {ch['tol']} {k} {nm} {BLOCKS[i]} net {net / 10:+.1f}")
    mrow, brow = ch["rows"]["MAP"], ch["rows"]["BEST"]
    for i in range(2):
        g = t10(mrow[i].split("%")[0]) - t10(brow[i])
        if 80 <= g <= 120:
            close_calls.append(f"{ch['dec']} {ch['tol']} MAP-BEST {BLOCKS[i]} {g / 10:+.1f}")
say("    printed values within 2.0 points of a 10.0 threshold: " + ("; ".join(close_calls) if close_calls else "none"))

# 5b2: does `beats chance` depend on the both-blocks reading?  recompute it as 2020-only and as 2021-22-only
alt = []
for ch in CH:
    h, hb, b, nets = label_from_table(ch)
    only20 = all(net >= 100 for (k, nm, i, net, pnet) in nets if i == 0)
    only22 = all(net >= 100 for (k, nm, i, net, pnet) in nets if i == 1)
    alt.append((ch["dec"], ch["tol"], only20, only22, ch["label"]["beats"]))
rec("5b2", not any(a[2] or a[3] for a in alt) and all(a[4] == "no" for a in alt),
    f"`beats chance` is `no` in all {len(alt)} full tables under any block reading (2020 only / 2021-22 only / both) - the printed labels do not rest on the both-blocks wording")

# 5c: beside one-liners
bad5c, n5c, notder = [], 0, []
for ch in CH:
    dec, tol = ch["dec"], ch["tol"]
    for ln in ch["beside"]:
        bm = re.match(r"^  beside (MAP-T1|HW-[A-Z]'?|SW-[ab]) — .*?: 2020 ([\d.]+)% / 2021-22 ([\d.]+)% / untouched ([\d.]+)% "
                      r"vs its BEST ([\d.]+)% / ([\d.]+)%; SHUF ([\d.]+)% / ([\d.]+)%; (.*?) -> helps (\w+), beats chance (\w+): (.+?) "
                      r"\(beside", ln)
        if not bm:
            continue
        nm = bm.group(1)
        M = [t10(bm.group(2)), t10(bm.group(3))]
        B = [t10(bm.group(5)), t10(bm.group(6))]
        S = [t10(bm.group(7)), t10(bm.group(8))]
        helps = all(M[i] >= B[i] + 100 and M[i] >= S[i] + 100 for i in range(2))
        arms = re.findall(r"(\w+): \(c-1\) ([\d.]+)% / ([\d.]+)%, \(c-2\) ([\d.]+)% / ([\d.]+)%", bm.group(9))
        # BEST's chance levels, from the full table of the same decision and tolerance (valid when 'its BEST' is the table's BEST)
        same_best = (B[0] == t10(ch["rows"]["BEST"][0]) and B[1] == t10(ch["rows"]["BEST"][1]))
        armmap = {"kprice": "k-price random prices", "shared": "the shared random window", "a_frames": "control (a), frames",
                  "a_noframes": "control (a), no frames", "rlevel": "random levels"}
        beats = None
        if same_best:
            beats = True
            for an, c1a, c1b, c2a, c2b in arms:
                for kind, vals in (("c-1", (c1a, c1b)), ("c-2", (c2a, c2b))):
                    ar = [x for x in ch["arms"] if x["kind"] == kind and x["name"] == armmap[an]][0]
                    for i in range(2):
                        bch = t10(ar["cells"][i][1])
                        net = (M[i] - B[i]) - (t10(vals[i]) - bch)
                        if net < 100:
                            beats = False
        else:
            notder.append(f"{dec} {tol} {nm}")
        exp_h = "yes" if helps else "no"
        n5c += 1
        atom(2)
        if bm.group(10) != exp_h:
            bad5c.append((dec, tol, nm, "helps", bm.group(10), exp_h))
        if beats is not None and bm.group(11) != ("yes" if beats else "no"):
            bad5c.append((dec, tol, nm, "beats", bm.group(11), "yes" if beats else "no"))
        sm = summary_of(helps, (beats if beats is not None else False))
        if bm.group(12) != sm and not (beats is None and not helps and bm.group(12) == "no context gain"):
            bad5c.append((dec, tol, nm, "summary", bm.group(12), sm))
        if beats is None and helps:
            bad5c.append((dec, tol, nm, "helps yes with beats-chance not derivable", bm.group(12), "?"))
rec("5c", not bad5c, f"{n5c} beside one-liners (MAP-T1, HW-*, SW-*): helps re-derived for all; beats chance re-derived where 'its BEST' is the table's BEST (BEST's chance levels are printed there); SUMMARY re-derived"
    + ("" if not bad5c else f"; {len(bad5c)} differ: {bad5c}"))
say("    beats-chance NOT derivable from the printout (BEST-T1 differs from the table's BEST, its chance levels are not printed; SUMMARY still follows because helps = no): " + (", ".join(notder) if notder else "none"))

# 5d: recap lines and the final SUMMARY
bad5d, n5d = [], 0
recap = [l for l in RUNTXT if "beside (never the summary):" in l and l.strip().startswith(("ENTER", "STOP", "EXIT"))]
for l in recap:
    dec = l.strip().split(" ")[0]
    body = l.split("(never the summary): ")[1]
    for item in body.split(" | "):
        m = re.match(r"^(B1 re-cross|B2 hit-or-ballpark|MAP-T1|HW-[A-Z]'?|SW-[ab]|±0|±1 symmetric|±2) (.+)$", item.strip())
        assert m, item
        nm, sm = m.groups()
        # find the label from the table / beside line
        got = None
        if nm in TOLMAP:
            got = getch(dec, TOLMAP[nm])
            h, hb, b, nets = label_from_table(got)
            exp = summary_of(h, b)
        else:
            exp = None
            for ch in CH:
                if ch["dec"] == dec and ch["tol"] == PRIMARY[dec]:
                    for ln in ch["beside"]:
                        if re.match(rf"^  beside {re.escape(nm)} —", ln):
                            exp = re.search(r": (no context gain|context helps, chance too|context map) \(beside", ln).group(1)
        n5d += 1
        atom()
        if exp != sm:
            bad5d.append((dec, nm, sm, exp))
summ = {}
for i, l in enumerate(RUNTXT):
    m = re.match(r"^- (ENTER|STOP|EXIT): (.+)$", l)
    if m:
        summ[m.group(1)] = m.group(2)
for dec in LIB:
    ch = getch(dec, PRIMARY[dec])
    h, hb, b, nets = label_from_table(ch)
    n5d += 1
    atom()
    if summ[dec] != summary_of(h, b):
        bad5d.append((dec, "THE SUMMARY", summ[dec], summary_of(h, b)))
rec("5d", not bad5d, f"{n5d} recap / THE SUMMARY labels match the per-table / per-line labels recomputed from the printed numbers" + ("" if not bad5d else f"; {len(bad5d)} differ: {bad5d}"))
say()

# =========================================================================================================
say("=" * 110)
say("CHECK 6 - SHUF from controls.tsv.gz 'perm' rows: mean, p95, MAP's percentile; and the MAP (c-2) arm means from the 'draw:*' rows")
P = CT[CT.kind == "perm"].copy()
P["s20"] = P.share_2020.astype(float)
P["s22"] = P.share_2021_22.astype(float)
conv = {
    "A: 100*mean(perm < MAP)": lambda a, x: 100.0 * np.mean(a < x - 1e-12),
    "B: 100*mean(perm <= MAP)": lambda a, x: 100.0 * np.mean(a <= x + 1e-12),
    "C: midrank (A+B)/2": lambda a, x: 50.0 * (np.mean(a < x - 1e-12) + np.mean(a <= x + 1e-12)),
}
p95m = ["linear", "higher", "lower", "nearest", "midpoint"]
conv_ok = {k: 0 for k in conv}
conv_tot = 0
p95_ok = {k: 0 for k in p95m}
bad6, n6 = [], 0
for ch in CH:
    dec, tol = ch["dec"], ch["tol"]
    sub = P[(P.decision == dec) & (P.tolerance == tol) & (P.line == "MAP")]
    if not len(sub):
        continue
    assert len(sub) == 200
    sh = ch["rows"]["SHUF mean"]
    pm = [re.match(r"^([\d.]+)% \(p95 ([\d.]+)%", sh[0]), re.match(r"^([\d.]+)% \(p95 ([\d.]+)%", sh[1])]
    pc = re.search(r"pctile ([\d.]+)", sh[0]).group(1)
    for i, col in enumerate(("s20", "s22")):
        a = sub[col].to_numpy()
        mean = f"{100.0 * a.mean():.1f}"
        n6 += 1
        atom()
        if mean != pm[i].group(1):
            bad6.append((dec, tol, BLOCKS[i], "SHUF mean", pm[i].group(1), mean))
        # p95 convention
        for mth in p95m:
            v = f"{100.0 * np.percentile(a, 95, method=mth):.1f}"
            p95_ok[mth] += int(v == pm[i].group(2))
    # MAP percentile on 2020 (MAP's own 2020 share from groups.tsv)
    g = gmap(dec, tol, "MAP")
    g20 = g[g.set == "2020"]
    mapshare = (g20.close == "True").sum() / len(g20)
    a = sub["s20"].to_numpy()
    conv_tot += 1
    for k, f in conv.items():
        conv_ok[k] += int(f"{f(a, mapshare):.1f}" == pc)
best_conv = max(conv_ok, key=conv_ok.get)
rec("6a", not bad6, f"{n6} SHUF means (2020 and 2021-22, 200 permutations each, every primary and beside full-table tolerance) recomputed from the perm rows" + ("" if not bad6 else f"; differ: {bad6[:4]}"))
say(f"    percentile convention scan over {conv_tot} printed 'MAP at pctile' values: " + "; ".join(f"{k} reproduces {v}" for k, v in conv_ok.items()))
say(f"    p95 convention scan (np.percentile method) over {2 * conv_tot} printed p95 values: " + "; ".join(f"{k} reproduces {v}" for k, v in p95_ok.items()))
rec("6b", conv_ok[best_conv] == conv_tot, f"MAP's 2020 percentile among the 200 permutations: convention '{best_conv}' reproduces {conv_ok[best_conv]}/{conv_tot} printed values")
best_p95 = max(p95_ok, key=p95_ok.get)
rec("6c", p95_ok[best_p95] == 2 * conv_tot, f"p95 of the permuted shares: np.percentile(method='{best_p95}') reproduces {p95_ok[best_p95]}/{2 * conv_tot} printed values")
# 6d: MAP-T1 SHUF means from the MAP-T1 perm rows
bad6d, n6d = [], 0
for ch in CH:
    for ln in ch["beside"]:
        bm = re.match(r"^  beside MAP-T1 — .*?; SHUF ([\d.]+)% / ([\d.]+)%;", ln)
        if bm:
            sub = P[(P.decision == ch["dec"]) & (P.tolerance == ch["tol"]) & (P.line == "MAP-T1")]
            if len(sub):
                for i, col in enumerate(("s20", "s22")):
                    n6d += 1
                    atom()
                    mean = f"{100.0 * sub[col].mean():.1f}"
                    if mean != bm.group(1 + i):
                        bad6d.append((ch["dec"], ch["tol"], BLOCKS[i], bm.group(1 + i), mean))
rec("6d", not bad6d, f"{n6d} MAP-T1 SHUF means recomputed from the MAP-T1 perm rows" + ("" if not bad6d else f"; differ: {bad6d}"))
# 6e: (c-2) MAP means from the draw rows
bad6e, n6e = [], 0
DRAW = {"kprice": "k-price random prices", "shared": "the shared random window", "a_frames": "control (a), frames",
        "a_noframes": "control (a), no frames", "rlevel": "random levels"}
for ch in CH:
    for kind in sorted(set(CT[(CT.decision == ch["dec"]) & (CT.tolerance == ch["tol"]) & (CT.line == "MAP")].kind)):
        if not kind.startswith("draw:"):
            continue
        sub = CT[(CT.decision == ch["dec"]) & (CT.tolerance == ch["tol"]) & (CT.line == "MAP") & (CT.kind == kind)]
        ar = [x for x in ch["arms"] if x["kind"] == "c-2" and x["name"] == DRAW[kind[5:]]]
        if not ar:
            continue
        for i, col in enumerate(("share_2020", "share_2021_22")):
            mean = f"{100.0 * sub[col].astype(float).mean():.1f}"
            n6e += 1
            atom()
            if mean != ar[0]["cells"][i][0]:
                bad6e.append((ch["dec"], ch["tol"], kind, BLOCKS[i], ar[0]["cells"][i][0], mean))
rec("6e", not bad6e, f"{n6e} MAP (c-2) arm means (mean over the 200 control draws' re-searched maps) recomputed from the draw rows" + ("" if not bad6e else f"; differ: {bad6e[:4]}"))
say()

# =========================================================================================================
say("=" * 110)
say("CHECK 7 - the untouched sign check: MAP - BEST sign from groups.tsv's untouched set vs the printed sign (BEST count = printed share x n, recoverable at this resolution; exact BEST from tags at +-0 / bracket)")
bad7, n7 = [], 0
rows7 = []
for ch in CH:
    dec, tol = ch["dec"], ch["tol"]
    s = share_by_set(gmap(dec, tol, "MAP")[lambda x: ~x.set.str.contains("beside")])
    mc, nu = s["untouched"]
    pb = t10(ch["rows"]["BEST"][2]) / 10.0
    bc = int(round(pb * nu / 100.0))
    assert abs(100.0 * bc / nu - pb) < 0.06, (dec, tol, pb, bc, nu)     # the count is uniquely recoverable
    exp = "+" if mc > bc else ("-" if mc < bc else "0")
    pm = re.search(r"MAP − BEST (\S+) \(n (\d+)\)", ch["rows"]["MAP"][2])
    got = {"0": "0", "+": "+", "−": "-", "-": "-"}[pm.group(1)]
    n7 += 1
    atom()
    # tag-exact BEST where possible
    tagnote = ""
    if (dec, tol) in DER and (tol == "pm0" or dec == "ENTER"):
        rows_, lo_m, _ = DER[(dec, tol)]
        bj = LIB[dec].index(ch["best_rule"])
        tb = int(lo_m[blk(rows_) == "untouched"][:, bj].sum())
        tagnote = f" tag-exact BEST count {tb}" + ("" if tb == bc else " (DIFFERS from the count implied by the printed share)")
        if tb != bc:
            bad7.append((dec, tol, "BEST count", bc, tb))
    rows7.append(f"    {dec} {tol}: MAP {mc}/{nu} - BEST {bc}/{nu} -> {exp}; printed {got}; n printed {pm.group(2)}{tagnote}")
    if exp != got or int(pm.group(2)) != nu:
        bad7.append((dec, tol, got, exp))
for r in rows7:
    say(r)
rec("7", not bad7, f"{n7} decision x tolerance untouched signs (MAP - BEST) recounted" + ("" if not bad7 else f"; differ: {bad7}"))
say()

# =========================================================================================================
say("=" * 110)
say("CHECK 8 (extra) - exact McNemar counts and p for MAP vs BEST where BEST is tag-exact (ENTER bracket, STOP/EXIT +-0) and where derived (+-1c): discordant counts and the exact two-sided binomial p")


def mcn_p(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


bad8, n8 = [], 0
for ch in CH:
    dec, tol = ch["dec"], ch["tol"]
    if (dec, tol) not in DER:
        continue
    rows_, lo_m, up_m = DER[(dec, tol)]
    bj = LIB[dec].index(ch["best_rule"])
    run_rule, run_close, rg = run_assign(dec, tol)
    ci = {e: i for i, e in enumerate(rows_.eid)}
    bl = blk(rows_)
    pcell = ch["rows"]["MAP − BEST (paired)"]
    for i, b in enumerate(BLOCKS[:2]):
        bcount = ccount = 0
        for e in rows_.eid[bl == b]:
            m_ = run_close[e]
            bs_ = bool(lo_m[ci[e], bj])
            bcount += int(m_ and not bs_)
            ccount += int(bs_ and not m_)
        mm = re.search(r"McNemar (\d+) / (\d+) \(p ([\d.]+)\)", pcell[i])
        n8 += 1
        atom()
        p_ = f"{mcn_p(bcount, ccount):.3f}"
        if (str(bcount), str(ccount), p_) != mm.groups():
            if lo_m.sum() != up_m.sum() and (tol != "pm0"):
                pass
            bad8.append((dec, tol, b, mm.groups(), (bcount, ccount, p_)))
        # paired difference point estimate
        d_prt = re.match(r"^([+-][\d.]+) \[", pcell[i]).group(1)
        n_b = int((bl == b).sum())
        mine_d = f"{(100.0 * (bcount - ccount) / n_b):+.1f}"
        n8 += 1
        atom()
        if mine_d != d_prt:
            bad8.append((dec, tol, b, "paired diff", d_prt, mine_d))
rec("8", not bad8, f"{n8} McNemar counts / exact p / paired point differences recounted for every full table where BEST is tag-derived" + ("" if not bad8 else f"; differ: {bad8[:6]}"))
say()

# =========================================================================================================
say("=" * 110)
say("CHECK S (self-test: do the recount's own comparisons have teeth?  each mutated input MUST be flagged)")
# S1: shift EXIT pm1c C-X2 T1 to the next larger defined 2020 value -> the assignment of the chosen map must disagree somewhere
c20 = CX[(CX.decision == "EXIT") & (CX.block == "2020") & (CX.set == "scorable")]
vals = np.sort(np.array([float(v) for v in c20["C-X2"]]))
t1 = pin_f("ctx_const_EXIT_C-X2_T1")
nxt = vals[vals > t1][0]
saved = PINS["ctx_const_EXIT_C-X2_T1"]
PINS["ctx_const_EXIT_C-X2_T1"] = repr(float(nxt))
dis = 0
gdf = gmap("EXIT", "pm1c", "MAP")
descs = {int(r.group): r.group_desc for r in gdf[["group", "group_desc"]].drop_duplicates().itertuples()}
for r in gdf.itertuples():
    hit = []
    for gi, ds in descs.items():
        if all(tok_eval("EXIT", tk, *ctx_vals("EXIT", r.eid, "scorable", tk.split(" ")[0])) for tk in tokens_of(ds)):
            hit.append(gi)
    dis += int(hit != [int(r.group)])
PINS["ctx_const_EXIT_C-X2_T1"] = saved
rec("S1", dis > 0, f"moving one pinned cut by one rank flips {dis} EXIT pm1c assignments (the assignment check would flag it)")
# S2: flip one STOP pm0 `close` in a copy -> the bucket comparison must flag exactly that row
g = gmap("STOP", "pm0", "MAP").copy()
g.loc[g.index[0], "close"] = "False" if g.iloc[0].close == "True" else "True"
flag = sum((TI["STOP"].loc[r.eid, r.rule + "_bucket"] == "EXPLAINS") != (r.close == "True") for r in g.itertuples())
rec("S2", flag == 1, f"flipping one STOP pm0 `close` makes the bucket comparison flag {flag} row (must be exactly 1)")
# S3: the label function must flip when MAP is lifted 10.0 above BEST and SHUF in the ENTER bracket table
tbl = {"rows": {"MAP": ["56.4% [..] (n 88)", "53.3% [..] (n 60)", ""], "BEST": ["36.4%", "43.3%", ""], "SHUF mean": ["41.8% (p95 1)", "41.5% (p95 1)"]},
       "arms": [{"kind": "c-1", "name": "x", "cells": [("20.9", "21.0", "+0"), ("31.1", "31.3", "+0")]}]}
h_, hb_, b_, _ = label_from_table(tbl)
rec("S3", h_ and b_ and summary_of(h_, b_) == "context map", f"a synthetic table with MAP >= BEST+10.0 and >= SHUF+10.0 on both blocks and net gains >= 10.0 reads `context map` (got helps={h_}, beats={b_})")
say()

# =========================================================================================================
run_res = [(c, o) for c, o in RES if not c.startswith("S")]
self_res = [(c, o) for c, o in RES if c.startswith("S")]
nchk = len(run_res)
k = sum(1 for _, ok_ in run_res if ok_)
j = nchk - k
say("=" * 110)
say(f"## RESULT: {nchk} checks, {k} MATCH, {j} MISMATCH; (+{len(self_res)} recount self-tests, {sum(1 for _, o in self_res if o)} behaved as required); {ATOMS[0]} atomic comparisons; "
    "widened-tolerance CLOSE (+-1c/+-1/+-2) is derived from the tag files with a lower/upper UNRESOLVED-upgrade band (parts of 1b/1c/3b/4/8); context VALUES are taken from contexts.tsv, not re-derived from bars")
(VER / "recount_run.txt").write_text("\n".join(LINES) + "\n")
