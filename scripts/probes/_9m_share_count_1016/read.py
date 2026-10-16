#!/usr/bin/env python3
"""THE ONE RUN of the 9M-share-count vs relative-volume read (2026-10-16). The pre-registration lives in
docs/analysis/ep_share_count_vs_rvol_2026-10-16.md §PRE-REGISTRATION; this script refuses if that
section's sha256 differs from prereg.sha256 (written before this file existed).

Reads #684's captured files only; imports #684's study.py read-only (run with PYTHONDONTWRITEBYTECODE=1
so nothing is written into _684/). Writes read.out and read_rows.tsv in this directory. $0, no prod.
"""
from __future__ import annotations

import hashlib
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from common import HERE, NINE_M, SRC, load_rows

import study  # noqa: E402  (#684, on sys.path via common)

DOC = HERE.parents[2] / "docs" / "analysis" / "ep_share_count_vs_rvol_2026-10-16.md"
SEED = 9016
N_PERM = 2000
LABELLED = study.LABELLED

DECISIVE = [
    ("SC_ge9m", "bool", "1", "CLOSE", "D1 gap-day shares >= 9M"),
    ("SC_log_shares", "cont", "HIGHER", "CLOSE", "D2 gap-day shares, top tercile"),
    ("CLOSE_vol_vs_avg50", "cont", "HIGHER", "CLOSE", "D3 gap-day relative volume (vs 50-day avg), top tercile"),
]
SECONDARY = [
    ("PRE_pm_rvol", "cont", "HIGHER", "PRE", "S pre-market relative volume"),
    ("PRE_projected_vol_multiple", "cont", "HIGHER", "PRE", "S projected volume multiple at the scan"),
    ("PRE_vol_20d_shares", "cont", "HIGHER", "PRE", "S 20-day avg shares (the liquidity half of share count)"),
    ("E_log_orb_shares", "cont", "HIGHER", "0945", "E1 shares 09:30-09:44, top tercile"),
    ("E_orb_ge_equiv", "bool", "1", "0945", "E2 shares 09:30-09:44 >= 9M-equivalent"),
    ("O945_orb_vol_vs_20d", "cont", "HIGHER", "0945", "E3 09:30-09:44 shares / 20-day avg daily shares (early RVOL)"),
]


def prereg_hash() -> str:
    t = DOC.read_text(encoding="utf-8")
    a = t.index("## PRE-REGISTRATION")
    marker = "\nEND OF PRE-REGISTRATION\n"
    assert t.count(marker) == 1
    return hashlib.sha256(t[a:t.index(marker) + len(marker)].encode("utf-8")).hexdigest()


def q(vals, p):
    s = sorted(vals)
    if not s:
        return None
    return s[min(len(s) - 1, int(p * (len(s) - 1) + 0.5))]


def fmt(x, nd=1):
    return "—" if x is None else f"{x:.{nd}f}"


def pct(x):
    return "—" if x is None else f"{100 * x:.1f}%"


