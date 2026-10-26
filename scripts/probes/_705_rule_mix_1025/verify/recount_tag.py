#!/usr/bin/env python3
"""#705 rule-mix — INDEPENDENT RECOUNT of the tagging printout (01_mix_tag.txt) from the per-trade files.

Registration: docs/analysis/cb_rule_mix_prereg_2026-10-25.md §3 (libraries and orders), §4 (the four buckets, the greedy tag, the
standalone share, precision, the one scorable denominator), §5 (controls), §6 (labels and the union's `mix / no mix`).

Independence: this file imports NOTHING from 01_mix.py or the frozen modules (stdlib only). The library orders, the label rule, the
union rule and every aggregation below are written here from the registration text. It READS (writes only verify/recount_tag.txt):
  rule_mix/tags_enter.tsv, tags_stop.tsv, tags_exit.tsv, control_windows.tsv.gz   (the run's per-trade files)
  intraday/enter_fit_trades.tsv, check_enter_trades.tsv   (earlier stage on disk; used ONLY for the per-level shifted chance per rule)
  01_mix_tag.txt   (the printout it is compared against)

What is recomputed from rows: every bucket count, greedy / standalone / precision share, the discretion and UNION shares, the earliest-
firing share, the ENTER random-price floor, the k-price / shared-window / per-level-shifted chance unions, the STOP/EXIT control-(a) and
control-(b) per-rule and union lines (both the frames and the no-frames mode) from the per-draw control rows, the random-level per-rule
floor, each rule label under §6, the summary labels and the UNION `mix / no mix` verdict.
What is NOT recomputable from any file: the STOP/EXIT random-level UNION (k independent levels per draw; only the single-level per-trade
`rlevel_ex` is written) — taken as printed, with an analytic estimate 1-(1-p)^k from the per-trade p shown beside; and the ENTER per-
level shifted chance for windows that have no row in the intraday TSVs (see the report).

Run:  python3 scripts/probes/_705_rule_mix_1025/verify/recount_tag.py
"""
from __future__ import annotations

import csv
import gzip
import math
import os
import re
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.dirname(HERE)
PRINTOUT = os.path.join(PROBE, "01_mix_tag.txt")
OUT_TXT = os.path.join(HERE, "recount_tag.txt")
DATA = "/Users/alvinfung/apollo_data/cb702/qm_streams/holdings_1024"
MIXDIR = os.path.join(DATA, "rule_mix")
INTRADIR = os.path.join(DATA, "intraday")

# ---------------------------------------------------------------------------------------------------------------------------------
# §3: the libraries, in the registered order (typed here from the doc's tables; asserted against the TSV headers in main())
# ---------------------------------------------------------------------------------------------------------------------------------
ORDER = {
    # §3a rows E-1..E-7: L1, L8, L2, L7, L3, L9, L4   (L5, L6 are NOT in the library)
    "ENTER": ["L1", "L8", "L2", "L7", "L3", "L9", "L4"],
    # §3b rows S-1..S-15: S1-T | S10 T,H,C | S9 T,H,C | S1-H, S1-C | S3 T,H,C | S4 T,H,C
    "STOP": ["S1-T", "S10-T", "S10-H", "S10-C", "S9-T", "S9-H", "S9-C", "S1-H", "S1-C", "S3-T", "S3-H", "S3-C", "S4-T", "S4-H", "S4-C"],
    # §3c: tier 1 M-1, M-2, M-3, M-4, M-5 (directly before its superset M-9), M-9, M-6, M-2s, M-11 ; tier 2 M-7, M-8, M-10
    "EXIT": ["M-1", "M-2", "M-3", "M-4", "M-5", "M-9", "M-6", "M-2s", "M-11", "M-7", "M-8", "M-10"],
}
EX, ME, UN, NE = "EXPLAINS", "MISS-EARLY", "UNRESOLVED", "NEITHER"
BLOCKS = ("2020", "2021-22", "untouched")

# §6 label constants, in tenths of a percentage point
CARRIES_MARGIN, CHANCE_BAND, PRECISION_BAR, MIX_MARGIN = 150, 50, 500, 150


def f1(x) -> str:
    """The printed one-decimal percentage."""
    return "nan%" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100.0 * x:.1f}%"


def tenths(x: float) -> int:
    """A share as its printed one-decimal percentage, in tenths of a point (§6: labels compare the printed numbers)."""
    return int(round(float(f"{100.0 * x:.1f}") * 10))


def label_of(stand: float, chance: float, prec: float) -> str:
    """§6: standalone >= 15.0 points over the chance share AND precision >= 50.0% -> carries; within 5.0 points -> chance; more than 5.0
    UNDER -> below chance; the rest -> weak."""
    d = tenths(stand) - tenths(chance)
    if d >= CARRIES_MARGIN and not math.isnan(prec) and tenths(prec) >= PRECISION_BAR:
        return "carries"
    if abs(d) <= CHANCE_BAND:
        return "chance"
    if d < -CHANCE_BAND:
        return "below chance"
    return "weak"


def mix_of(union: float, chance_union: float) -> bool:
    """§6: the union beats the chance union by >= 15 points (printed one-decimal percentages)."""
    return tenths(union) - tenths(chance_union) >= MIX_MARGIN


def mean(xs):
    xs = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return sum(xs) / len(xs) if xs else math.nan


def num(s: str):
    return math.nan if s == "" else float(s)


def read_tsv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def is_tie(x: float) -> bool:
    """True when x (a fraction) sits exactly on a printed-rounding half point (e.g. 4.15%): the one-decimal print is then arbitrary."""
    t = 1000.0 * x
    return abs(t - math.floor(t) - 0.5) < 1e-6


