#!/usr/bin/env python3
"""#705 v2 comparison - INDEPENDENT recount of v2_compare.txt.

Written from the registration alone (docs/analysis/cb_2017_21_rerun_v2_prereg_2026-10-25.md section 7:
rules R1-R6 and the sources table). It does NOT import or read v2_compare.py. It reads each line's OLD and NEW
source file/key (the paths the printout names after 'source:'), recomputes old value, new value and the
HOLDS / CHANGES verdict, then reads v2_compare.txt ONLY to compare its printed old / new / verdict strings to mine.

Read-only: no stage of the breakout re-run is run; nothing is written except verify/recount_compare.txt.
Run:  python3 verify/recount_compare.py        (writes verify/recount_compare.txt and echoes it)
"""
import csv
import gzip
import hashlib
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROBES = "/Users/alvinfung/apollo_the_wise/scripts/probes"
DATA = "/Users/alvinfung/apollo_data"
PRINTOUT = os.environ.get("RECOUNT_PRINTOUT", os.path.join(HERE, "..", "v2_compare.txt"))
OUT_TXT = os.environ.get("RECOUNT_OUT", os.path.join(HERE, "recount_compare.txt"))

OUT = io.StringIO()


def say(s=""):
    OUT.write(s + "\n")
    print(s)


# ---------------------------------------------------------------- sources (old, new)
SRC = {
    "N1": (f"{PROBES}/_702_breakout_definition_1022/03_numbers.json",
           f"{PROBES}/_702_breakout_definition_1022/rerun_v2_1025/03_numbers.json"),
    "R1MD": (f"{PROBES}/_702_breakout_definition_1022/03_report.md",
             f"{PROBES}/_702_breakout_definition_1022/rerun_v2_1025/03_report.md"),
    "N2": (f"{PROBES}/_702_winner_recall_1022/03_numbers.json",
           f"{PROBES}/_702_winner_recall_1022/rerun_v2_1025/03_numbers.json"),
    "H3": (f"{PROBES}/_702_entry_stop_retry_1022/03_headline.json",
           f"{PROBES}/_702_entry_stop_retry_1022/rerun_v2_1025/03_headline.json"),
    "H4": (f"{PROBES}/_702_trail_variants_1023/03_headline.json",
           f"{PROBES}/_702_trail_variants_1023/rerun_v2_1025/03_headline.json"),
    "P5": (f"{PROBES}/_cb_backtest/out/p5_report_pre.tsv",
           f"{PROBES}/_cb_backtest/out/v2_1025/p5_report_pre.tsv"),
    "H60": (f"{DATA}/cb702_pre/out/h60_verdict_pre.json",
            f"{DATA}/cb702_pre_v2/out/h60_verdict_pre.json"),
    "EXIT": (f"{DATA}/cb702_pre/out/exitpb_verdict_pre.json",
             f"{DATA}/cb702_pre_v2/out/exitpb_verdict_pre.json"),
}
# bonus cross-check tables (not the section-7 sources): the fills tables behind lines 1.1 / 1.2
FILLS = (f"{DATA}/cb702_pre/out/bdef_fills_2017-21.tsv.gz",
         f"{DATA}/cb702_pre_v2/out/rerun_v2_1025/breakout_definition/bdef_fills_2017-21.tsv.gz")

SHA_SEEN = {}  # path -> sha256 of the bytes this script read


def read_bytes(path):
    with open(path, "rb") as fh:
        b = fh.read()
    SHA_SEEN[path] = hashlib.sha256(b).hexdigest()
    return b


def load_json(path):
    return json.loads(read_bytes(path).decode("utf-8"))


def load_text(path):
    return read_bytes(path).decode("utf-8")


def load_tsv(path):
    return list(csv.DictReader(io.StringIO(load_text(path)), delimiter="\t"))


J = {}  # (name, 0/1) -> parsed
for name, (o, n) in SRC.items():
    if name in ("P5",):
        J[(name, 0)], J[(name, 1)] = load_tsv(o), load_tsv(n)
    elif name == "R1MD":
        J[(name, 0)], J[(name, 1)] = load_text(o), load_text(n)
    else:
        J[(name, 0)], J[(name, 1)] = load_json(o), load_json(n)

OLD, NEW = 0, 1
Q = "ADR decile x 63-session return quintile|"

# ---------------------------------------------------------------- the registered rules
def cls(lo, hi):
    """R1 class: ABOVE (lower end > 0), SPANS (lo <= 0 <= hi), BELOW (upper end < 0)."""
    if lo > 0:
        return "ABOVE"
    if hi < 0:
        return "BELOW"
    return "SPANS"


def r1_fmt(d, lo, hi, n):
    return f"{d:+.4f} ({lo:+.4f} .. {hi:+.4f}) {cls(lo, hi)}, n {n:,}"


def r1_verdict(o, n):
    """o, n = (d, lo, hi). HOLDS = same class; names 'moved' (same class, new point outside old interval)."""
    co, cn = cls(o[1], o[2]), cls(n[1], n[2])
    if co != cn:
        return "CHANGES", f"class {co} -> {cn}"
    moved = not (o[1] <= n[0] <= o[2])
    return "HOLDS", f"class {co} -> {cn}" + (" (moved: new point outside the old interval)" if moved else "")


def r3_tol(old_pct):
    """R3 tolerance (points) = larger of 2 and the smaller of 5 and half the old share."""
    return max(2.0, min(5.0, old_pct / 2.0))


def share_fmt(c, n):
    return f"{c:,} of {n:,} = {100.0 * c / n:.2f}%"


