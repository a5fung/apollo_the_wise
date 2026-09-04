"""#623 — the pre-registered analysis (_623_PREREGISTERED.md): univariate, interactions,
cap-band comparison, live-lane impact, robustness. Every cell/number here is a fixed item
from that file — nothing new added after seeing R.
"""
import json
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BAND_ORDER = ["<200M", "200-500M", "500M-2B", "2-10B", ">10B"]


def load_master():
    with open(HERE / "_623_master.jsonl") as fh:
        return [json.loads(l) for l in fh]


def settled(rows):
    return [r for r in rows if r["status"] == "settled" and r["realized_r"] is not None]


def clean(rows):
    """Exclude degenerate-stop rows (risk/share <0.3% of entry) — see _623_join.py. This is the
    PRIMARY lens: 13/1590 settled rows are degenerate and their R is noise-amplified by the
    rule-set's own normalization on a near-zero-width ORB range. Reported once, applied
    everywhere below, alongside the unfiltered number for comparison."""
    return [r for r in rows if not r.get("degenerate_stop")]


def spearman(xs, ys):
    n = len(xs)
    if n < 8:
        return None, n
    rx = _rank(xs)
    ry = _rank(ys)
    if np.std(rx) == 0 or np.std(ry) == 0:
        return None, n
    rho = np.corrcoef(rx, ry)[0, 1]
    return round(float(rho), 3), n


def _rank(v):
    arr = np.asarray(v, dtype=float)
    order = arr.argsort()
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(len(arr))
    # average ties
    sorted_arr = arr[order]
    i = 0
    while i < len(arr):
        j = i
        while j + 1 < len(arr) and sorted_arr[j + 1] == sorted_arr[i]:
            j += 1
        if j > i:
            avg = ranks[order[i:j + 1]].mean()
            ranks[order[i:j + 1]] = avg
        i = j + 1
    return ranks