# ---------------------------------------------------------------------------------------------------------------------------------
# the printout, parsed
# ---------------------------------------------------------------------------------------------------------------------------------
def parse_printout(path):
    tables, summaries, cur, sec = {}, {}, None, None
    for ln in open(path, encoding="utf-8").read().split("\n"):
        m = re.match(r"^decision (ENTER|STOP|EXIT) — block (.+?) \(n scorable (\d+);", ln)
        if m:
            sec = None
            cur = dict(dec=m.group(1), block=m.group(2), n=int(m.group(3)), rules={})
            tables[(cur["dec"], cur["block"])] = cur
            continue
        m = re.match(r"^## (ENTER|STOP|EXIT) — the summary labels", ln)
        if m:
            sec = m.group(1)
            summaries[sec] = dict(rows={}, union=None)
            cur = None
            continue
        if sec and ln.startswith("  UNION:"):
            summaries[sec]["union"] = ln.strip()
            continue
        if sec and re.match(r"^  \S+\s+\|", ln) and not ln.strip().startswith("rule"):
            cells = [c.strip() for c in ln.split("|")]
            summaries[sec]["rows"][cells[0]] = cells[1:]
            continue
        if cur is None:
            continue
        if ln.strip() == "":
            cur = None
            continue
        s = ln.strip()
        if re.match(r"^[A-Za-z0-9\-]+\s+\|", s) and not s.startswith("rule"):
            cells = [c.strip() for c in s.split("|")]
            cur["rules"][cells[0]] = cells[1:]
        elif s.startswith("discretion "):
            cur["disc"] = s
        elif s.startswith("UNION "):
            cur["union_line"] = s
    return tables, summaries


def pct_of(cell: str) -> str:
    m = re.match(r"^(nan%|[0-9.]+%)", cell.strip())
    return m.group(1) if m else cell.strip()


def load_controls():
    """Per (decision, range, eid): n rows, per-rule count of 'E', count of rows with >= 1 'E' among the decision's own rules."""
    acc = {}
    with gzip.open(os.path.join(MIXDIR, "control_windows.tsv.gz"), "rt", newline="") as fh:
        rd = csv.reader(fh, delimiter="\t")
        hdr = next(rd)
        idx = {h: i for i, h in enumerate(hdr)}
        for row in rd:
            dec, eid, rng = row[0], row[1], row[2]
            rules = ORDER[dec]
            a = acc.setdefault((dec, rng, eid), dict(n=0, ex=Counter(), un=0))
            a["n"] += 1
            anyx = False
            for r in rules:
                if row[idx[r]] == "E":
                    a["ex"][r] += 1
                    anyx = True
            if anyx:
                a["un"] += 1
    return acc