def r3_verdict(oc, on, nc, nn):
    po, pn = 100.0 * oc / on, 100.0 * nc / nn
    t = r3_tol(po)
    ok = abs(pn - po) <= t
    return ("HOLDS" if ok else "CHANGES"), f"{po:.2f}% -> {pn:.2f}% (|diff| {abs(pn - po):.2f} vs tolerance +-{t:.2f} points)"


def r5_verdict(o, n, dp=2):
    """R5: same direction and within 25% = HOLDS; same direction but further = moved (counts as HOLDS); flip = CHANGES."""
    if (o > 0) != (n > 0):
        return "CHANGES", "direction flips"
    ch = (n - o) / abs(o)
    if abs(ch) <= 0.25:
        return "HOLDS", f"{o:+.{dp}f} -> {n:+.{dp}f} ({100 * ch:+.1f}%; band +-25%)"
    return "HOLDS", f"MOVED {o:+.{dp}f} -> {n:+.{dp}f} ({100 * ch:+.1f}%; beyond +-25%, counts as holds)"


# ---------------------------------------------------------------- collected results
RES = {}      # id -> dict(role, rule, old, new, verdict, reason)
ORDER = []


def rec(lid, role, rule, old_s, new_s, verdict, reason, title=""):
    RES[lid] = dict(role=role, rule=rule, old=old_s, new=new_s, verdict=verdict, reason=reason, title=title)
    ORDER.append(lid)


# ---------------------------------------------------------------- registered OLD values (typed from section 7 of the prereg)
REG = []  # (line, label, actual, registered, dp)


def reg(line, label, actual, registered, dp):
    REG.append((line, label, actual, registered, dp))


# ================================================================ READ 1
md_o, md_n = J[("R1MD", OLD)], J[("R1MD", NEW)]


def md_section_a(md):
    """Row of table A for 2017-21: returns (median_str, atabove_count, n_fills)."""
    lines = md.splitlines()
    hi = next(i for i, l in enumerate(lines) if "fill distance below the base high" in l)
    header = [c.strip() for c in lines[hi].strip().strip("|").split("|")]
    row = [c.strip() for c in lines[hi + 2].strip().strip("|").split("|")]
    assert row[0] == "2017-21", row
    i_med = next(i for i, h in enumerate(header) if "fill distance below the base high" in h)
    i_at = next(i for i, h in enumerate(header) if "fill already at/above the base high" in h)
    n = int(re.search(r"n = ([\d,]+)", row[1]).group(1).replace(",", ""))
    cnt = int(re.match(r"([\d,]+) \(", row[i_at]).group(1).replace(",", ""))
    return float(row[i_med]), cnt, n


m_o, c_o, n_o = md_section_a(md_o)
m_n, c_n, n_n = md_section_a(md_n)

# 1.1 R5
v, why = r5_verdict(m_o, m_n)
rec("1.1", "deciding", "R5", f"{m_o:+.2f}", f"{m_n:+.2f}", v, why, "fill median distance below the base high (ADR20)")
reg("1.1", "median 1.16", m_o, 1.16, 2)
# 1.2 R3
v, why = r3_verdict(c_o, n_o, c_n, n_n)
rec("1.2", "deciding", "R3", share_fmt(c_o, n_o), share_fmt(c_n, n_n), v, why, "share of fills at/above the base high")
reg("1.2", "1,098 count", c_o, 1098, 0); reg("1.2", "n 13,363", n_o, 13363, 0)

# 1.3 / 1.4 / 1.5
a_o, a_n = J[("N1", OLD)]["A_sc_2017-21"], J[("N1", NEW)]["A_sc_2017-21"]
v, why = r3_verdict(a_o["by60"], a_o["n"], a_n["by60"], a_n["n"])
rec("1.3", "deciding", "R3", share_fmt(a_o["by60"], a_o["n"]), share_fmt(a_n["by60"], a_n["n"]), v, why, "share that close above the base high within 60 sessions")
reg("1.3", "by60 10,214", a_o["by60"], 10214, 0)
keys14 = ("by0", "by5", "by20", "never")
ro = tuple(a_o[k] for k in keys14)
rn = tuple(a_n[k] for k in keys14)
rem14 = " / ".join(f"{a} -> {b} (x{b / a:.3f})" for a, b in zip(ro, rn))
rec("1.4", "beside", "R6", str(ro), str(rn), "REPORTED", rem14, "first close above it: fill day / by 5 / by 20 / never")
reg("1.4", "1,548/4,989/8,110/3,149", ro, (1548, 4989, 8110, 3149), 0)
b_o, b_n = J[("N1", OLD)]["A_big_2017-21_5"], J[("N1", NEW)]["A_big_2017-21_5"]
v, why = r3_verdict(b_o["before"], b_o["n"], b_n["before"], b_n["n"])
rec("1.5", "beside", "R3", share_fmt(b_o["before"], b_o["n"]), share_fmt(b_n["before"], b_n["n"]), v, why, "+5 ADR movers that cleared the base high first")
reg("1.5", "5,675 of 5,756", (b_o["before"], b_o["n"]), (5675, 5756), 0)


def r1_from(blob, key, sub):
    e = blob[key][Q + sub]
    return e["d"], e["lo"], e["hi"], e["n"]