def halves(rows):
    rows = sorted(rows, key=lambda r: r["scan_date"])
    n = len(rows)
    return rows[: n // 2], rows[n // 2 :]


def cell_stats(rows):
    Rs = [r["realized_r"] for r in rows]
    if not Rs:
        return {"n": 0, "mean": None, "sum": None}
    return {"n": len(Rs), "mean": round(statistics.mean(Rs), 3), "sum": round(sum(Rs), 2),
            "win_rate": round(sum(1 for x in Rs if x > 0) / len(Rs) * 100, 1)}


def tercile_labels(vals):
    """Return cut points for tercile split of a list of values."""
    s = sorted(vals)
    n = len(s)
    if n < 9:
        return None
    t1 = s[n // 3]
    t2 = s[2 * n // 3]
    return t1, t2


def tercile_of(v, cuts):
    if cuts is None or v is None:
        return None
    t1, t2 = cuts
    if v <= t1:
        return "low"
    elif v <= t2:
        return "mid"
    else:
        return "high"


def vol_bucket(v):
    """Distribution-shape-driven (not outcome-driven) 3-bucket split — see _623_PREREGISTERED.md
    addendum: a plain tercile degenerates because 73% of values are exactly 0.0."""
    if v is None:
        return None
    if v <= 0:
        return "none"
    elif v < 90:
        return "some"
    else:
        return "strong"


def report_univariate(rows, out):
    out.append("\n=== UNIVARIATE (Spearman rho vs realized_r) — pooled, then per cap band ===")
    params = [
        ("gap_pct", lambda r: r["gap_pct"]),
        ("vol_pct_daily_bars", lambda r: r["vol_pct_daily_bars"]),
        ("dollar_volume_0931", lambda r: r["dollar_volume_0931"]),
        ("market_cap_log", lambda r: np.log10(r["market_cap"]) if r.get("market_cap") else None),
        ("catalyst_ord", lambda r: r["catalyst_ord"]),
        ("tick_dist_sec", lambda r: r["tick_dist_sec"]),
    ]
    for label, getter in params:
        pairs = [(getter(r), r["realized_r"]) for r in rows if getter(r) is not None]
        if len(pairs) < 8:
            out.append(f"  {label:22s}: n={len(pairs)} too thin")
            continue
        xs, ys = zip(*pairs)
        rho, n = spearman(xs, ys)
        sub_rows = [r for r in rows if getter(r) is not None]
        h1, h2 = halves(sub_rows)
        p1 = [(getter(r), r["realized_r"]) for r in h1]
        p2 = [(getter(r), r["realized_r"]) for r in h2]
        rho1 = spearman(*zip(*p1))[0] if len(p1) >= 8 else None
        rho2 = spearman(*zip(*p2))[0] if len(p2) >= 8 else None
        agree = (rho1 is not None and rho2 is not None and
                 ((rho1 >= 0) == (rho2 >= 0)))
        out.append(f"  {label:22s}: rho={rho:+.3f} (n={n})  H1={rho1} (n={len(p1)})  H2={rho2} (n={len(p2)})  "
                   f"sign_agrees={agree}")

    # record_volume_400d_0931 boolean: mean R with/without
    with_rv = [r["realized_r"] for r in rows if r.get("record_volume_400d_0931") is True]
    without_rv = [r["realized_r"] for r in rows if r.get("record_volume_400d_0931") is False]
    out.append(f"  record_volume_400d_0931=True : n={len(with_rv)} meanR={(statistics.mean(with_rv) if with_rv else None)}")
    out.append(f"  record_volume_400d_0931=False: n={len(without_rv)} meanR={(statistics.mean(without_rv) if without_rv else None)}")

    # regime
    out.append("  regime breakdown:")
    by_regime = defaultdict(list)
    for r in rows:
        if r.get("regime"):
            by_regime[r["regime"]].append(r["realized_r"])
    for reg, Rs in sorted(by_regime.items()):
        out.append(f"    {reg:12s} n={len(Rs)} meanR={statistics.mean(Rs):+.3f}")

    # catalyst categorical
    out.append("  catalyst_quality breakdown:")
    by_cat = defaultdict(list)
    for r in rows:
        if r.get("catalyst_quality"):
            by_cat[r["catalyst_quality"]].append(r["realized_r"])
    for cat, Rs in sorted(by_cat.items()):
        out.append(f"    {cat:14s} n={len(Rs)} meanR={statistics.mean(Rs):+.3f}")

    out.append("\n  -- per cap band (gap_pct, vol_pct_daily_bars only, n permitting) --")
    for band in BAND_ORDER:
        sub = [r for r in rows if r["cap_band"] == band]
        if len(sub) < 15:
            out.append(f"  [{band}] n={len(sub)} too thin for band-level correlation")
            continue
        for label, getter in [("gap_pct", lambda r: r["gap_pct"]),
                              ("vol_pct_daily_bars", lambda r: r["vol_pct_daily_bars"])]:
            pairs = [(getter(r), r["realized_r"]) for r in sub if getter(r) is not None]
            if len(pairs) < 8:
                out.append(f"  [{band}] {label}: n={len(pairs)} too thin")
                continue
            xs, ys = zip(*pairs)
            rho, n = spearman(xs, ys)
            out.append(f"  [{band}] {label:20s}: rho={rho:+.3f} (n={n})  band_meanR={statistics.mean([r['realized_r'] for r in sub]):+.3f} band_n={len(sub)}")
        # vol bucket breakdown per band (since the pct is degenerate for correlation, buckets carry the signal)
        vb = defaultdict(list)
        for r in sub:
            if r["vol_pct_daily_bars"] is not None:
                vb[vol_bucket(r["vol_pct_daily_bars"])].append(r["realized_r"])
        parts = []
        for b in ["none", "some", "strong"]:
            Rs = vb.get(b, [])
            parts.append(f"{b}:n={len(Rs)},meanR={(round(statistics.mean(Rs),3) if Rs else None)}")
        out.append(f"  [{band}] vol_bucket: " + "  ".join(parts))


def report_interactions(rows, out):
    out.append("\n=== INTERACTIONS (cells = n, mean R) ===")

    gap_vals = [r["gap_pct"] for r in rows if r["gap_pct"] is not None]
    gap_cuts = tercile_labels(gap_vals)
    vol_vals = [r["vol_pct_daily_bars"] for r in rows if r["vol_pct_daily_bars"] is not None]
    vol_cuts = tercile_labels(vol_vals)
    out.append(f"gap tercile cuts: {gap_cuts}")
    out.append(f"vol_pct_daily_bars tercile cuts: {vol_cuts}")

    out.append("\n-- gap tercile x record_volume_400d_0931 (operator's primary hypothesis) --")
    cells = defaultdict(list)
    for r in rows:
        if r["gap_pct"] is None or r.get("record_volume_400d_0931") is None:
            continue
        g = tercile_of(r["gap_pct"], gap_cuts)
        cells[(g, r["record_volume_400d_0931"])].append(r)
    for g in ["low", "mid", "high"]:
        for rv in [False, True]:
            c = cells.get((g, rv), [])
            st = cell_stats(c)
            out.append(f"  gap={g:5s} record_vol={str(rv):5s}: n={st['n']:4d} meanR={st['mean']}")

    out.append("\n-- gap tercile x vol_bucket (none/some/strong; smoother hypothesis, see addendum) --")
    cells = defaultdict(list)
    for r in rows:
        if r["gap_pct"] is None or r["vol_pct_daily_bars"] is None:
            continue
        g = tercile_of(r["gap_pct"], gap_cuts)
        v = vol_bucket(r["vol_pct_daily_bars"])
        cells[(g, v)].append(r)
    for g in ["low", "mid", "high"]:
        for v in ["none", "some", "strong"]:
            c = cells.get((g, v), [])
            st = cell_stats(c)
            out.append(f"  gap={g:5s} vol={v:6s}: n={st['n']:4d} meanR={st['mean']}")

    out.append("\n-- cap band x gap tercile --")
    cells = defaultdict(list)
    for r in rows:
        if r["cap_band"] is None or r["gap_pct"] is None:
            continue
        g = tercile_of(r["gap_pct"], gap_cuts)
        cells[(r["cap_band"], g)].append(r)
    for band in BAND_ORDER:
        for g in ["low", "mid", "high"]:
            c = cells.get((band, g), [])
            st = cell_stats(c)
            out.append(f"  cap={band:10s} gap={g:5s}: n={st['n']:4d} meanR={st['mean']}")

    out.append("\n-- cap band x vol_bucket (none/some/strong) --")
    cells = defaultdict(list)
    for r in rows:
        if r["cap_band"] is None or r["vol_pct_daily_bars"] is None:
            continue
        v = vol_bucket(r["vol_pct_daily_bars"])
        cells[(r["cap_band"], v)].append(r)
    for band in BAND_ORDER:
        for v in ["none", "some", "strong"]:
            c = cells.get((band, v), [])
            st = cell_stats(c)
            out.append(f"  cap={band:10s} vol={v:6s}: n={st['n']:4d} meanR={st['mean']}")

    out.append("\n-- cap band x record_volume_400d_0931 --")
    cells = defaultdict(list)
    for r in rows:
        if r["cap_band"] is None or r.get("record_volume_400d_0931") is None:
            continue
        cells[(r["cap_band"], r["record_volume_400d_0931"])].append(r)
    for band in BAND_ORDER:
        for rv in [False, True]:
            c = cells.get((band, rv), [])
            st = cell_stats(c)
            out.append(f"  cap={band:10s} record_vol={str(rv):5s}: n={st['n']:4d} meanR={st['mean']}")

    out.append("\n-- THREE-WAY: cap(<500M vs >=500M) x gap tercile x vol_bucket(none/some/strong) --")
    out.append("   (record_volume_400d_0931 folded into 'strong' — true on only 7/939 rows, too rare alone)")
    cells = defaultdict(list)
    for r in rows:
        if r["cap_band"] is None or r["gap_pct"] is None or r["vol_pct_daily_bars"] is None:
            continue
        capgrp = "<500M" if r["cap_band"] in ("<200M", "200-500M") else ">=500M"
        g = tercile_of(r["gap_pct"], gap_cuts)
        v = vol_bucket(r["vol_pct_daily_bars"])
        cells[(capgrp, g, v)].append(r)
    for capgrp in ["<500M", ">=500M"]:
        for g in ["low", "mid", "high"]:
            for v in ["none", "some", "strong"]:
                c = cells.get((capgrp, g, v), [])
                st = cell_stats(c)
                flag = "" if st["n"] >= 10 else "  (n<10, not a finding)"
                out.append(f"  cap={capgrp:7s} gap={g:5s} vol={v:6s}: n={st['n']:4d} meanR={st['mean']}{flag}")


def report_live_lane(rows, out):
    out.append("\n=== LIVE-LANE IMPACT ===")
    admitted_today = [r for r in rows if r["admitted_today"]]
    st = cell_stats(admitted_today)
    out.append(f"admitted_today (ever_scored & best_score_tier==HIGH): n={st['n']} meanR={st['mean']} sumR={st['sum']}")
    # Example candidate rule: record_volume_400d_0931 OR gap high tercile, restricted to those with data
    gap_vals = [r["gap_pct"] for r in rows if r["gap_pct"] is not None]
    gap_cuts = tercile_labels(gap_vals)
    for rule_name, pred in [
        ("record_volume_400d_0931==True (strict)", lambda r: r.get("record_volume_400d_0931") is True),
        ("vol_bucket==strong (>=90th pctile)", lambda r: r["vol_pct_daily_bars"] is not None
            and vol_bucket(r["vol_pct_daily_bars"]) == "strong"),
        ("gap_high_tercile AND vol_bucket==strong", lambda r: tercile_of(r["gap_pct"], gap_cuts) == "high"
            and r["vol_pct_daily_bars"] is not None and vol_bucket(r["vol_pct_daily_bars"]) == "strong"),
    ]:
        newly_admitted = [r for r in rows if pred(r) and not r["admitted_today"]]
        would_drop = [r for r in admitted_today if not pred(r)]
        st_new = cell_stats([r for r in newly_admitted if r["status"] == "settled" and r["realized_r"] is not None])
        st_drop = cell_stats([r for r in would_drop if r["status"] == "settled" and r["realized_r"] is not None])
        out.append(f"\n  RULE: {rule_name}")
        out.append(f"    newly admitted (not admitted today): n={len(newly_admitted)} settled_n={st_new['n']} meanR={st_new['mean']}")
        out.append(f"    would drop (admitted today, fails rule): n={len(would_drop)} settled_n={st_drop['n']} meanR={st_drop['mean']}")


def report_robustness(rows, out):
    out.append("\n=== ROBUSTNESS (headline cells: n, split-half, minus top contributor) ===")
    gap_vals = [r["gap_pct"] for r in rows if r["gap_pct"] is not None]
    gap_cuts = tercile_labels(gap_vals)
    cell = [r for r in rows if r["gap_pct"] is not None and r["vol_pct_daily_bars"] is not None
            and vol_bucket(r["vol_pct_daily_bars"]) == "strong" and tercile_of(r["gap_pct"], gap_cuts) == "high"]
    st = cell_stats(cell)
    out.append(f"gap=high & vol_bucket=strong: n={st['n']} meanR={st['mean']}")
    if cell:
        h1, h2 = halves(cell)
        out.append(f"  split-half: H1 n={len(h1)} meanR={(statistics.mean([r['realized_r'] for r in h1]) if h1 else None)}  "
                   f"H2 n={len(h2)} meanR={(statistics.mean([r['realized_r'] for r in h2]) if h2 else None)}")
        top = max(cell, key=lambda r: abs(r["realized_r"]))
        rest = [r for r in cell if r is not top]
        out.append(f"  top contributor: {top['ticker']} {top['scan_date']} R={top['realized_r']:+.2f}")
        out.append(f"  minus top: n={len(rest)} meanR={(statistics.mean([r['realized_r'] for r in rest]) if rest else None)}")


def report_headline_degenerate_check(all_rows, clean_rows, out):
    out.append("=== HEADLINE DATA-QUALITY FINDING (read this before any number below) ===")
    st_all = cell_stats(all_rows)
    st_clean = cell_stats(clean_rows)
    degen = [r for r in all_rows if r.get("degenerate_stop")]
    out.append(f"ALL settled rows:   n={st_all['n']} meanR={st_all['mean']} sumR={st_all['sum']}")
    out.append(f"CLEAN (ex degenerate-stop, {len(degen)} rows removed): n={st_clean['n']} meanR={st_clean['mean']} sumR={st_clean['sum']}")
    out.append("Two rows (ATI 2026-08-06 R=+119.5, AVBC 2026-07-24 R=+67.5 -- both near-zero-width "
               "ORB ranges producing noise-amplified R under the rule-set's own R-normalization, "
               "not real economic outcomes) account for +186.97 of the population's +167.85 total R. "
               "The WHOLE POPULATION's apparent positive edge is an artifact of two rows. CLEAN is "
               "used for every number in the rest of this report; ALL is not used again.")
    top_degen = sorted(degen, key=lambda r: -abs(r["realized_r"]))[:5]
    for r in top_degen:
        out.append(f"    {r['ticker']:6s} {r['scan_date']} entry={r['entry_px']} stop={r['stop']} R={r['realized_r']:+.2f}")


def main():
    all_rows = settled(load_master())
    rows = clean(all_rows)
    out = [f"n settled with realized_r (ALL): {len(all_rows)}  (CLEAN, used below): {len(rows)}"]
    report_headline_degenerate_check(all_rows, rows, out)
    report_univariate(rows, out)
    report_interactions(rows, out)
    report_live_lane(rows, out)
    report_robustness(rows, out)
    txt = "\n".join(out)
    (HERE / "_623_analysis_out.txt").write_text(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