def draw(col, kind, fav, disc, held, scored, best_week, best_two, rng):
    """#684 study.main per-feature block, verbatim logic, plus a held-out permutation p (as #686 reports)."""
    dr = [r for r in disc if r.get(col) is not None]
    hr = [r for r in held if r.get(col) is not None]
    res = {"feature": col, "n_disc": len(dr), "n_held": len(hr)}
    if len(dr) < 30:
        res["verdict"] = "no data"
        return res
    cut = study.tercile_cuts([r[col] for r in dr]) if kind == "cont" else None
    fm = study.fav_mask(dr, col, kind, fav, cut)
    labels = [int(r["runner5"]) for r in dr]
    weeks = [r["iso_week"] for r in dr]
    d_obs = study.diff_stat(labels, fm)
    pv = study.perm_p(labels, fm, weeks, d_obs, rng) if d_obs is not None else None
    a = study.auc([r[col] for r in dr], labels, fav) if kind != "bool" else study.auc([float(f) for f in fm], labels, "HIGHER")
    hm = study.fav_mask(hr, col, kind, fav, cut)
    hl = [int(r["runner5"]) for r in hr]
    h_fav = [l for l, f in zip(hl, hm) if f]
    h_rest = [l for l, f in zip(hl, hm) if not f]
    h_d = study.diff_stat(hl, hm)
    h_ok = sum(hl) >= 3 and len(h_fav) >= 8 and len(h_rest) >= 8
    h_p = study.perm_p(hl, hm, [r["iso_week"] for r in hr], h_d, rng) if h_d is not None else None
    dw = [i for i, r in enumerate(dr) if r["iso_week"] != best_week]
    d_w = study.diff_stat([labels[i] for i in dw], [fm[i] for i in dw])
    p_w = study.perm_p([labels[i] for i in dw], [fm[i] for i in dw], [weeks[i] for i in dw], d_w, rng) if d_w is not None else None
    dn = [i for i, r in enumerate(dr) if r["ticker"] not in best_two]
    d_n = study.diff_stat([labels[i] for i in dn], [fm[i] for i in dn])
    p_n = study.perm_p([labels[i] for i in dn], [fm[i] for i in dn], [weeks[i] for i in dn], d_n, rng) if d_n is not None else None
    lab_rows = [r for r in scored if (r["ticker"], r["scan_date"]) in LABELLED and r.get(col) is not None]
    lab_fav = sum(1 for f in study.fav_mask(lab_rows, col, kind, fav, cut) if f)
    if d_obs is None or pv is None:
        verdict = "no data"
    elif d_obs < 0:
        verdict = "fail (wrong way)" + (f", p={1 - pv:.3f} the other way" if (1 - pv) < 0.05 else "")
    elif pv >= 0.05:
        verdict = "can't tell (discovery p >= 0.05)"
    elif not h_ok:
        verdict = "can't tell (held-out too thin)"
    elif h_d is None or h_d <= 0:
        verdict = "can't tell (held-out sign against)"
    elif not (d_w is not None and d_w > 0 and p_w is not None and p_w < 0.05):
        verdict = "can't tell (does not survive dropping the best week)"
    elif not (d_n is not None and d_n > 0 and p_n is not None and p_n < 0.05):
        verdict = "can't tell (does not survive dropping the best two names)"
    else:
        verdict = "PASS " + ("(with held-out p < 0.05)" if (h_p is not None and h_p < 0.05) else f"(sign-only, held-out p {h_p:.3f})")
    res.update({"cut": cut, "n_fav": sum(fm), "rate_fav": study.rate([l for l, f in zip(labels, fm) if f]),
                "n_rest": len(dr) - sum(fm), "rate_rest": study.rate([l for l, f in zip(labels, fm) if not f]),
                "runners_fav": sum(l for l, f in zip(labels, fm) if f), "runners_rest": sum(l for l, f in zip(labels, fm) if not f),
                "diff": d_obs, "auc": a, "p_disc": pv,
                "held_n_fav": len(h_fav), "held_r_fav": sum(h_fav), "held_n_rest": len(h_rest), "held_r_rest": sum(h_rest),
                "held_diff": h_d, "held_ok": h_ok, "held_p": h_p,
                "drop_week_diff": d_w, "drop_week_p": p_w, "drop_two_diff": d_n, "drop_two_p": p_n,
                "labelled_in_fav": lab_fav, "labelled_n": len(lab_rows), "verdict": verdict})
    return res


def line(res, name):
    if res.get("verdict") == "no data":
        return f"{name} | n disc {res['n_disc']} | no data"
    return (f"{name} | disc n {res['n_disc']}: fav {res['runners_fav']}/{res['n_fav']} = {pct(res['rate_fav'])} vs rest {res['runners_rest']}/{res['n_rest']} = {pct(res['rate_rest'])} "
            f"({100 * res['diff']:+.1f}pp) AUC {res['auc']:.3f} p {res['p_disc']:.3f} | held fav {res['held_r_fav']}/{res['held_n_fav']} vs rest {res['held_r_rest']}/{res['held_n_rest']} "
            f"({'—' if res['held_diff'] is None else f'{100 * res['held_diff']:+.1f}pp'}{'' if res['held_ok'] else ' THIN'}, held p {fmt(res['held_p'], 3)}) | "
            f"drop best week {100 * res['drop_week_diff']:+.1f}pp p {res['drop_week_p']:.3f} | drop best two {100 * res['drop_two_diff']:+.1f}pp p {res['drop_two_p']:.3f} | "
            f"labelled in fav {res['labelled_in_fav']} of {res['labelled_n']} | {res['verdict']}")