K_R1 = "2017-21|R1 base-high close — entry at that close"
K_R2 = "2017-21|R2 expansion breakout — entry at that close"
for lid, role, key, sub, title, regv in (
        ("1.6", "deciding", K_R1, "share >= 5 ADR within 60", "R1: share reaching +5 ADR within 60, entries minus control",
         (0.0109, -0.0069, 0.0292, 9281)),
        ("1.7", "beside", K_R1, "mean close return +60 (ADR)", "R1 mean close return at +60 sessions (ADR), difference",
         (0.1749, 0.0013, 0.3904, 9191)),
        ("1.8", "beside", K_R2, "share >= 5 ADR within 60", "R2 expansion-day breakouts: +5 ADR share, difference",
         (0.0310, 0.0055, 0.0554, 1582))):
    o = r1_from(J[("N1", OLD)], key, sub)
    n = r1_from(J[("N1", NEW)], key, sub)
    v, why = r1_verdict(o[:3], n[:3])
    rec(lid, role, "R1", r1_fmt(*o), r1_fmt(*n), v, why, title)
    reg(lid, "d/lo/hi/n", o, regv, 4)

# ================================================================ READ 2
f_o, f_n = J[("N2", OLD)]["2017-21/x200/funnel"], J[("N2", NEW)]["2017-21/x200/funnel"]
comp_o, comp_n = J[("N2", OLD)]["2017-21/x200/composition"], J[("N2", NEW)]["2017-21/x200/composition"]
ok20 = comp_n["n"] == 1181
rec("2.0", "check", "R6", str(comp_o["n"]), str(comp_n["n"]), "PASSES" if ok20 else "FAILS",
    f"big winners {comp_n['n']} (must be 1,181)", "big winners kept")
reg("2.0", "994", comp_o["n"], 994, 0)
F_COVER = "… whose base nights our watch covers"
F_WATCH = "… WATCHED (a watch row on some base night)"
F_TRIG = "… TRIGGERED (a tl ORH5 fill, E in the catch window)"
F_S50 = "… triggered and STILL IN at s50 (half the gain made)"
F_KEPT = "… triggered and KEPT >= half of the episode's gain"
rec("2.1", "beside", "R6", str((f_o[F_COVER][0],)), str((f_n[F_COVER][0],)), "REPORTED",
    f"{f_o[F_COVER][0]} -> {f_n[F_COVER][0]} (x{f_n[F_COVER][0] / f_o[F_COVER][0]:.3f})", "measurable breakouts whose base nights are covered")
reg("2.1", "481", f_o[F_COVER][0], 481, 0)
for lid, key, title, regc in (("2.2", F_WATCH, "of those, WATCHED", 240), ("2.3", F_TRIG, "TRIGGERED", 237),
                              ("2.4", F_S50, "still in the trade when the stock had made half its gain", 25),
                              ("2.5", F_KEPT, "kept at least half of the episode's gain", 3)):
    (oc, on), (nc, nn) = f_o[key], f_n[key]
    v, why = r3_verdict(oc, on, nc, nn)
    rec(lid, "deciding", "R3", share_fmt(oc, on), share_fmt(nc, nn), v, why, title)
    reg(lid, "count of 481", (oc, on), (regc, 481), 0)

# ================================================================ READ 3
H3o, H3n = J[("H3", OLD)]["2017-21"], J[("H3", NEW)]["2017-21"]


def best_cell(H, prefix, field="still_in_s50"):
    cells = {k: H[k][field] / H[k]["n"] for k in H if k.startswith(prefix)}
    return max(cells, key=cells.get), cells


# 3.1: R4 over every H3 win_* cell + R3 on the best cell's share (S2_T2)
bo, co_ = best_cell(H3o, "win_")
bn, cn_ = best_cell(H3n, "win_")
assert len(co_) == 12 and len(cn_) == 12
cell31 = "win_S2_T2"
tie31 = abs(100 * cn_[bo] - 100 * cn_[bn]) <= 2.0
r4ok = (bo == bn) or tie31
oc, on = H3o[bo]["still_in_s50"], H3o[bo]["n"]
nc, nn = H3n[bo]["still_in_s50"], H3n[bo]["n"]
v3, why3 = r3_verdict(oc, on, nc, nn)
verdict31 = "HOLDS" if (r4ok and v3 == "HOLDS") else "CHANGES"
nm = lambda c: c.replace("win_", "")
rec("3.1", "deciding", "R4+R3",
    f"{nm(bo)} {oc} of {on} = {100 * oc / on:.1f}%; best {nm(bo)} {100 * co_[bo]:.1f}%",
    f"{nm(bn)} {H3n[bn]['still_in_s50']} of {H3n[bn]['n']} = {100 * cn_[bn]:.1f}%; best {nm(bn)} {100 * cn_[bn]:.1f}%",
    verdict31,
    (f"best cell {nm(bo)} is still the best" if bo == bn else (f"best cell tie within 2 points ({nm(bo)} vs {nm(bn)})" if tie31 else f"best cell moved {nm(bo)} -> {nm(bn)}"))
    + "; " + why3,
    "best-holding cell on the doublers: S2 with two retries, still in at half")
reg("3.1", "213 of 481 (44.3%)", (oc, on), (213, 481), 0)
# 3.2 beside
c32 = "win_S2_T2"
for lid, field, title in (("3.2", "kept_half", "the same cell: kept half"), ("3.2b", "kept_quarter", "the same cell: kept a quarter")):
    oc, on = H3o[c32][field], H3o[c32]["n"]
    nc, nn = H3n[c32][field], H3n[c32]["n"]
    v, why = r3_verdict(oc, on, nc, nn)
    rec(lid, "beside", "R3", share_fmt(oc, on), share_fmt(nc, nn), v, why, title)
reg("3.2", "kept half 8, quarter 121", (H3o[c32]["kept_half"], H3o[c32]["kept_quarter"]), (8, 121), 0)
ro_, rn_ = H3o[c32]["retries_mean"], H3n[c32]["retries_mean"]
rec("3.2c", "beside", "R6", str((round(ro_, 6),)), str((round(rn_, 6),)), "REPORTED", f"{ro_:.6f} -> {rn_:.6f} (x{rn_ / ro_:.3f})", "the same cell: retries used, mean")
reg("3.2c", "0.657", ro_, 0.657, 3)