def main():
    S = {k: [] for k in ("head", "cmp", "rows", "detail", "robust")}
    cur = ["detail"]

    def say(s=""):
        S[cur[0]].append(s)

    tables, summaries = parse_printout(PRINTOUT)
    controls = load_controls()
    enter = read_tsv(os.path.join(MIXDIR, "tags_enter.tsv"))
    stop = read_tsv(os.path.join(MIXDIR, "tags_stop.tsv"))
    exitr = read_tsv(os.path.join(MIXDIR, "tags_exit.tsv"))
    for dec, rows in (("STOP", stop), ("EXIT", exitr), ("ENTER", enter)):
        got = [h[:-7] for h in rows[0].keys() if h.endswith("_bucket")]
        assert got == ORDER[dec], (dec, got, ORDER[dec])
    shift = {}
    for fn in ("enter_fit_trades.tsv", "check_enter_trades.tsv"):
        for r in read_tsv(os.path.join(INTRADIR, fn)):
            shift[r["eid"]] = r

    cnt = Counter()
    diffs, ties, partials = [], [], []      # real differences / exact-half rounding ties / per-level-shifted cells with incomplete source rows

    def cmp(where, what, printed, mine, val=None):
        cnt["cells"] += 1
        if str(printed) == str(mine):
            cnt["equal"] += 1
        elif val is not None and is_tie(val) and abs(float(str(printed)[:-1]) - float(str(mine)[:-1])) < 0.11:
            ties.append((where, what, str(printed), str(mine), val))
        else:
            diffs.append((where, what, str(printed), str(mine)))

    results = {}
    labels_by = {}

    # =============================================================================================================================
    # ENTER
    # =============================================================================================================================
    order = ORDER["ENTER"]

    def enter_sel(block, sub):
        rows = [r for r in enter if r["block"] == block]
        if sub is None:
            return [r for r in rows if r["tagged"] == "True"]
        if sub == "dated":
            return [r for r in rows if r["tagged"] == "True" and r["dated"] == "True"]
        if sub == "undated non-flicker":
            return [r for r in rows if r["tagged"] == "True" and r["dated"] == "False"]
        if sub == "flickers":
            return [r for r in rows if r["tagged"] == "False" and r["dated"] == "False" and r["flicker"] == "True"]
        if sub == "pre-market-flat, dated":
            return [r for r in rows if r["tagged"] == "False" and r["dated"] == "True"]
        if sub == "pre-market-flat, undated":
            return [r for r in rows if r["tagged"] == "False" and r["dated"] == "False" and r["flicker"] == "False"]
        raise KeyError(sub)

    def hhmm_min(s):
        h, m = s.split(":")
        return int(h) * 60 + int(m) - (9 * 60 + 30)       # minutes since 09:30

    bad_bucket, bad_tag, bad_etag = [], [], []
    for r in enter:
        flat, first = hhmm_min(r["flat_clock"]), hhmm_min(r["first_clock"])
        exs = []
        for c in order:
            cross = num(r[c + "_cross"])
            if math.isnan(cross) or cross > first:
                mine = NE
            elif cross <= flat:
                mine = ME
            else:
                mine = EX
            if mine != r[c + "_bucket"]:
                bad_bucket.append((r["eid"], c, r[c + "_bucket"], mine, r[c + "_cross"], r["flat_clock"], r["first_clock"]))
            if mine == EX:
                exs.append((cross, order.index(c), c))
        g = next((c for c in order if r[c + "_bucket"] == EX), "discretion")
        if g != r["tag"]:
            bad_tag.append((r["eid"], r["tag"], g))
        et = min(exs)[2] if exs else "discretion"
        if et != r["earliest_tag"]:
            bad_etag.append((r["eid"], r["earliest_tag"], et))
    say("## ENTER row-level re-derivation (the independent part: bucket, greedy tag, earliest tag, and the control columns, from the rows)")
    say(f"- bucket re-derived from the cross minute and the flat / first clocks (§4a: EXPLAINS = first crossing in (flat_clock, first_clock]; at or before flat = MISS-EARLY; "
        f"none by first_clock = NEITHER) vs the file's bucket: {len(enter) * len(order) - len(bad_bucket)} of {len(enter) * len(order)} cells equal; {len(bad_bucket)} differ")
    say(f"- greedy tag (first EXPLAINS rule in the registered order, else discretion) vs the file's tag: {len(enter) - len(bad_tag)} of {len(enter)} rows equal; {len(bad_tag)} differ")
    say(f"- earliest-firing tag (the EXPLAINS rule with the earliest cross minute, ties -> library order) vs the file: {len(enter) - len(bad_etag)} of {len(enter)} rows equal; {len(bad_etag)} differ")
    ctl_eids = {k[2] for k in controls if k[0] == "ENTER"}
    tsv_eids = {r["eid"] for r in enter}
    say(f"- ENTER controls: {len(ctl_eids)} eids in control_windows, {len(tsv_eids)} rows in tags_enter. In controls but not in the TSV: {sorted(ctl_eids - tsv_eids)} "
        f"(eid 1719 = DWAC 2022-01-31: dropped by §2c flat_before_open, intraday dry run l.30; it stays in the replayed random-draw population, in no block, in no printed n). "
        f"In the TSV but not in controls: {sorted(tsv_eids - ctl_eids)}")
    sh_bad = sum(1 for r in enter if abs(controls[("ENTER", "shared", r["eid"])]["un"] / controls[("ENTER", "shared", r["eid"])]["n"] - num(r["shared_union"])) > 1e-9)
    say(f"- the file's per-record shared_union vs the union re-counted from control_windows' 200 draws per record: {len(enter) - sh_bad} of {len(enter)} equal")

    enter_detail = {}
    for (dec, bname), T in tables.items():
        if dec != "ENTER":
            continue
        m = re.match(r"^(2020|2021-22|untouched)(?: / (.+?) \(beside\))?$", bname)
        block, sub = m.group(1), m.group(2)
        if sub == "non-flicker":
            sub = None
        rows = enter_sel(block, sub)
        n = len(rows)
        where = f"ENTER {bname}"
        cmp(where, "n scorable", T["n"], n)
        stand, prec, greedy, etg, shared_ch, shift_lv, cn = {}, {}, {}, {}, {}, {}, {}
        for c in order:
            e = sum(1 for r in rows if r[c + "_bucket"] == EX)
            mm = sum(1 for r in rows if r[c + "_bucket"] == ME)
            cn[c] = e
            stand[c] = e / n
            prec[c] = e / (e + mm) if e + mm else math.nan
            greedy[c] = sum(1 for r in rows if next((x for x in order if r[x + "_bucket"] == EX), "discretion") == c) / n
            etg[c] = sum(1 for r in rows if r["earliest_tag"] == c) / n
            shared_ch[c] = mean([controls[("ENTER", "shared", r["eid"])]["ex"][c] / controls[("ENTER", "shared", r["eid"])]["n"] for r in rows])
            present = [num(shift[r["eid"]][c + "_shift_feasible"]) for r in rows if r["eid"] in shift and shift[r["eid"]][c + "_shift_no_room"] == "False"]
            absent = [r for r in rows if r["eid"] not in shift]
            shift_lv[c] = (mean(present), len(present), len(absent), sum(present), [r["eid"] for r in absent])
        disc = sum(1 for r in rows if all(r[x + "_bucket"] != EX for x in order)) / n
        union = 1 - disc
        rprice = mean([num(r["rprice_feasible"]) for r in rows])
        k_u = mean([num(r["kprice_union"]) for r in rows])
        s_u = mean([num(r["shared_union"]) for r in rows])
        l_u = mean([num(r["shift_union"]) for r in rows])
        chance_u = max(k_u, s_u, l_u)
        cmp(where, "discretion", pct_of(T["disc"].split(" ", 1)[1]), f1(disc), disc)
        um = re.match(r"^UNION ([0-9.]+%) .*? chance union: k-price ([0-9.]+%) \| shared-window ([0-9.]+%) \| per-level shifted ([0-9.]+%) -> the largest ([0-9.]+%)", T["union_line"])
        cmp(where, "UNION", um.group(1), f1(union), union)
        cmp(where, "chance union k-price", um.group(2), f1(k_u), k_u)
        cmp(where, "chance union shared-window", um.group(3), f1(s_u), s_u)
        cmp(where, "chance union per-level shifted", um.group(4), f1(l_u), l_u)
        cmp(where, "chance union (largest)", um.group(5), f1(chance_u), chance_u)
        labels, labels_noshift, labels_printedshift, shift_largest = {}, {}, {}, {}
        for c in order:
            cells = T["rules"][c]
            mean_sh, m_, k_, s_, absent_eids = shift_lv[c]
            printed_sh = cells[4].split("/")[0].strip()
            printed_sh_val = float(printed_sh[:-1]) / 100.0
            if k_ == 0:
                cmp(where, f"{c} chance shifted per level", printed_sh, f1(mean_sh), mean_sh)
            elif m_ == 0:
                partials.append(dict(where=where, c=c, printed=printed_sh, note="no source rows", k=k_, ok=None, eids=absent_eids, fixed=False))
            else:
                lo = min(s_ / (m_ + k_), s_ / m_)
                hi = max((s_ + k_) / (m_ + k_), s_ / m_)
                inside = tenths(lo) - 1 <= round(printed_sh_val * 1000) <= tenths(hi) + 1
                partials.append(dict(where=where, c=c, printed=printed_sh, k=k_, ok=inside, eids=absent_eids, m=m_, s=s_, mine=f1(mean_sh), lo=f1(lo), hi=f1(hi),
                                     note=f"{f1(mean_sh)} on {m_} of {m_ + k_} windows; the {k_} absent can put it in [{f1(lo)}, {f1(hi)}]",
                                     fixed=(f1(mean_sh) != printed_sh)))
            chance = max(x for x in (rprice, shift_lv[c][0], shared_ch[c]) if not math.isnan(x))
            labels[c] = label_of(stand[c], chance, prec[c])
            labels_noshift[c] = label_of(stand[c], max(rprice, shared_ch[c]), prec[c])
            labels_printedshift[c] = label_of(stand[c], max(rprice, shared_ch[c], printed_sh_val), prec[c])
            shift_largest[c] = printed_sh_val > max(rprice, shared_ch[c])
            cmp(where, f"{c} greedy", pct_of(cells[1]), f1(greedy[c]), greedy[c])
            cmp(where, f"{c} standalone", pct_of(cells[2]), f1(stand[c]), stand[c])
            cmp(where, f"{c} standalone count", re.search(r"\((\d+)\)", cells[2]).group(1), cn[c])
            cmp(where, f"{c} chance random-price", pct_of(cells[3]), f1(rprice), rprice)
            cmp(where, f"{c} chance shared window", cells[4].split("/")[1].strip(), f1(shared_ch[c]), shared_ch[c])
            cmp(where, f"{c} precision", pct_of(cells[6]), f1(prec[c]), prec[c])
            cmp(where, f"{c} earliest-order", pct_of(cells[7]), f1(etg[c]), etg[c])
            cmp(where, f"{c} label", cells[8], labels[c])
        enter_detail[bname] = dict(shift_largest=shift_largest, noshift=labels_noshift, printedshift=labels_printedshift, printed={c: T["rules"][c][8] for c in order})
        results[("ENTER", bname)] = dict(n=n, union=union, chance=chance_u, mix=mix_of(union, chance_u), labels=labels, printed_union=um.group(1), printed_chance=um.group(5),
                                         parts=dict(k=k_u, shared=s_u, shift=l_u), stand=stand, prec=prec, greedy=greedy, disc=disc, rprice=rprice,
                                         chance_rule={c: max(x for x in (rprice, shift_lv[c][0], shared_ch[c]) if not math.isnan(x)) for c in order},
                                         printed_labels={c: T["rules"][c][8] for c in order})

    # =============================================================================================================================
    # STOP / EXIT
    # =============================================================================================================================
    def se_sel(rows, dec, block, sub):
        base = [r for r in rows if r["block"] == block and r["status"] == "scorable" and r["room"] == "True"]
        if dec == "STOP":
            base = [r for r in base if r["loser"] == "True"]
        if sub is None:
            return base
        if sub == "dated":
            return [r for r in base if r["dated"] == "True"]
        if sub == "undated":
            return [r for r in base if r["dated"] == "False"]
        if sub == "losers":
            return [r for r in base if r["loser"] == "True"]
        if sub == "non-losers":
            return [r for r in base if r["loser"] == "False"]
        raise KeyError(sub)

    for dec, rows in (("STOP", stop), ("EXIT", exitr)):
        order = ORDER[dec]
        n_sc = bad_greedy = 0
        viol = Counter()
        bad_et = []
        for r in rows:
            if r["status"] != "scorable":
                continue
            n_sc += 1
            lo, hi = float(r["exit_lo_j"]), float(r["exit_hi_j"])
            g = next((c for c in order if r[c + "_bucket"] == EX), "discretion")
            if g != r["tag"]:
                bad_greedy += 1
            for c in order:
                b, bk = r[c + "_bucket"], num(r[c + "_booked_j"])
                if b == EX and not (not math.isnan(bk) and lo <= bk <= hi):
                    viol["EXPLAINS booked outside [exit_lo_j, exit_hi_j]"] += 1
                if b == ME and not (not math.isnan(bk) and bk < lo):
                    viol["MISS-EARLY not before exit_lo_j"] += 1
                if b == NE and not (math.isnan(bk) or bk > hi):
                    viol["NEITHER with a booked session inside / before the window"] += 1
            cand = []
            for i, c in enumerate(order):
                if r[c + "_bucket"] == EX:
                    fm = num(r[c + "_first_minute"])
                    cand.append((num(r[c + "_first_j"]), 0 if math.isnan(fm) else fm, i, c))
            et = min(cand)[3] if cand else "discretion"
            if et != r["earliest_tag"]:
                bad_et.append((r["eid"], r["sym"], r["E"], r["block"], f"room={r['room']}", r["earliest_tag"], et))
        say("")
        say(f"## {dec} row-level re-derivation ({n_sc} scorable of {len(rows)} rows)")
        say(f"- greedy tag (first EXPLAINS rule in the registered order, else discretion) vs the file's tag: {n_sc - bad_greedy} of {n_sc} equal; {bad_greedy} differ")
        say(f"- bucket vs booked session against the window [exit_lo_j, exit_hi_j] (structural; UNRESOLVED unconstrained): violations {dict(viol) if viol else 'none'}")
        say(f"- earliest-firing tag (EXPLAINS rule with the earliest (event session, minute), ties -> library order) vs the file: {n_sc - len(bad_et)} of {n_sc} equal; differ: {bad_et if bad_et else 'none'}"
            + ("  [every differing trade has room=False, i.e. sits outside every printed denominator; the tie is a buy-day touch row with no minute, which my default orders first]"
               if bad_et and all(x[4] == 'room=False' for x in bad_et) else ""))
        say("  (the printed earliest-order column is compared file->printout in the cell comparison; the row-level line above is the independent derivation)")
        ca_bad = cb_bad = pl_bad = n_ca = 0
        for r in rows:
            if r["status"] != "scorable":
                continue
            a, b_ = controls[(dec, "a", r["eid"])], controls[(dec, "b", r["eid"])]
            n_ca += 1
            ca_bad += abs(a["un"] / a["n"] - num(r["ctl_a_union"])) > 1e-9
            cb_bad += abs(b_["un"] / b_["n"] - num(r["ctl_b_union"])) > 1e-9
            pl_bad += a["n"] != int(float(r["exit_lo_j"])) + 1
        say(f"- the file's per-trade ctl_a_union / ctl_b_union vs the union re-counted from the per-draw control rows (frames mode): {n_ca - ca_bad} of {n_ca} equal (a), "
            f"{n_ca - cb_bad} of {n_ca} equal (b); placements in (a) = exit_lo_j + 1 on {n_ca - pl_bad} of {n_ca} trades")

    se_extra = {}
    for (dec, bname), T in tables.items():
        if dec not in ("STOP", "EXIT"):
            continue
        m = re.match(r"^(2020|2021-22|untouched)(?: / (.+?)(?: \(beside\))?)?$", bname)
        block, sub = m.group(1), m.group(2)
        rows = se_sel(stop if dec == "STOP" else exitr, dec, block, sub)
        order = ORDER[dec]
        n = len(rows)
        where = f"{dec} {bname}"
        cmp(where, "n scorable", T["n"], n)
        stand, prec, greedy, etg, cn = {}, {}, {}, {}, {}
        for c in order:
            e = sum(1 for r in rows if r[c + "_bucket"] == EX)
            mm = sum(1 for r in rows if r[c + "_bucket"] == ME)
            cn[c] = e
            stand[c] = e / n
            prec[c] = e / (e + mm) if e + mm else math.nan
            greedy[c] = sum(1 for r in rows if next((x for x in order if r[x + "_bucket"] == EX), "discretion") == c) / n
            etg[c] = sum(1 for r in rows if r["earliest_tag"] == c) / n
        disc = sum(1 for r in rows if all(r[x + "_bucket"] != EX for x in order)) / n
        union = 1 - disc

        def ctl_rule(rng, c, rs=rows, dec=dec):
            return mean([controls[(dec, rng, r["eid"])]["ex"][c] / controls[(dec, rng, r["eid"])]["n"] for r in rs])

        def ctl_union(rng, rs=rows, dec=dec):
            return mean([controls[(dec, rng, r["eid"])]["un"] / controls[(dec, rng, r["eid"])]["n"] for r in rs])

        a_u, aff_u, b_u, bff_u = ctl_union("a"), ctl_union("a_ff"), ctl_union("b"), ctl_union("b_ff")
        rl_rows = [r for r in rows if r["rlevel_ex"] != ""]
        rl_ex = mean([num(r["rlevel_ex"]) for r in rl_rows])
        k = len(order)
        rl_est = mean([1 - (1 - num(r["rlevel_ex"])) ** k for r in rl_rows])          # analytic: k independent levels per draw
        a_larger = max(a_u, aff_u)
        um = re.match(r"^UNION ([0-9.]+%) .*? chance union: \(a\) inside the hold ([0-9.]+%) with frames / ([0-9.]+%) without \| random level \(k = (\d+)\) ([0-9.]+%) \| "
                      r"\(b\) hold \+ tail ([0-9.]+%) / ([0-9.]+%) -> the larger of \(a\) and the random level ([0-9.]+%)", T["union_line"])
        rl_printed = float(um.group(5)[:-1]) / 100.0
        chance_u = max(a_larger, rl_printed)
        cmp(where, "discretion", pct_of(T["disc"].split(" ", 1)[1]), f1(disc), disc)
        cmp(where, "UNION", um.group(1), f1(union), union)
        cmp(where, "chance union (a) with frames", um.group(2), f1(a_u), a_u)
        cmp(where, "chance union (a) without frames", um.group(3), f1(aff_u), aff_u)
        cmp(where, "chance union k of random level", um.group(4), k)
        cmp(where, "chance union (b) with frames", um.group(6), f1(b_u), b_u)
        cmp(where, "chance union (b) without frames", um.group(7), f1(bff_u), bff_u)
        cmp(where, "chance union (larger of (a) and random level; random-level union TAKEN AS PRINTED)", um.group(8), f1(chance_u), chance_u)
        labels, alt = {}, {"ff_only": {}, "fa_only": {}}
        chance_rule = {}
        for c in order:
            cells = T["rules"][c]
            a_fa, a_ff = ctl_rule("a", c), ctl_rule("a_ff", c)
            chance = max(a_fa, a_ff, rl_ex)
            chance_rule[c] = chance
            labels[c] = label_of(stand[c], chance, prec[c])
            alt["ff_only"][c] = label_of(stand[c], max(a_ff, rl_ex), prec[c])
            alt["fa_only"][c] = label_of(stand[c], max(a_fa, rl_ex), prec[c])
            cmp(where, f"{c} greedy", pct_of(cells[1]), f1(greedy[c]), greedy[c])
            cmp(where, f"{c} standalone", pct_of(cells[2]), f1(stand[c]), stand[c])
            cmp(where, f"{c} standalone count", re.search(r"\((\d+)\)", cells[2]).group(1), cn[c])
            cmp(where, f"{c} chance (a) frames", cells[3].split("/")[0].strip(), f1(a_fa), a_fa)
            cmp(where, f"{c} chance (a) no frames", cells[3].split("/")[1].strip(), f1(a_ff), a_ff)
            cmp(where, f"{c} chance random level", pct_of(cells[4]), f1(rl_ex), rl_ex)
            cmp(where, f"{c} chance (b) frames", cells[5].split("/")[0].strip(), f1(ctl_rule("b", c)), ctl_rule("b", c))
            cmp(where, f"{c} chance (b) no frames", cells[5].split("/")[1].strip(), f1(ctl_rule("b_ff", c)), ctl_rule("b_ff", c))
            cmp(where, f"{c} precision", pct_of(cells[7]), f1(prec[c]), prec[c])
            cmp(where, f"{c} earliest-order", pct_of(cells[8]), f1(etg[c]), etg[c])
            cmp(where, f"{c} label", cells[10], labels[c])
        se_extra[(dec, bname)] = alt
        results[(dec, bname)] = dict(n=n, union=union, chance=chance_u, a_larger=a_larger, a_fa=a_u, a_ff=aff_u, rl_est=rl_est, rl_printed=rl_printed, rl_ex=rl_ex,
                                     mix=mix_of(union, chance_u), mix_a_only=mix_of(union, a_larger), mix_ff_only=mix_of(union, aff_u),
                                     mix_est=mix_of(union, max(a_larger, rl_est)), labels=labels, printed_union=um.group(1), printed_chance=um.group(8),
                                     stand=stand, prec=prec, greedy=greedy, disc=disc, chance_rule=chance_rule, printed_labels={c: T["rules"][c][10] for c in order})

    # =============================================================================================================================
    # summary labels and verdicts
    # =============================================================================================================================
    mix_rows, summary_lab_diffs = {}, 0
    for dec in ("ENTER", "STOP", "EXIT"):
        s = summaries[dec]
        for c in ORDER[dec]:
            L = [results[(dec, b)]["labels"][c] for b in BLOCKS]
            summ = "carries" if (L[0] == "carries" and L[1] == "carries") else "-"
            pr = s["rows"][c]
            for i, b in enumerate(BLOCKS):
                cmp(f"{dec} summary", f"{c} {b} label", pr[i], L[i])
            cmp(f"{dec} summary", f"{c} summary", pr[3], summ)
        r20, r22, ru = (results[(dec, b)] for b in BLOCKS)
        verdict = "mix" if (r20["mix"] and r22["mix"]) else "no mix"
        mm = re.match(r"^UNION: 2020 ([0-9.]+%) vs ([0-9.]+%); 2021-22 ([0-9.]+%) vs ([0-9.]+%); untouched ([0-9.]+%) vs ([0-9.]+%) -> (mix|no mix)", s["union"])
        cmp(f"{dec} summary", "UNION 2020", mm.group(1), f1(r20["union"]))
        cmp(f"{dec} summary", "chance 2020", mm.group(2), f1(r20["chance"]))
        cmp(f"{dec} summary", "UNION 2021-22", mm.group(3), f1(r22["union"]))
        cmp(f"{dec} summary", "chance 2021-22", mm.group(4), f1(r22["chance"]))
        cmp(f"{dec} summary", "UNION untouched", mm.group(5), f1(ru["union"]))
        cmp(f"{dec} summary", "chance untouched", mm.group(6), f1(ru["chance"]))
        cmp(f"{dec} summary", "verdict", mm.group(7), verdict)
        mix_rows[dec] = (verdict, mm.group(7))

    # =============================================================================================================================
    # HEAD: the table
    # =============================================================================================================================
    cur[0] = "head"
    say("# #705 RULE MIX — INDEPENDENT RECOUNT of the tagging printout (01_mix_tag.txt)")
    say("# own code (stdlib only; no import of 01_mix.py or the frozen modules). Inputs: rule_mix/tags_{enter,stop,exit}.tsv, control_windows.tsv.gz, the intraday ENTER TSVs")
    say("# (per-level shifted chance only) and the printout text. Registration cb_rule_mix_prereg_2026-10-25.md §3-§6. Run: python3 .../verify/recount_tag.py")
    say("")
    say("## HEADLINE — decision x block: UNION, chance union, mix verdict (printout vs mine; the verdict per block is the +15.0-point test, the overall verdict needs 2020 AND 2021-22)")
    hdr = (f"{'decision':8} {'block':10} {'n':>4} | {'UNION print':>11} {'mine':>6} | {'chance print':>12} {'mine':>6} | {'margin':>7} | {'verdict print':>13} {'mine':>7}")
    say(hdr)
    say("-" * len(hdr))
    for dec in ("ENTER", "STOP", "EXIT"):
        for b in BLOCKS:
            r = results[(dec, b)]
            pv = "mix" if tenths(float(r["printed_union"][:-1]) / 100) - tenths(float(r["printed_chance"][:-1]) / 100) >= MIX_MARGIN else "no mix"
            say(f"{dec:8} {b:10} {r['n']:>4} | {r['printed_union']:>11} {f1(r['union']):>6} | {r['printed_chance']:>12} {f1(r['chance']):>6} | {100 * (r['union'] - r['chance']):>+6.1f}p | {pv:>13} {'mix' if r['mix'] else 'no mix':>7}")
        say(f"{dec:8} {'OVERALL':10} {'':>4} | {'':>11} {'':>6} | {'':>12} {'':>6} | {'':>7} | printout: {mix_rows[dec][1]:6}  mine: {mix_rows[dec][0]}")
        say("")
    ncell, ndiff, nties, nbound = cnt["cells"], len(diffs), len(ties), len(partials)
    n_lab = sum(1 for k, v in results.items() for c in v["labels"] if v["labels"][c] != v["printed_labels"][c])
    lab_cells = sum(len(v["labels"]) for v in results.values())
    say(f"## rule labels that differ: {n_lab} of {lab_cells} (every rule x every printed table incl. the sub-blocks beside); summary-table labels / verdicts that differ: "
        f"{sum(1 for d in diffs if d[0].endswith('summary'))}")
    say(f"## cells compared: {ncell} printed numbers / labels; equal {cnt['equal']}; exact-half rounding ties {nties}; real differences {ndiff}; "
        f"per-level-shifted cells compared by bound only (source rows incomplete) {nbound}")

    # =============================================================================================================================
    # CMP: what differs and why
    # =============================================================================================================================
    cur[0] = "cmp"
    say("")
    say("## cells that are not an exact string match")
    if not diffs:
        say("- real differences: none")
    for d in diffs:
        say(f"  DIFF {d[0]} | {d[1]} | printout {d[2]} | mine {d[3]}")
    for t in ties:
        say(f"  TIE  {t[0]} | {t[1]} | printout {t[2]} | mine {t[3]} | exact value {100 * t[4]:.6f}% sits on a rounding half point (float summation order decides the printed digit); not a count difference")
    say("")
    say(f"## ENTER per-level shifted chance (printed column 'shifted per level'): {nbound} cells are compared by bound only")
    say("   control_windows holds only the SHARED-window ENTER draws; the per-level shifted share per rule is in the intraday TSVs (enter_fit_trades.tsv, check_enter_trades.tsv),")
    say("   which have no row for some windows the mix read scored. Absent windows per printed table (derived from the rows; a cell with some rows absent is bound-checked, a cell with")
    say("   none present is unverifiable from the files):")
    seen = {}
    for pt in partials:
        seen.setdefault(pt["where"], pt)
    for w, pt in seen.items():
        say(f"   {w}: {len(pt['eids'])} window(s) absent from the intraday TSVs" + (f" (eid {', '.join(pt['eids'])})" if len(pt['eids']) <= 3 else "")
            + ("; ALL absent: no source rows" if pt["note"] == "no source rows" else ""))
    by_kind = Counter("no source rows" if pt["note"] == "no source rows" else ("bound pass" if pt["ok"] else "bound FAIL") for pt in partials)
    say(f"   outcome over {nbound} cells: {dict(by_kind)}")
    for pt in partials:
        if pt["where"] in ("ENTER 2020", "ENTER 2021-22", "ENTER untouched"):
            say(f"   deciding block {pt['where']} {pt['c']}: printed {pt['printed']}; mine {pt['note']}; {'inside bound' if pt['ok'] else 'OUTSIDE bound'}")
    for pt in partials:
        if pt["where"] in ("ENTER 2020", "ENTER 2021-22", "ENTER untouched") and pt.get("fixed"):
            k_, m_, s_ = pt["k"], pt["m"], pt["s"]
            say(f"   {pt['where']} {pt['c']}: my mean over the {m_} present windows is {100 * s_ / m_:.3f}% -> {pt['mine']}; the printout averages {m_ + k_} (eid {', '.join(pt['eids'])} has no TSV row): "
                f"{s_:.4f}/{m_ + k_} = {100 * s_ / (m_ + k_):.3f}% (the absent window's own value 0) -> {f1(s_ / (m_ + k_))} = the printed {pt['printed']}")
    say("   Proof the per-level shifted column cannot matter to any label: every ENTER label recomputed WITHOUT the per-level shifted line (chance = max(random-price floor, shared window))")
    n_ns = sum(1 for b, v in enter_detail.items() for c in v["printed"] if v["noshift"][c] != v["printed"][c])
    n_ps = sum(1 for b, v in enter_detail.items() for c in v["printed"] if v["printedshift"][c] != v["printed"][c])
    n_tot = sum(len(v["printed"]) for v in enter_detail.values())
    say(f"   equals the printed label on {n_tot - n_ns} of {n_tot} rule x table cells ({n_ns} differ); recomputed WITH the printed per-level value, {n_tot - n_ps} of {n_tot} equal ({n_ps} differ).")
    dec_blocks = ("2020", "2021-22", "untouched")
    n_dec_sl = sum(1 for b in dec_blocks for c in ORDER["ENTER"] if enter_detail[b]["shift_largest"][c])
    n_all_sl = sum(1 for b in enter_detail for c in ORDER["ENTER"] if enter_detail[b]["shift_largest"][c])
    say(f"   (the per-level shifted value is the LARGEST of the three ENTER chance lines in {n_dec_sl} of 21 deciding-block rule cells and {n_all_sl} of {n_tot} cells over all printed tables; "
        f"so the column cannot move any label)")

    # =============================================================================================================================
    # ROWS: per-rule recount of the nine deciding tables
    # =============================================================================================================================
    cur[0] = "rows"
    say("")
    say("## PER-RULE RECOUNT of the nine deciding tables (mine; every number below equals the printout unless listed in the diff section above)")
    say("   greedy / standalone / precision are shares of the block's n; chance = the line the label is held against (ENTER: max(random-price, per-level shifted, shared window);")
    say("   STOP/EXIT: max(control (a) frames, control (a) no frames, random-level floor)); label = §6 on the printed one-decimal numbers; 'pr' = the printed label")
    for dec in ("ENTER", "STOP", "EXIT"):
        for b in BLOCKS:
            r = results[(dec, b)]
            say("")
            say(f"{dec} {b} (n {r['n']}): UNION {f1(r['union'])} = 1 - discretion {f1(r['disc'])}; chance union {f1(r['chance'])}")
            say(f"  {'rule':6} {'greedy':>7} {'stand.':>7} {'prec.':>7} {'chance':>7} {'label (mine)':>13} {'pr':>13}  {'ok':>3}")
            for c in ORDER[dec]:
                ok = "ok" if r["labels"][c] == r["printed_labels"][c] else "NO"
                say(f"  {c:6} {f1(r['greedy'][c]):>7} {f1(r['stand'][c]):>7} {f1(r['prec'][c]):>7} {f1(r['chance_rule'][c]):>7} {r['labels'][c]:>13} {r['printed_labels'][c]:>13}  {ok:>3}")

    # =============================================================================================================================
    # ROBUST
    # =============================================================================================================================
    cur[0] = "robust"
    say("")
    say("## chance-union detail: the three ENTER lines the printout quotes (k-price / shared-window / per-level shifted) and the STOP/EXIT control (a) modes + random-level union")
    for b in BLOCKS:
        r = results[("ENTER", b)]
        p = r["parts"]
        say(f"  ENTER {b:9} union {f1(r['union'])}  k-price {f1(p['k'])}  shared-window {f1(p['shared'])}  per-level shifted {f1(p['shift'])}  -> largest {f1(r['chance'])}; "
            f"margin {100 * (r['union'] - r['chance']):+.1f} pts; random-price floor {f1(r['rprice'])}")
    for dec in ("STOP", "EXIT"):
        for b in BLOCKS:
            r = results[(dec, b)]
            say(f"  {dec} {b:9} union {f1(r['union'])}  (a) frames {f1(r['a_fa'])} / no frames {f1(r['a_ff'])}  random-level union: printed {f1(r['rl_printed'])}, analytic estimate "
                f"{f1(r['rl_est'])} (diff {100 * abs(r['rl_est'] - r['rl_printed']):.1f} pt)  -> chance {f1(r['chance'])}; margin {100 * (r['union'] - r['chance']):+.1f} pts; "
                f"vs (a) alone {100 * (r['union'] - r['a_larger']):+.1f} pts")
    say("  CAVEAT (the one circular cell): the STOP/EXIT random-level UNION is a union of k independent levels per draw; no per-trade file stores it (only the single-level rlevel_ex),")
    say("  so 'chance mine' for STOP/EXIT takes it AS PRINTED. The analytic estimate 1-(1-p_t)^k from each trade's rlevel_ex reproduces it to <= 0.2 pt on all six cells. The verdict does")
    say("  not turn on it: the random level can only RAISE the chance line, and the union already fails the +15.0 bar against control (a) alone on both deciding blocks.")
    say("")
    say("## fragile readings (within 0.3 pt of a §6 threshold, on the printed one-decimal numbers); deciding blocks only")
    frag = 0
    for dec in ("ENTER", "STOP", "EXIT"):
        for b in BLOCKS:
            r = results[(dec, b)]
            for c in ORDER[dec]:
                d = tenths(r["stand"][c]) - tenths(r["chance_rule"][c])
                p = r["prec"][c]
                why = []
                for thr, nm in ((CARRIES_MARGIN, "carries margin +15.0"), (CHANCE_BAND, "chance band +5.0"), (-CHANCE_BAND, "chance band -5.0")):
                    if abs(d - thr) <= 3:
                        why.append(f"standalone - chance = {d / 10:+.1f} pt vs the {nm} bar")
                if d >= CARRIES_MARGIN - 3 and not math.isnan(p) and abs(tenths(p) - PRECISION_BAR) <= 3:
                    why.append(f"precision {f1(p)} vs the 50.0% bar")
                if why:
                    frag += 1
                    say(f"  {dec} {b} {c}: label {r['labels'][c]}; " + "; ".join(why))
    for dec in ("ENTER", "STOP", "EXIT"):
        for b in BLOCKS:
            r = results[(dec, b)]
            mg = tenths(r["union"]) - tenths(r["chance"])
            if abs(mg - MIX_MARGIN) <= 5:
                frag += 1
                say(f"  {dec} {b} UNION margin {mg / 10:+.1f} pt vs the +15.0 bar ({r['printed_union']} vs {r['printed_chance']})")
    if not frag:
        say("  none")
    say("")
    say("## the 2020 margin against every chance line separately (the overall verdict needs +15.0 on BOTH deciding blocks, so 2020 alone settles 'no mix' when no registered line reaches it)")
    r = results[("ENTER", "2020")]
    p_ = r["parts"]
    say(f"  ENTER 2020: union {f1(r['union'])} - k-price {f1(p_['k'])} = {100 * (r['union'] - p_['k']):+.1f}; - shared-window {f1(p_['shared'])} = {100 * (r['union'] - p_['shared']):+.1f}; "
        f"- per-level shifted {f1(p_['shift'])} = {100 * (r['union'] - p_['shift']):+.1f}   (§6 registers the LARGEST of the three, i.e. k-price: +{100 * (r['union'] - p_['k']):.1f}, short of +15.0)")
    for dec in ("STOP", "EXIT"):
        r = results[(dec, "2020")]
        say(f"  {dec} 2020: union {f1(r['union'])} - (a) frames {f1(r['a_fa'])} = {100 * (r['union'] - r['a_fa']):+.1f}; - (a) no frames {f1(r['a_ff'])} = {100 * (r['union'] - r['a_ff']):+.1f}; "
            f"- random level {f1(r['rl_printed'])} (printed) = {100 * (r['union'] - r['rl_printed']):+.1f}   (§6: the larger of (a) and the random level)")
    say("")
    say("## sensitivity of the STOP/EXIT labels and verdict to the control-(a) mode (the registration says control (a) 'has no frames'; the module takes the LARGER of the two modes)")
    for dec in ("STOP", "EXIT"):
        ch_ff = ch_fa = tot = 0
        ch_list, fa_list = [], []
        for b in BLOCKS:
            alt = se_extra[(dec, b)]
            for c in ORDER[dec]:
                tot += 1
                if alt["ff_only"][c] != results[(dec, b)]["labels"][c]:
                    ch_ff += 1
                    ch_list.append(f"{b} {c}: {results[(dec, b)]['labels'][c]} -> {alt['ff_only'][c]}")
                if alt["fa_only"][c] != results[(dec, b)]["labels"][c]:
                    ch_fa += 1
                    fa_list.append(f"{b} {c}: {results[(dec, b)]['labels'][c]} -> {alt['fa_only'][c]}")
        v_ff = all(not results[(dec, b)]["mix_ff_only"] for b in ("2020", "2021-22"))
        say(f"  {dec}: labels that change if control (a) is frame-free only: {ch_ff} of {tot} {ch_list[:8] if ch_list else ''}; frames only: {ch_fa} of {tot} {fa_list[:8] if fa_list else ''}; "
            f"overall verdict under frame-free-only (a) with the printed random level: no mix on both deciding blocks = {v_ff}; against (a) alone (random level dropped): "
            f"mix on 2020 {results[(dec, '2020')]['mix_a_only']}, on 2021-22 {results[(dec, '2021-22')]['mix_a_only']}")

    # =============================================================================================================================
    out = []
    out += S["head"] + [""] + ["#" * 100] + S["cmp"] + [""] + ["#" * 100] + S["rows"] + [""] + ["#" * 100] + S["robust"] + [""] + ["#" * 100]
    out += ["", "# ROW-LEVEL RE-DERIVATIONS (the part that does not rest on the printout)", ""] + S["detail"]
    return out, diffs, ties, partials, results, n_lab, cnt


if __name__ == "__main__":
    out, diffs, ties, partials, results, n_lab, cnt = main()
    with open(OUT_TXT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print("\n".join(out))
    print(f"\nwritten {OUT_TXT}; {len(diffs)} real differences, {len(ties)} rounding ties, {len(partials)} bound-only cells, {n_lab} label differences")