def auc_rank(vals, labels):
    """Mann-Whitney AUC with average ranks for ties (> 0.5 = higher value, more runners)."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    npos = sum(labels)
    nneg = len(labels) - npos
    if npos == 0 or nneg == 0:
        return None
    rs = sum(r for r, l in zip(ranks, labels) if l)
    return (rs - npos * (npos + 1) / 2) / (npos * nneg)


def pct_rank(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    out = [0.0] * len(vals)
    for k, i in enumerate(order):
        out[i] = k / max(1, len(vals) - 1)
    return out


def paired_auc_test(rows, a_col, b_col, rng):
    rr = [r for r in rows if r.get(a_col) is not None and r.get(b_col) is not None]
    lab = [int(r["runner5"]) for r in rr]
    pa = pct_rank([r[a_col] for r in rr])
    pb = pct_rank([r[b_col] for r in rr])
    a0, b0 = auc_rank(pa, lab), auc_rank(pb, lab)
    obs = a0 - b0
    hits = 0
    for _ in range(N_PERM):
        xa, xb = [], []
        for u, v in zip(pa, pb):
            if rng.random() < 0.5:
                xa.append(v); xb.append(u)
            else:
                xa.append(u); xb.append(v)
        if auc_rank(xa, lab) - auc_rank(xb, lab) >= obs - 1e-12:
            hits += 1
    return len(rr), sum(lab), a0, b0, obs, hits / N_PERM


def group_stats(g):
    xs = [r["run_xadr"] for r in g]
    return (len(g), sum(r["runner5"] for r in g), study.rate([r["runner5"] for r in g]), sum(r["runner8"] for r in g),
            study.rate([r["runner8"] for r in g]), q(xs, 0.9), statistics.median(xs) if xs else None, statistics.mean(xs) if xs else None,
            statistics.median([r["PRE_adr20_pct"] for r in g if r.get("PRE_adr20_pct") is not None]) if g else None)


def table(p, title, groups):
    p(title)
    p("group | n | >=5 ADR n (rate) | >=8 ADR n (rate) | p90 run ADR | median run ADR | mean run ADR | median ADR%")
    for name, g in groups:
        n, r5, rr5, r8, rr8, p90, med, mean, adr = group_stats(g)
        p(f"{name} | {n} | {r5} ({pct(rr5)}) | {r8} ({pct(rr8)}) | {fmt(p90)} | {fmt(med, 2)} | {fmt(mean, 2)} | {fmt(adr)}")
    p("")


def terciles(rows, col, cut):
    lo, hi = cut
    return [("bottom third", [r for r in rows if r.get(col) is not None and r[col] <= lo]),
            ("middle third", [r for r in rows if r.get(col) is not None and lo < r[col] < hi]),
            ("top third", [r for r in rows if r.get(col) is not None and r[col] >= hi])]


def main() -> None:
    out: list[str] = []
    p = out.append
    want = (HERE / "prereg.sha256").read_text().split()[0]
    got = prereg_hash()
    p(f"PRE-REGISTRATION sha256 at run time {got}  (prereg.sha256 {want})  {'MATCH' if got == want else 'MISMATCH'}")
    if got != want:
        print("\n".join(out))
        sys.exit("refusing: the pre-registration section changed after it was hashed")
    rows = load_rows()
    # E2 threshold from VOLUMES ONLY (discovery), printed before any outcome is attached
    ratios = [r["E_orb_share_of_day"] for r in rows if r["block"] == "DISCOVERY" and r.get("E_orb_share_of_day") is not None]
    med_ratio = statistics.median(ratios)
    e_thr = NINE_M * med_ratio
    for r in rows:
        r["E_orb_ge_equiv"] = (1.0 if r["E_orb_shares"] >= e_thr else 0.0) if r.get("E_orb_shares") is not None else None
    p(f"E2 threshold (volumes only, before outcomes): discovery median first-15-min/day share ratio {med_ratio:.4f} (n {len(ratios)}) -> 9M x ratio = {e_thr:,.0f} shares by 09:44")
    study.add_outcomes(rows, study.load_daily())
    scored = [r for r in rows if r["runner5"] is not None]
    r5, r8 = sum(r["runner5"] for r in scored), sum(r["runner8"] for r in scored)
    p(f"ANCHOR vs #684 summary.json: outcome rows {len(scored)} (want 667)  runners>=5 {r5} (want 71)  >=8 {r8} (want 26)")
    assert (len(scored), r5, r8) == (667, 71, 26), "outcome does not match #684"
    disc = [r for r in scored if r["block"] == "DISCOVERY"]
    held = [r for r in scored if r["block"] == "HELD-OUT"]
    p(f"DISCOVERY n {len(disc)} runners>=5 {sum(r['runner5'] for r in disc)} >=8 {sum(r['runner8'] for r in disc)}   HELD-OUT n {len(held)} runners>=5 {sum(r['runner5'] for r in held)} >=8 {sum(r['runner8'] for r in held)}")
    wk = Counter(r["iso_week"] for r in disc if r["runner5"])
    best_week = wk.most_common(1)[0][0]
    best_two = [r["ticker"] for r in sorted(disc, key=lambda r: -r["run_xadr"])[:2]]
    p(f"best discovery week {best_week} ({wk[best_week]} runners); two biggest discovery runners {best_two}  (#684: 2026-W19, ['UMC', 'CRSR'])")
    p("")
    rng = random.Random(SEED)
    p("=== DECISIVE DRAWS (#684 four-condition bar; rates = share reaching >= 5 ADR within 15 sessions of the gap-day close) ===")
    dec = {}
    for col, kind, fav, when, name in DECISIVE:
        dec[col] = draw(col, kind, fav, disc, held, scored, best_week, best_two, rng)
        dec[col]["name"] = name
        p(line(dec[col], name))
    # cross-check D3 vs #684 published row
    pub = {}
    with (SRC / "results.tsv").open() as fh:
        hdr = fh.readline().rstrip("\n").split("\t")
        for ln in fh:
            d = dict(zip(hdr, ln.rstrip("\n").split("\t")))
            pub[d["feature"]] = d
    pr = pub["CLOSE_vol_vs_avg50"]
    same = abs(float(pr["rate_fav"]) - dec["CLOSE_vol_vs_avg50"]["rate_fav"]) < 1e-3 and abs(float(pr["rate_rest"]) - dec["CLOSE_vol_vs_avg50"]["rate_rest"]) < 1e-3
    p(f"D3 cross-check vs #684 results.tsv: published fav {float(pr['rate_fav']):.4f} rest {float(pr['rate_rest']):.4f} p {pr['p_disc']} verdict '{pr['verdict']}' -> {'IDENTICAL rates' if same else 'DIFFERS'}")
    assert same, "D3 does not reproduce #684"
    p("")
    # verdict map (P5)
    pass_sc = [c for c in ("SC_ge9m", "SC_log_shares") if dec[c]["verdict"].startswith("PASS")]
    pass_rv = dec["CLOSE_vol_vs_avg50"]["verdict"].startswith("PASS")
    thin = [c for c in dec if dec[c]["verdict"] == "can't tell (held-out too thin)" or dec[c].get("n_fav", 99) < 30]
    if pass_sc and not pass_rv:
        verdict = "share_count_separates"
    elif pass_rv and not pass_sc:
        verdict = "rvol_separates"
    elif pass_sc and pass_rv:
        best_sc = max(dec[c]["held_diff"] for c in pass_sc)
        hv = dec["CLOSE_vol_vs_avg50"]["held_diff"]
        verdict = "share_count_separates" if best_sc > hv else "rvol_separates" if hv > best_sc else "neither"
    elif thin:
        verdict = "too_few_to_judge"
    else:
        verdict = "neither"
    p(f"VERDICT (P5 map): {verdict}   share-count PASS draws {pass_sc}   relative-volume PASS {pass_rv}   thin draws {thin}")
    p("")
    # head-to-head
    p("=== HEAD-TO-HEAD: AUC(gap-day shares) - AUC(relative volume) for >= 5 ADR, paired swap permutation, one-sided share count > RVOL ===")
    for blk, g in (("DISCOVERY (decisive)", disc), ("HELD-OUT (descriptive)", held), ("ALL (descriptive)", scored)):
        n, nr, a0, b0, d, pv = paired_auc_test(g, "SC_log_shares", "CLOSE_vol_vs_avg50", rng)
        p(f"{blk}: n {n} runners {nr}  AUC shares {a0:.3f}  AUC RVOL {b0:.3f}  difference {d:+.3f}  p {pv:.3f}")
    p("")
    # Bonde's two chart comparisons, our units
    p("=== HIS CHART'S TWO COMPARISONS, IN OUR UNITS ===")
    c3 = study.tercile_cuts([r["CLOSE_vol_vs_avg50"] for r in disc if r.get("CLOSE_vol_vs_avg50") is not None])
    for blk, g in (("ALL", scored), ("DISCOVERY", disc), ("HELD-OUT", held)):
        a = [r for r in g if r["SC_ge9m"] == 1.0]
        b = [r for r in g if r["SC_ge9m"] == 0.0]
        top = [r for r in g if r.get("CLOSE_vol_vs_avg50") is not None and r["CLOSE_vol_vs_avg50"] >= c3[1]]
        bot = [r for r in g if r.get("CLOSE_vol_vs_avg50") is not None and r["CLOSE_vol_vs_avg50"] <= c3[0]]
        ga, gb, gt, gl = group_stats(a), group_stats(b), group_stats(top), group_stats(bot)
        p(f"{blk}: >=9M {ga[1]}/{ga[0]} = {pct(ga[2])} vs <9M {gb[1]}/{gb[0]} = {pct(gb[2])}  ({100 * ((ga[2] or 0) - (gb[2] or 0)):+.1f}pp; mean run ADR {fmt(ga[7], 2)} vs {fmt(gb[7], 2)})   |   "
          f"top RVOL third {gt[1]}/{gt[0]} = {pct(gt[2])} vs bottom third {gl[1]}/{gl[0]} = {pct(gl[2])}  ({100 * ((gt[2] or 0) - (gl[2] or 0)):+.1f}pp; mean run ADR {fmt(gt[7], 2)} vs {fmt(gl[7], 2)})")
    p("")
    # descriptive tables
    sc_cut = study.tercile_cuts([r["SC_log_shares"] for r in disc])
    p(f"share-count tercile cuts (discovery): {10 ** sc_cut[0]:,.0f} / {10 ** sc_cut[1]:,.0f} shares   RVOL tercile cuts: {c3[0]:.2f}x / {c3[1]:.2f}x")
    table(p, "--- gap-day shares, >= 9M vs < 9M (all 667) ---", [(">= 9M", [r for r in scored if r["SC_ge9m"] == 1.0]), ("< 9M", [r for r in scored if r["SC_ge9m"] == 0.0])])
    table(p, "--- gap-day shares by tercile (all 667; discovery cuts) ---", terciles(scored, "SC_log_shares", sc_cut))
    table(p, "--- gap-day relative volume by tercile (all; discovery cuts) ---", terciles(scored, "CLOSE_vol_vs_avg50", c3))
    lq_cut = study.tercile_cuts([r["PRE_vol_20d_shares"] for r in disc if r.get("PRE_vol_20d_shares") is not None])
    table(p, "--- 20-day average shares (the liquidity half of share count) by tercile ---", terciles(scored, "PRE_vol_20d_shares", lq_cut))
    al = [r for r in scored if int(r["alerted"])]
    table(p, "--- ALERTED rows only: >= 9M vs < 9M ---", [(">= 9M", [r for r in al if r["SC_ge9m"] == 1.0]), ("< 9M", [r for r in al if r["SC_ge9m"] == 0.0])])
    table(p, "--- ALERTED rows only: relative volume by tercile ---", terciles(al, "CLOSE_vol_vs_avg50", c3))
    # 2x2: share count x RVOL (does share count add anything inside an RVOL level?)
    p("--- 2x2: >= 9M x relative volume above/below its discovery median (all 667) ---")
    rv_med = statistics.median([r["CLOSE_vol_vs_avg50"] for r in disc if r.get("CLOSE_vol_vs_avg50") is not None])
    for s_name, s_val in ((">= 9M", 1.0), ("< 9M", 0.0)):
        for v_name, cond in (("RVOL above median", lambda x: x > rv_med), ("RVOL at/below median", lambda x: x <= rv_med)):
            g = [r for r in scored if r["SC_ge9m"] == s_val and r.get("CLOSE_vol_vs_avg50") is not None and cond(r["CLOSE_vol_vs_avg50"])]
            n, k5, rr5, k8, rr8, p90, med, mean, adr = group_stats(g)
            p(f"{s_name} & {v_name} ({rv_med:.2f}x) | n {n} | >=5 ADR {k5} ({pct(rr5)}) | >=8 ADR {k8} ({pct(rr8)}) | median ADR% {fmt(adr)}")
    p("")
    # secondaries
    p("=== SECONDARY DRAWS (same machinery, NO verdict mapped) ===")
    sec = {}
    for col, kind, fav, when, name in SECONDARY:
        sec[col] = draw(col, kind, fav, disc, held, scored, best_week, best_two, rng)
        p(f"[{when}] " + line(sec[col], name))
    e_cut = study.tercile_cuts([r["E_log_orb_shares"] for r in disc if r.get("E_log_orb_shares") is not None])
    p(f"early-share tercile cuts (discovery): {10 ** e_cut[0]:,.0f} / {10 ** e_cut[1]:,.0f} shares by 09:44")
    table(p, "--- shares 09:30-09:44 by tercile (rows with >= 12 of 15 minute bars) ---", terciles(scored, "E_log_orb_shares", e_cut))
    n, nr, a0, b0, d, pv = paired_auc_test(disc, "E_log_orb_shares", "O945_orb_vol_vs_20d", rng)
    p(f"early head-to-head (DISCOVERY, descriptive): n {n} runners {nr}  AUC early shares {a0:.3f}  AUC early RVOL {b0:.3f}  difference {d:+.3f}  p {pv:.3f}")
    p("")
    # labelled + biggest runners
    p("=== HIS LABELLED EPs ===")
    for t, d in LABELLED:
        r = next((x for x in scored if x["ticker"] == t and x["scan_date"] == d), None)
        if r is None:
            p(f"{t} {d}: no outcome row")
            continue
        p(f"{t} {d} ({r['block']}): shares {r['SC_shares']:,.0f} (>=9M {int(r['SC_ge9m'])}, tercile {'top' if r['SC_log_shares'] >= sc_cut[1] else 'bottom' if r['SC_log_shares'] <= sc_cut[0] else 'middle'})  "
          f"RVOL {r['CLOSE_vol_vs_avg50']:.2f}x (tercile {'top' if r['CLOSE_vol_vs_avg50'] >= c3[1] else 'bottom' if r['CLOSE_vol_vs_avg50'] <= c3[0] else 'middle'})  run {r['run_xadr']:.1f} ADR ({r['run_pct']:.0f}%)")
    p("")
    p("=== THE 15 BIGGEST RUNS (all 667) — who carries the tail ===")
    p("ticker | scan_date | block | alerted | shares | >=9M | RVOL | ADR% | run ADR | run %")
    for r in sorted(scored, key=lambda r: -r["run_xadr"])[:15]:
        p(f"{r['ticker']} | {r['scan_date']} | {r['block']} | {int(r['alerted'])} | {r['SC_shares']:,.0f} | {int(r['SC_ge9m'])} | {fmt(r.get('CLOSE_vol_vs_avg50'), 2)} | {fmt(r.get('PRE_adr20_pct'))} | {r['run_xadr']:.1f} | {r['run_pct']:.0f}")
    text = "\n".join(out) + "\n"
    (HERE / "read.out").write_text(text)
    with (HERE / "read_rows.tsv").open("w") as fh:
        cols = ["ticker", "scan_date", "block", "iso_week", "alerted", "SC_shares", "SC_ge9m", "CLOSE_vol_vs_avg50", "PRE_vol_20d_shares", "PRE_adr20_pct",
                "E_orb_shares", "E_orb_ge_equiv", "O945_orb_vol_vs_20d", "PRE_pm_rvol", "run_xadr", "run_pct", "runner5", "runner8"]
        fh.write("\t".join(cols) + "\n")
        for r in scored:
            fh.write("\t".join("" if r.get(c) is None else (f"{r[c]:.6g}" if isinstance(r[c], float) else str(r[c])) for c in cols) + "\n")
    print(text)


if __name__ == "__main__":
    main()