def dd(Hblob, key, field):
    e = Hblob[key][field]
    return e["diff"], e["lo"], e["hi"], e["n"]


for lid, role, key, field, title, regv in (
        ("3.3", "deciding", "all_S2_T0", "diff_r_per_base", "R1, S2, no retry: mean R per base, entries minus control", (0.0054, -0.0355, 0.0496, 9239)),
        ("3.4", "deciding", "all_S2_T0", "diff_any5", "R1, S2, no retry: bases with a >= 5R trade per 100, entries minus control", (0.478, 0.138, 0.857, 9239)),
        ("3.5", "beside", "all_S2_T2", "diff_r_per_base", "R1, S2, two retries: mean R per base difference", (0.0712, 0.0156, 0.1356, 9239)),
        ("3.6", "beside", "all_S2_T2", "diff_any5", "R1, S2, two retries: >= 5R bases per 100", (1.383, 0.995, 1.829, 9239))):
    o, n = dd(H3o, key, field), dd(H3n, key, field)
    v, why = r1_verdict(o[:3], n[:3])
    rec(lid, role, "R1", r1_fmt(*o), r1_fmt(*n), v, why, title)
    reg(lid, "d/lo/hi/n", o, regv, 4 if lid in ("3.3", "3.5") else 3)
# 3.4 side check: registered 1.905 vs 1.426
reg("3.4", "any5 1.905 / ctl 1.426", (H3o["all_S2_T0"]["any5"], H3o["all_S2_T0"]["ctl_any5"]), (1.905, 1.426), 3)
# 3.7 beside: race5_hit, entries vs control, R3 on the difference (+-2)
ho, hn = H3o["all_S2_T0"], H3n["all_S2_T0"]
dpo = 100 * (ho["race5_hit"] - ho["ctl_race5_hit"])
dpn = 100 * (hn["race5_hit"] - hn["ctl_race5_hit"])
rec("3.7", "beside", "R3d",
    f"{100 * ho['race5_hit']:.2f}% vs {100 * ho['ctl_race5_hit']:.2f}% (difference {dpo:+.2f} points)",
    f"{100 * hn['race5_hit']:.2f}% vs {100 * hn['ctl_race5_hit']:.2f}% (difference {dpn:+.2f} points)",
    "HOLDS" if abs(dpn - dpo) <= 2.0 else "CHANGES", f"difference {dpo:+.2f} -> {dpn:+.2f} points (tolerance +-2.00)",
    "R1, S2, no retry: share reaching +5R before the stop, entries vs control")
reg("3.7", "17.82% vs 18.71%", (100 * ho["race5_hit"], 100 * ho["ctl_race5_hit"]), (17.82, 18.71), 2)

# ================================================================ READ 4
H4o, H4n = J[("H4", OLD)]["2017-21"], J[("H4", NEW)]["2017-21"]


def num_equal(a, b, tol=1e-9, path=""):
    """recursive: returns (n_compared, [problems]) over keys common to both."""
    if isinstance(a, dict) and isinstance(b, dict):
        n, bad = 0, []
        for k in sorted(set(a) & set(b)):
            nn, bb = num_equal(a[k], b[k], tol, f"{path}/{k}")
            n += nn
            bad += bb
        return n, bad
    if isinstance(a, list) and isinstance(b, list):
        n, bad = 0, []
        if len(a) != len(b):
            return 0, [f"{path}: list length {len(a)} vs {len(b)}"]
        for i, (x, y) in enumerate(zip(a, b)):
            nn, bb = num_equal(x, y, tol, f"{path}[{i}]")
            n += nn
            bad += bb
        return n, bad
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return 1, ([] if abs(a - b) <= tol * max(1.0, abs(a), abs(b)) else [f"{path}: {a} vs {b}"])
    return 1, ([] if a == b else [f"{path}: {a!r} vs {b!r}"])


# H4's R1_T0 and H3's all_S2_T0 name the same quantities differently; the pairing below was fixed by reading
# both key lists and matching on meaning + value (n, trades/week, R per trade and control, the three differences
# with their intervals, >=5R and >=10R per 100, win rate, the account blocks).
R1_KEYMAP = {"n": "n", "tpw": "trades_per_week", "r_trade": "r_per_trade", "r_trade_ctl": "ctl_r_per_trade",
             "diff": "diff_r_per_base", "any5": "any5", "any5_ctl": "ctl_any5", "any5_diff": "diff_any5",
             "any10": "ge10_per100_trades", "any10_diff": "diff_any10", "win": "win_per_trade",
             "acc": "account", "acc_ctl": "account_control"}


def pp_parity(H4, H3):
    n1, b1 = num_equal(H4["A20_X1_P1"]["win_T2"], H3["win_S2_T2"], 1e-9, "win")
    a, b = H4["A20_X1_P1"]["R1_T0"], H3["all_S2_T0"]
    n2, b2 = 0, []
    for k4, k3 in R1_KEYMAP.items():
        nn, bb = num_equal(a[k4], b[k3], 1e-9, f"R1:{k4}~{k3}")
        n2 += nn
        b2 += bb
    return n1, n2, b1 + b2


p_o, p_n = pp_parity(H4o, H3o), pp_parity(H4n, H3n)
rec("4.0", "check", "must pass",
    "every value equal" if not p_o[2] else f"{len(p_o[2])} differ",
    "every value equal" if not p_n[2] else f"{len(p_n[2])} differ",
    "PASSES" if not p_o[2] and not p_n[2] else "FAILS",
    f"values compared at 1e-9: old {p_o[0]}+{p_o[1]}, new {p_n[0]}+{p_n[1]} (win cell + R1 cell); problems old {p_o[2][:2]} new {p_n[2][:2]}",
    "pp cell (A20_X1_P1) equals read 3's S2 two-retry cell and S2 no-retry R1")

# 4.1 R4 over all 16 cells + R3
bo4, co4 = best_cell({k: H4o[k]["win_T2"] for k in H4o}, "")
bn4, cn4 = best_cell({k: H4n[k]["win_T2"] for k in H4n}, "")
assert len(co4) == 16 and len(cn4) == 16
tie41 = abs(100 * cn4[bo4] - 100 * cn4[bn4]) <= 2.0
oc, on = H4o[bo4]["win_T2"]["still_in_s50"], H4o[bo4]["win_T2"]["n"]
nc, nn = H4n[bo4]["win_T2"]["still_in_s50"], H4n[bo4]["win_T2"]["n"]
v41, why41 = r3_verdict(oc, on, nc, nn)
verdict41 = "HOLDS" if ((bo4 == bn4 or tie41) and v41 == "HOLDS") else "CHANGES"
rec("4.1", "deciding", "R4+R3",
    f"{bo4} {oc} of {on} = {100 * oc / on:.1f}%; best {bo4} {100 * co4[bo4]:.1f}%",
    f"{bn4} {H4n[bn4]['win_T2']['still_in_s50']} of {H4n[bn4]['win_T2']['n']} = {100 * cn4[bn4]:.1f}%; best {bn4} {100 * cn4[bn4]:.1f}%",
    verdict41,
    (f"best cell {bo4} is still the best" if bo4 == bn4 else (f"best cell tie within 2 points ({bo4} vs {bn4})" if tie41 else f"best cell moved {bo4} -> {bn4}")) + "; " + why41,
    "best-holding cell on the doublers: A20_X3_P0, still in at half")
reg("4.1", "256 of 481 (53.2%)", (oc, on), (256, 481), 0)
# 4.2, 4.2b, 4.2c
X, PP = "A20_X3_P0", "A20_X1_P1"
for lid, cell, title in (("4.2", X, "kept at least half: A20_X3_P0"), ("4.2b", PP, "kept at least half: pp (A20_X1_P1)")):
    oc, on = H4o[cell]["win_T2"]["kept_half"], H4o[cell]["win_T2"]["n"]
    nc, nn = H4n[cell]["win_T2"]["kept_half"], H4n[cell]["win_T2"]["n"]
    v, why = r3_verdict(oc, on, nc, nn)
    rec(lid, "deciding", "R3", share_fmt(oc, on), share_fmt(nc, nn), v, why, title)
reg("4.2", "92 (19.1%) vs 8 (1.7%)", (H4o[X]["win_T2"]["kept_half"], H4o[PP]["win_T2"]["kept_half"]), (92, 8), 0)
go = H4o[X]["win_T2"]["kept_half"] - H4o[PP]["win_T2"]["kept_half"]
gn = H4n[X]["win_T2"]["kept_half"] - H4n[PP]["win_T2"]["kept_half"]
sgo = H4o[X]["win_T2"]["kept_half"] / H4o[X]["win_T2"]["n"] - H4o[PP]["win_T2"]["kept_half"] / H4o[PP]["win_T2"]["n"]
sgn = H4n[X]["win_T2"]["kept_half"] / H4n[X]["win_T2"]["n"] - H4n[PP]["win_T2"]["kept_half"] / H4n[PP]["win_T2"]["n"]
same_sign = (go > 0) == (gn > 0) and (sgo > 0) == (sgn > 0)
rec("4.2c", "deciding", "SIGN", str(go), str(gn), "HOLDS" if same_sign else "CHANGES",
    f"count gap {go:+d} -> {gn:+d}; share gap {100 * sgo:+.2f} -> {100 * sgn:+.2f} points", "sign of the gap: kept half A20_X3_P0 minus pp")
# 4.3 a-d R5 beside
for lid, cell, fld, idx, title in (
        ("4.3", X, "kept_share_q", 1, "median share of the gain kept, A20_X3_P0"),
        ("4.3b", PP, "kept_share_q", 1, "median share of the gain kept, pp"),
        ("4.3c", X, "held_chain_q", 1, "median sessions held, A20_X3_P0"),
        ("4.3d", PP, "held_chain_q", 1, "median sessions held, pp")):
    o, n = H4o[cell]["win_T2"][fld][idx], H4n[cell]["win_T2"][fld][idx]
    d5 = 5 if fld == "kept_share_q" else 0
    v, why = r5_verdict(o, n, d5)
    rec(lid, "beside", "R5", f"{o:+.{d5}f}", f"{n:+.{d5}f}", v, why, title)
reg("4.3", "0.0863 vs 0.054 / 25 vs 18",
    (H4o[X]["win_T2"]["kept_share_q"][1], H4o[PP]["win_T2"]["kept_share_q"][1], H4o[X]["win_T2"]["held_chain_q"][1], H4o[PP]["win_T2"]["held_chain_q"][1]),
    (0.0863, 0.054, 25, 18), 3)
# 4.4 / 4.5
for lid, role, cell, field, title, regv in (
        ("4.4", "deciding", PP, "diff", "R1, no retry: mean R per base, entries minus control - pp", (0.0054, -0.0355, 0.0496, 9239)),
        ("4.4b", "deciding", X, "diff", "R1, no retry: mean R per base, entries minus control - A20_X3_P0", (0.0095, -0.0505, 0.0762, 9239)),
        ("4.5", "beside", PP, "any5_diff", "R1, no retry: >= 5R bases per 100, difference - pp", (0.478, 0.138, 0.857, 9239)),
        ("4.5b", "beside", X, "any5_diff", "R1, no retry: >= 5R bases per 100, difference - A20_X3_P0", (0.600, 0.224, 1.033, 9239))):
    o, n = dd(H4o[cell], "R1_T0", field), dd(H4n[cell], "R1_T0", field)
    v, why = r1_verdict(o[:3], n[:3])
    rec(lid, role, "R1", r1_fmt(*o), r1_fmt(*n), v, why, title)
    reg(lid, "d/lo/hi/n", o, regv, 4 if lid in ("4.4", "4.4b") else 3)

# ================================================================ STAGES
def p5_row(rows, window, cell):
    m = [r for r in rows if r["key"] == "spec" and r["K"] == "tl" and r["arm"] == "c3_p33_t20_cut3"
         and r["slice"] == "all" and r["window"] == window and r["cell"] == cell]
    assert len(m) == 1, (window, cell, len(m))
    r = m[0]
    return dict(n=int(r["n"]), mean=float(r["mean_r"]), lo=float(r["ci_lo"]), hi=float(r["ci_hi"]), verdict=r["verdict"])


def stage_str(r, with_cls=True, verdict_word=True):
    return f"{r['mean']:+.4f} ({r['lo']:+.4f} .. {r['hi']:+.4f}) {cls(r['lo'], r['hi'])}, n {r['n']:,}" + (f", {r['verdict']}" if verdict_word else "")


P5o, P5n = J[("P5", OLD)], J[("P5", NEW)]
# S1 R2+R1
o, n = p5_row(P5o, "era", "C1"), p5_row(P5n, "era", "C1")
ok = o["verdict"] == n["verdict"] and cls(o["lo"], o["hi"]) == cls(n["lo"], n["hi"])
rec("S1", "stage", "R2+R1", stage_str(o), stage_str(n), "HOLDS" if ok else "CHANGES",
    f"'{o['verdict']}' -> '{n['verdict']}'; class {cls(o['lo'], o['hi'])} -> {cls(n['lo'], n['hi'])}; n {o['n']} -> {n['n']}",
    "pre-read, whole era, C1 (tl, his exit with the staller cut)")
reg("S1", "n 180, +0.277 (-0.24 .. +0.99) CAN'T TELL", (o["n"], o["mean"], o["lo"], o["hi"], o["verdict"]), (180, 0.277, -0.24, 0.99, "CAN'T TELL"), 2)
# S2 R1
o, n = p5_row(P5o, "era", "C0"), p5_row(P5n, "era", "C0")
ok = cls(o["lo"], o["hi"]) == cls(n["lo"], n["hi"])
rec("S2", "stage", "R1", stage_str(o), stage_str(n), "HOLDS" if ok else "CHANGES",
    f"class {cls(o['lo'], o['hi'])} -> {cls(n['lo'], n['hi'])}", "pre-read, whole era, C0 baseline")
reg("S2", "+0.024 (-0.12 .. +0.17) n 13,363", (o["n"], o["mean"], o["lo"], o["hi"]), (13363, 0.024, -0.12, 0.17), 2)
# S3 R2
o, n = p5_row(P5o, "era", "C4"), p5_row(P5n, "era", "C4")
rec("S3", "stage", "R2", o["verdict"], n["verdict"], "HOLDS" if o["verdict"] == n["verdict"] else "CHANGES",
    f"'{o['verdict']}' -> '{n['verdict']}'", "pre-read, whole era, C4")
reg("S3", "FAIL n 1,017 -0.202 (-0.34 .. -0.05)", (o["verdict"], o["n"], o["mean"], o["lo"], o["hi"]), ("FAIL", 1017, -0.202, -0.34, -0.05), 2)
# S4 R2
o, n = p5_row(P5o, "2020-21", "C1"), p5_row(P5n, "2020-21", "C1")
rec("S4", "stage", "R2", o["verdict"], n["verdict"], "HOLDS" if o["verdict"] == n["verdict"] else "CHANGES",
    f"'{o['verdict']}' -> '{n['verdict']}'", "pre-read, 2020-21 alone, C1")
reg("S4", "CAN'T TELL n 72", (o["verdict"], o["n"]), ("CAN'T TELL", 72), 0)
# S5 R2 (c1_verdict | pair_verdict_c1)
wo, wn = J[("H60", OLD)]["windows"]["pre"], J[("H60", NEW)]["windows"]["pre"]
so, sn = f"{wo['c1_verdict']} | {wo['pair_verdict_c1']}", f"{wn['c1_verdict']} | {wn['pair_verdict_c1']}"
rec("S5", "stage", "R2", so, sn, "HOLDS" if (wo["c1_verdict"], wo["pair_verdict_c1"]) == (wn["c1_verdict"], wn["pair_verdict_c1"]) else "CHANGES",
    f"'{so}' -> '{sn}'", "hourly-close read, pre, C1 verdict | paired entry verdict")
reg("S5", "CAN'T TELL n 180 +0.588 (-0.15 .. +1.61); pair can't tell",
    (wo["c1_verdict"], wo["c1_n"], wo["c1_mean_r"], wo["c1_ci"][0], wo["c1_ci"][1], wo["pair_verdict_c1"]),
    ("CAN'T TELL", 180, 0.588, -0.15, 1.61, "can't tell"), 2)
# S6 R2+R1, S7 R2
eo, en = J[("EXIT", OLD)], J[("EXIT", NEW)]
o, n = eo["delta_c1"], en["delta_c1"]
co, cn = cls(o["lo"], o["hi"]), cls(n["lo"], n["hi"])
fs = lambda r, c: f"{r['mean']:+.4f} ({r['lo']:+.4f} .. {r['hi']:+.4f}) {c}, n {r['n']:,}, {r['verdict']}"
rec("S6", "stage", "R2+R1", fs(o, co), fs(n, cn), "HOLDS" if (o["verdict"] == n["verdict"] and co == cn) else "CHANGES",
    f"'{o['verdict']}' -> '{n['verdict']}'; class {co} -> {cn}; n {o['n']} -> {n['n']}"
    + ("" if o["lo"] <= n["mean"] <= o["hi"] else " (moved)"),
    "exit read, pre, C1: whole-trade breakeven minus pp")
reg("S6", "loss n 180 -0.1221 (-0.19 .. -0.05)", (o["verdict"], o["n"], o["mean"], o["lo"], o["hi"]), ("loss", 180, -0.1221, -0.19, -0.05), 2)
o, n = eo["delta_c0"], en["delta_c0"]
rec("S7", "stage", "R2", o["verdict"], n["verdict"], "HOLDS" if o["verdict"] == n["verdict"] else "CHANGES",
    f"'{o['verdict']}' -> '{n['verdict']}'", "exit read, pre, C0: the same delta")
reg("S7", "can't tell n 13,362 +0.0112 (-0.02 .. +0.04)", (o["verdict"], o["n"], o["mean"], o["lo"], o["hi"]), ("can't tell", 13362, 0.0112, -0.02, 0.04), 2)

# ================================================================ read the printout ONLY to compare strings
PLINES = open(PRINTOUT, encoding="utf-8").read().splitlines()
P = {}  # id -> dict(old,new,verdict,rest)
cur = None
for ln in PLINES:
    m = re.match(r"^  (\S+)\s+\[(\w+), ([^\]]+)\]", ln)
    if m:
        cur = m.group(1)
        P[cur] = dict(role=m.group(2), rule=m.group(3))
        continue
    m = re.match(r"^\s+old (.*?)  \|  new (.*?)  ->  (\w+):? ?(.*)$", ln)
    if m and cur and "old" not in P[cur]:
        P[cur].update(old=m.group(1), new=m.group(2), verdict=m.group(3), rest=m.group(4))
printout_concl = {}
for ln in PLINES:
    m = re.match(r"^(Read \d) .*-> CONCLUSION (HOLDS|CHANGES)", ln)
    if m:
        printout_concl[m.group(1)] = (m.group(2), ln.split("->", 1)[1].strip() if "->" in ln else "")
printout_sha = {}
for ln in PLINES:
    m = re.match(r"^  ([0-9a-f]{64})  (old|new) (.*)$", ln)
    if m:
        printout_sha[m.group(3)] = m.group(1)

norm = lambda s: re.sub(r"\s+", " ", s.replace("−", "-")).strip()

# ================================================================ output
say("#705 v2 COMPARISON - INDEPENDENT RECOUNT (written from prereg section 7; does not import v2_compare.py)")
say("old = published sources; new = chain outputs (rerun_v2_1025 / v2_1025 / cb702_pre_v2/out).  Rules R1-R6 as registered.")
say("Match columns compare MY strings to the strings printed in v2_compare.txt (old text, new text, verdict word).")
say("")
READS = {"Read 1": ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8"],
         "Read 2": ["2.0", "2.1", "2.2", "2.3", "2.4", "2.5"],
         "Read 3": ["3.1", "3.2", "3.2b", "3.2c", "3.3", "3.4", "3.5", "3.6", "3.7"],
         "Read 4": ["4.0", "4.1", "4.2", "4.2b", "4.2c", "4.3", "4.3b", "4.3c", "4.3d", "4.4", "4.4b", "4.5", "4.5b"],
         "Stages": ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]}
TITLE = {"Read 1": "was our trigger early, and does a real breakout follow through?",
         "Read 2": "of the big winners, how many did we catch?",
         "Read 3": "entry at the breakout close x four stops x up to two retries",
         "Read 4": "the trail exit, sixteen ways", "Stages": "the chain's own stages (decide nothing new)"}
MM = []       # mismatches found against the printout
CONCL = {}
for grp, ids in READS.items():
    deciding = [i for i in ids if RES[i]["role"] == "deciding"]
    changed = [i for i in deciding if RES[i]["verdict"] != "HOLDS"]
    CONCL[grp] = ("HOLDS" if not changed else "CHANGES", changed)
    if grp != "Stages":
        word = "CONCLUSION HOLDS: every deciding line holds" if not changed else f"CONCLUSION CHANGES: {', '.join(changed)}"
        say(f"{grp} - {TITLE[grp]} -> {word}")
    else:
        say(f"{TITLE[grp]}")
    for i in ids:
        r = RES[i]
        pr = P.get(i)
        if pr is None:
            m_old = m_new = m_ver = "NO-PRINTOUT-LINE"
        else:
            if r["rule"] == "R6" and r["role"] == "beside":
                # the printout renders R6 values as python tuples; compare the old -> new (xratio) text instead
                m_old = m_new = None
                m_ver = "MATCH" if (pr["verdict"] == r["verdict"] and norm(r["reason"]) in norm(pr["rest"])) else "MISMATCH"
                m_old = m_new = "MATCH" if m_ver == "MATCH" else "MISMATCH"
            else:
                m_old = "MATCH" if norm(pr["old"]) == norm(r["old"]) else "MISMATCH"
                m_new = "MATCH" if norm(pr["new"]) == norm(r["new"]) else "MISMATCH"
                m_ver = "MATCH" if pr["verdict"] == r["verdict"] else "MISMATCH"
        if "MISMATCH" in (m_old, m_new, m_ver) or "NO-PRINTOUT-LINE" in (m_old,):
            MM.append(i)
        say(f"  {i:<5} [{r['role']}, {r['rule']}] {r['title']}")
        say(f"        old {r['old']}  |  new {r['new']}  ->  {r['verdict']}: {r['reason']}")
        say(f"        vs printout: old {m_old} | new {m_new} | verdict {m_ver}"
            + ("" if pr is None else f"   (printout verdict word: {pr['verdict']})"))
        if (m_old == "MISMATCH" or m_new == "MISMATCH") and pr is not None:
            say(f"        printout old: {pr['old']}")
            say(f"        printout new: {pr['new']}")
    say("")

# cross-check: the fills tables behind 1.1 / 1.2 (bonus, not the section-7 source)
say("CROSS-CHECK (bonus; not the section-7 source) - lines 1.1 / 1.2 from the fills tables themselves:")
xc = []
for k, p in enumerate(FILLS):
    rows = list(csv.DictReader(io.StringIO(gzip.decompress(read_bytes(p)).decode("utf-8")), delimiter="\t"))
    d = sorted(float(r["dist_adr"]) for r in rows if r["dist_adr"] not in ("", "nan", "NaN"))
    nn_ = len(d)
    med = d[nn_ // 2] if nn_ % 2 else (d[nn_ // 2 - 1] + d[nn_ // 2]) / 2
    atab = sum(1 for x in d if x <= 0)
    xc.append((nn_, med, atab, len(rows)))
    say(f"  {'old' if k == 0 else 'new'} fills table: {len(rows):,} rows, {nn_:,} with a distance; median {med:+.4f} ADR; at/above the base high {atab:,}")
xc_ok = (round(xc[0][1], 2) == m_o and round(xc[1][1], 2) == m_n and xc[0][2] == c_o and xc[1][2] == c_n and xc[0][0] == n_o and xc[1][0] == n_n)
say(f"  tables {'AGREE' if xc_ok else 'DISAGREE'} with the report md numbers used for 1.1 (median {m_o:.2f} -> {m_n:.2f}) and 1.2 (count/n {c_o:,}/{n_o:,} -> {c_n:,}/{n_n:,})")
say("")

# registered OLD values vs the old source files
say("REGISTERED-OLD CHECK - the old values typed in prereg section 7 vs the old source files (at the doc's printed precision):")
bad_reg = []
for line, label, actual, registered, dp in REG:
    def close(a, b):
        if isinstance(a, (tuple, list)):
            return len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))
        if isinstance(a, str) or isinstance(b, str):
            return a == b
        return abs(a - b) <= 0.5 * 10 ** (-dp) + 1e-12
    ok = close(actual, registered)
    if not ok:
        bad_reg.append(line)
    say(f"  {line:<5} {'OK ' if ok else 'BAD'} {label}: source {actual!r} vs registered {registered!r}")
say(f"  -> {'all registered old values equal the old sources' if not bad_reg else 'DIFFER: ' + ', '.join(bad_reg)}")
say("")

# sha256 of the bytes this script read vs the printout's SOURCE SHA256 list
say("SOURCE SHA256 - bytes this script read vs the hashes v2_compare.txt printed:")
sha_bad = []
for p, h in sorted(SHA_SEEN.items()):
    ph = printout_sha.get(p)
    if ph is None:
        say(f"  not in the printout list (bonus cross-check file): {p}")
    elif ph == h:
        say(f"  SAME  {h[:16]}  {p}")
    else:
        sha_bad.append(p)
        say(f"  DIFF  mine {h[:16]} printout {ph[:16]}  {p}")
say("")

# totals
deciding_ids = [i for i in RES if RES[i]["role"] == "deciding"]
holds = [i for i in deciding_ids if RES[i]["verdict"] == "HOLDS"]
chg_all = [i for i in RES if RES[i]["verdict"] == "CHANGES"]
say("SUMMARY")
say(f"  deciding lines: {len(deciding_ids)} ({', '.join(deciding_ids)}); HOLDS {len(holds)}; CHANGES {len(deciding_ids) - len(holds)}")
say(f"  every line that reads CHANGES (deciding or not): {chg_all if chg_all else 'none'}")
say(f"  read conclusions (mine): " + "; ".join(f"{g} {CONCL[g][0]}" for g in ("Read 1", "Read 2", "Read 3", "Read 4")))
pc = {g: printout_concl.get(g, ("?", ""))[0] for g in ("Read 1", "Read 2", "Read 3", "Read 4")}
say(f"  read conclusions (printout): " + "; ".join(f"{g} {pc[g]}" for g in pc))
concl_ok = all(CONCL[g][0] == pc[g] for g in pc)
checks_ok = RES["2.0"]["verdict"] == "PASSES" and RES["4.0"]["verdict"] == "PASSES"
say(f"  checks 2.0 / 4.0: {RES['2.0']['verdict']} / {RES['4.0']['verdict']}")
say(f"  stages S1-S7: " + ", ".join(f"{s} {RES[s]['verdict']}" for s in READS["Stages"]))
say(f"  lines whose old/new/verdict string differs from the printout: {MM if MM else 'none'}")
final = (not MM) and concl_ok and not bad_reg and not sha_bad and xc_ok
say(f"  OVERALL: {'RECOUNT MATCHES THE PRINTOUT on every line, conclusion, registered old value and source hash' if final else 'DIFFERENCES FOUND - see above'}")

with open(OUT_TXT, "w", encoding="utf-8") as fh:
    fh.write(OUT.getvalue())
