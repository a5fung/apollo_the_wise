"""#327 hypothesis tests — the `report` phase: reads hyp_rows_*.tsv, applies the pre-registered bars
(hyptests.py docstring), writes hyp_report.txt + hyp_summary.json. No settlement is computed here."""
from __future__ import annotations

import json
import random
import statistics
from collections import Counter, defaultdict

import hyptests as H
from hyptests import HERE, N_PERM, SEED, MIN_HELDOUT, TAIL_R, PATTERNS, K_POST, H1C_N, H13_RULES, N_DRAWS, NOISE_MAX, FAMILY_MIN, _f
import rerun
import reentry
from shared.operator_labelled_eps import OPERATOR_LABELLED_EPS

SPLITS = ("DISC", "HOA", "B")


def rd(path):
    return rerun.read_tsv(HERE / path)


def fl(v):
    return _f(v)


def mean(v):
    return statistics.mean(v) if v else None


def fm(x, f="{:+.2f}"):
    return "—" if x is None else f.format(x)


def sign(x):
    return "—" if x is None else ("+" if x > 0 else ("-" if x < 0 else "0"))


# ── permutation machinery ─────────────────────────────────────────────────────────────────────────────

def perm_paired(diffs, weeks, seed=SEED):
    """Sign-flip WHOLE week blocks; one-sided p in the observed direction."""
    if len(diffs) < 2:
        return None
    obs = sum(diffs) / len(diffs)
    blocks = defaultdict(list)
    for i, wk in enumerate(weeks):
        blocks[wk].append(diffs[i])
    sums = [sum(b) for b in blocks.values()]
    rng = random.Random(seed)
    n = len(diffs)
    cnt = 0
    for _ in range(N_PERM):
        s = sum(x if rng.random() < 0.5 else -x for x in sums) / n
        if (obs >= 0 and s >= obs - 1e-12) or (obs < 0 and s <= obs + 1e-12):
            cnt += 1
    return (cnt + 1) / (N_PERM + 1)


def perm_group(vals, labels, weeks, seed=SEED):
    """Shuffle labels WITHIN each week; statistic = mean(label 1) - mean(label 0); one-sided p in the observed direction."""
    v1 = [v for v, l in zip(vals, labels) if l]
    v0 = [v for v, l in zip(vals, labels) if not l]
    if len(v1) < 2 or len(v0) < 2:
        return None
    obs = mean(v1) - mean(v0)
    blocks = defaultdict(list)
    for i, wk in enumerate(weeks):
        blocks[wk].append(i)
    rng = random.Random(seed)
    labs = list(labels)
    cnt = 0
    n1, n0 = len(v1), len(v0)
    for _ in range(N_PERM):
        s1 = 0.0
        s0 = 0.0
        for idxs in blocks.values():
            bl = [labs[i] for i in idxs]
            rng.shuffle(bl)
            for i, l in zip(idxs, bl):
                if l:
                    s1 += vals[i]
                else:
                    s0 += vals[i]
        s = s1 / n1 - s0 / n0
        if (obs >= 0 and s >= obs - 1e-12) or (obs < 0 and s <= obs + 1e-12):
            cnt += 1
    return (cnt + 1) / (N_PERM + 1)


def drop2(pairs):
    """pairs = [(ticker, value)] -> (sum after dropping the two best tickers by summed value, [names])."""
    by = defaultdict(float)
    for t, v in pairs:
        by[t] += v
    top = sorted(by.items(), key=lambda kv: -kv[1])[:2]
    return sum(by.values()) - sum(v for _, v in top), [f"{t} {v:+.1f}" for t, v in top]


def tail_sets():
    alerts = rd("alerts.tsv")
    keys = {(a["ticker"], a["alert_date"]) for a in alerts}
    labelled = {(e.ticker, e.alert_date) for e in OPERATOR_LABELLED_EPS if (e.ticker, e.alert_date) in keys}
    runners = reentry.load_runners()
    return labelled, runners


def tail_count(items, labelled, runners, key="v"):
    """items: rows with ticker, ep_date and a per-fire R under `key`; returns (labelled kept, labelled fired, runners kept, runners fired)."""
    best = defaultdict(lambda: None)
    for it in items:
        k = (it["ticker"], it["ep_date"])
        if it.get(key) is None:
            continue
        best[k] = it[key] if best[k] is None else max(best[k], it[key])
    lk = sum(1 for k in labelled if best.get(k) is not None and best[k] >= TAIL_R - 1e-9)
    lf = sum(1 for k in labelled if best.get(k) is not None)
    rk = sum(1 for k in runners if best.get(k) is not None and best[k] >= TAIL_R - 1e-9)
    rf = sum(1 for k in runners if best.get(k) is not None)
    return lk, lf, rk, rf


def paired_stats(items, labelled, runners, name):
    """items: {ticker, ep_date, split, week, v, b, fv, fb}. Per split: n, means, diff, drop-2, p (DISC), tail, worst, losses<-1.5."""
    out = {"name": name}
    for sp in SPLITS:
        it = [x for x in items if x["split"] == sp and x["v"] is not None and x["b"] is not None]
        d = [x["v"] - x["b"] for x in it]
        res = {"n": len(it), "names": len({x["ticker"] for x in it}), "mean_v": mean([x["v"] for x in it]), "mean_b": mean([x["b"] for x in it]),
               "mean_diff": mean(d), "sum_diff": sum(d) if d else None, "worst_v": min([x["v"] for x in it]) if it else None,
               "worst_b": min([x["b"] for x in it]) if it else None,
               "n_loss_gt15_v": sum(1 for x in it if x["v"] < -1.5), "n_loss_gt15_b": sum(1 for x in it if x["b"] < -1.5),
               "n_stop_v": None}
        if d:
            res["drop2_sum"], res["drop2_names"] = drop2([(x["ticker"], x["v"] - x["b"]) for x in it])
        if sp == "DISC" and d:
            res["p"] = perm_paired(d, [x["week"] for x in it])
        fi = [x for x in items if x["split"] == sp and x.get("fv") is not None and x.get("fb") is not None]
        res["fill_n"] = len(fi)
        res["fill_mean_diff"] = mean([x["fv"] - x["fb"] for x in fi])
        res["fill_mean_v"] = mean([x["fv"] for x in fi])
        lk, lf_, rk, rf = tail_count(it, labelled, runners, "v")
        lkb, _, rkb, _ = tail_count(it, labelled, runners, "b")
        res["tail"] = {"labelled_kept": lk, "labelled_fired": lf_, "runners_kept": rk, "runners_fired": rf, "labelled_kept_base": lkb, "runners_kept_base": rkb}
        out[sp] = res
    D_ = out["DISC"]
    disc_pass = (D_["n"] > 0 and D_["mean_diff"] is not None and D_["mean_diff"] > 0 and D_.get("drop2_sum", 0) > 0
                 and D_.get("p") is not None and D_["p"] < 0.05 and (D_["fill_mean_diff"] is not None and D_["fill_mean_diff"] > 0))
    ho = {}
    for sp in ("HOA", "B"):
        r = out[sp]
        ho[sp] = "can't tell" if r["n"] < MIN_HELDOUT else sign(r["mean_diff"])
    out["disc_pass"] = disc_pass
    out["heldout"] = ho
    out["verdict"] = ("holds" if disc_pass and ho["HOA"] == "+" and ho["B"] == "+" else
                      ("can't tell (held-out thin)" if disc_pass and ("can't tell" in ho.values()) else "fails"))
    return out


def fmt_paired(o):
    ls = [f"  {o['name']}"]
    for sp in SPLITS:
        r = o[sp]
        t = r["tail"]
        ls.append(f"    {sp:4s} n {r['n']:3d} ({r['names']} names) | variant {fm(r['mean_v'])} vs base {fm(r['mean_b'])} -> diff {fm(r['mean_diff'])}R/fire "
                  f"(sum {fm(r['sum_diff'], '{:+.1f}')}; drop-2 {fm(r.get('drop2_sum'), '{:+.1f}')} {r.get('drop2_names', '')}; p {fm(r.get('p'), '{:.3f}')}) | "
                  f"fillable n {r['fill_n']} diff {fm(r['fill_mean_diff'])} | worst {fm(r['worst_v'])} (base {fm(r['worst_b'])}) | losses<-1.5R {r['n_loss_gt15_v']} (base {r['n_loss_gt15_b']}) | "
                  f"tail: labelled {t['labelled_kept']}/{t['labelled_fired']} (base {t['labelled_kept_base']}), runners {t['runners_kept']}/{t['runners_fired']} (base {t['runners_kept_base']})")
    ls.append(f"    => DISC {'pass' if o['disc_pass'] else 'fail'} · HOA {o['heldout']['HOA']} · B {o['heldout']['B']} · VERDICT {o['verdict']}")
    return ls


def group_stats(items, labelled, runners, name, val="v"):
    """items: {ticker, ep_date, split, week, g (0/1), v}; label 1 predicted better."""
    out = {"name": name}
    for sp in SPLITS:
        it = [x for x in items if x["split"] == sp and x.get(val) is not None and x.get("g") is not None]
        v1 = [x[val] for x in it if x["g"]]
        v0 = [x[val] for x in it if not x["g"]]
        res = {"n1": len(v1), "n0": len(v0), "mean1": mean(v1), "mean0": mean(v0),
               "diff": (mean(v1) - mean(v0)) if (v1 and v0) else None}
        if v1 and v0:
            # drop-2: remove the two best tickers of group 1 by summed value
            by = defaultdict(float)
            for x in it:
                if x["g"]:
                    by[x["ticker"]] += x[val]
            top = {t for t, _ in sorted(by.items(), key=lambda kv: -kv[1])[:2]}
            v1d = [x[val] for x in it if x["g"] and x["ticker"] not in top]
            res["diff_drop2"] = (mean(v1d) - mean(v0)) if v1d else None
            res["drop2_names"] = sorted(top)
        if sp == "DISC" and v1 and v0:
            res["p"] = perm_group([x[val] for x in it], [x["g"] for x in it], [x["week"] for x in it])
        out[sp] = res
    D_ = out["DISC"]
    out["disc_pass"] = bool(D_.get("diff") is not None and D_["diff"] > 0 and (D_.get("diff_drop2") or 0) > 0 and D_.get("p") is not None and D_["p"] < 0.05)
    ho = {sp: ("can't tell" if min(out[sp]["n1"], out[sp]["n0"]) < MIN_HELDOUT else sign(out[sp]["diff"])) for sp in ("HOA", "B")}
    out["heldout"] = ho
    out["verdict"] = ("holds" if out["disc_pass"] and ho["HOA"] == "+" and ho["B"] == "+" else
                      ("can't tell (held-out thin)" if out["disc_pass"] and "can't tell" in ho.values() else "fails"))
    return out


def fmt_group(o, l1="group 1", l0="group 0"):
    ls = [f"  {o['name']}"]
    for sp in SPLITS:
        r = o[sp]
        ls.append(f"    {sp:4s} {l1} n {r['n1']:3d} mean {fm(r['mean1'])} | {l0} n {r['n0']:3d} mean {fm(r['mean0'])} | diff {fm(r['diff'])} "
                  f"(drop-2 {fm(r.get('diff_drop2'))} {r.get('drop2_names', '')}; p {fm(r.get('p'), '{:.3f}')})")
    ls.append(f"    => DISC {'pass' if o['disc_pass'] else 'fail'} · HOA {o['heldout']['HOA']} · B {o['heldout']['B']} · VERDICT {o['verdict']}")
    return ls


# ── H2 ─────────────────────────────────────────────────────────────────────────────────────────────────

def report_h2(S, L):
    rows = rd("hyp_rows_h2.tsv")
    L.append("\n" + "=" * 120 + "\nH2 — is the reclaim patterns' entry edge a volatility-timing artefact? (+2-first AND -1-first rates, fires vs controls)\n" + "=" * 120)
    L.append("  rates = share of NON-abstaining walks resolved by session 10 as +2 first (edge) / -1 first (the artefact tell); pess = stop-first on a straddle.")
    S["H2"] = {}
    for pat in PATTERNS:
        S["H2"][pat] = {}
        for barrier in ("orig", "scaled", "scaled_partial"):
            for bnd in ("pess", "opt"):
                if barrier == "scaled_partial" and bnd == "opt":
                    continue
                for ek in ("rec", "close", "fill"):
                    key = f"{barrier}/{bnd}/{ek}"
                    res = {}
                    for sp in SPLITS:
                        fr = [r for r in rows if r["pattern"] == pat and r["barrier"] == barrier and r["bound"] == bnd and r["split"] == sp and r["is_fire"] == "1" and r["entry_kind"] == ek and r["outcome"] != "abstain"]
                        cb = "scaled" if barrier == "scaled_partial" else barrier
                        co = [r for r in rows if r["pattern"] == pat and r["barrier"] == cb and r["bound"] == bnd and r["split"] == sp and r["is_fire"] == "0" and r["outcome"] != "abstain"]
                        nf, nc = len(fr), len(co)
                        f2 = 100 * sum(1 for r in fr if r["outcome"] == "target") / nf if nf else None
                        f1 = 100 * sum(1 for r in fr if r["outcome"] == "stop") / nf if nf else None
                        c2 = 100 * sum(1 for r in co if r["outcome"] == "target") / nc if nc else None
                        c1 = 100 * sum(1 for r in co if r["outcome"] == "stop") / nc if nc else None
                        rr = {"n_fire": nf, "n_ctl": nc, "fire_plus2": f2, "fire_minus1": f1, "ctl_plus2": c2, "ctl_minus1": c1,
                              "gap_plus2": (f2 - c2) if (f2 is not None and c2 is not None) else None,
                              "gap_minus1": (f1 - c1) if (f1 is not None and c1 is not None) else None,
                              "fire_abstain": sum(1 for r in rows if r["pattern"] == pat and r["barrier"] == barrier and r["bound"] == bnd and r["split"] == sp and r["is_fire"] == "1" and r["entry_kind"] == ek and r["outcome"] == "abstain"),
                              "fire_open": sum(1 for r in fr if r["outcome"] == "open"), "ctl_open": sum(1 for r in co if r["outcome"] == "open")}
                        if nf and nc:
                            # drop the two fire names with the most +2 hits (their controls too)
                            hits = Counter(r["ticker"] for r in fr if r["outcome"] == "target")
                            top = {t for t, _ in hits.most_common(2)}
                            fr2 = [r for r in fr if r["ticker"] not in top]; co2 = [r for r in co if r["ticker"] not in top]
                            if fr2 and co2:
                                rr["gap_plus2_drop2"] = 100 * sum(1 for r in fr2 if r["outcome"] == "target") / len(fr2) - 100 * sum(1 for r in co2 if r["outcome"] == "target") / len(co2)
                                rr["drop2_names"] = sorted(top)
                            if sp == "DISC":
                                allr = fr + co
                                rr["p"] = perm_group([1.0 if r["outcome"] == "target" else 0.0 for r in allr], [r["is_fire"] == "1" for r in allr], [r["week"] for r in allr])
                                rr["p_minus1"] = perm_group([1.0 if r["outcome"] == "stop" else 0.0 for r in allr], [r["is_fire"] == "1" for r in allr], [r["week"] for r in allr])
                            if barrier != "orig":
                                s1f = [r for r in fr if r["session_idx"] == "1"]; s1c = [r for r in co if r["session_idx"] == "1"]
                                rr["s1_n_fire"], rr["s1_n_ctl"] = len(s1f), len(s1c)
                                if s1f and s1c:
                                    rr["s1_gap_plus2"] = 100 * sum(1 for r in s1f if r["outcome"] == "target") / len(s1f) - 100 * sum(1 for r in s1c if r["outcome"] == "target") / len(s1c)
                                    rr["s1_gap_minus1"] = 100 * sum(1 for r in s1f if r["outcome"] == "stop") / len(s1f) - 100 * sum(1 for r in s1c if r["outcome"] == "stop") / len(s1c)
                            rr["y_over_adr_fire_median"] = statistics.median([fl(r["y_over_adr"]) for r in fr])
                            rr["y_over_adr_ctl_median"] = statistics.median([fl(r["y_over_adr"]) for r in co])
                        res[sp] = rr
                    S["H2"][pat][key] = res
        # print the essentials per pattern
        L.append(f"\n  {pat}")
        for key in ("orig/pess/rec", "orig/pess/close", "orig/pess/fill", "scaled/pess/rec", "scaled/pess/close", "scaled/pess/fill", "scaled_partial/pess/rec", "scaled/opt/rec"):
            res = S["H2"][pat][key]
            for sp in SPLITS:
                r = res[sp]
                if not r["n_fire"]:
                    continue
                L.append(f"    {key:24s} {sp:4s} fires {r['n_fire']:3d} (abstain {r['fire_abstain']}) vs ctl {r['n_ctl']:4d} | +2 first {fm(r['fire_plus2'], '{:.1f}')}% vs {fm(r['ctl_plus2'], '{:.1f}')}% -> {fm(r['gap_plus2'], '{:+.1f}')} pts"
                         f" (drop-2 {fm(r.get('gap_plus2_drop2'), '{:+.1f}')} {r.get('drop2_names', '')}; p {fm(r.get('p'), '{:.3f}')}) | -1 first {fm(r['fire_minus1'], '{:.1f}')}% vs {fm(r['ctl_minus1'], '{:.1f}')}% -> {fm(r['gap_minus1'], '{:+.1f}')} pts (p {fm(r.get('p_minus1'), '{:.3f}')})"
                         + (f" | yardstick/ADR fire {fm(r.get('y_over_adr_fire_median'), '{:.2f}')} ctl {fm(r.get('y_over_adr_ctl_median'), '{:.2f}')}; session-1 fires {r.get('s1_n_fire')}: +2 gap {fm(r.get('s1_gap_plus2'), '{:+.1f}')} -1 gap {fm(r.get('s1_gap_minus1'), '{:+.1f}')}" if key.startswith("scaled") else ""))
        # verdict per pattern on the pre-registered bar: scaled/pess/rec on DISC
        d = S["H2"][pat]["scaled/pess/rec"]["DISC"]
        dfill = S["H2"][pat]["scaled/pess/fill"]["DISC"]
        g2, g1 = d.get("gap_plus2"), d.get("gap_minus1")
        art = g1 is not None and g2 is not None and g1 >= 0.5 * abs(g2)
        disc_pass = (g2 is not None and g2 >= 5 and not art and d.get("p") is not None and d["p"] < 0.05 and (d.get("gap_plus2_drop2") or 0) >= 5
                     and dfill.get("gap_plus2") is not None and dfill["gap_plus2"] > 0)
        ho = {}
        for sp in ("HOA", "B"):
            r = S["H2"][pat]["scaled/pess/rec"][sp]
            ho[sp] = "can't tell" if r["n_fire"] < MIN_HELDOUT else sign(r.get("gap_plus2"))
        verdict = "holds" if disc_pass and ho["HOA"] == "+" and ho["B"] == "+" else ("can't tell (held-out thin)" if disc_pass and "can't tell" in ho.values() else "fails")
        orig = S["H2"][pat]["orig/pess/rec"]["DISC"]
        S["H2"][pat]["verdict"] = {"disc_pass": disc_pass, "artefact_tell": art, "heldout": ho, "verdict": verdict,
                                   "orig_gap_plus2": orig.get("gap_plus2"), "orig_gap_minus1": orig.get("gap_minus1"), "scaled_gap_plus2": g2, "scaled_gap_minus1": g1}
        L.append(f"    => original barriers DISC: +2 gap {fm(orig.get('gap_plus2'), '{:+.1f}')} / -1 gap {fm(orig.get('gap_minus1'), '{:+.1f}')}; scaled: +2 gap {fm(g2, '{:+.1f}')} / -1 gap {fm(g1, '{:+.1f}')} "
                 f"-> artefact tell (-1 gap >= half the +2 gap) {art}; DISC {'pass' if disc_pass else 'fail'} · HOA {ho['HOA']} · B {ho['B']} · VERDICT {verdict}")


# ── H1b / H1c / H3 from hyp_rows_stops.tsv ──────────────────────────────────────────────────────────────

def report_stops(S, L, labelled, runners):
    rows = rd("hyp_rows_stops.tsv")
    for r in rows:
        for k in list(r):
            if k.endswith("_r") or k in ("stop_w", "rpost", "rpost_over_adr", "low_age_bars", "vol_low_bar", "vol_fire_bar", "vol_prior_mean", "adr", "entry", "stop") or k.endswith("_w") or k.endswith("_low"):
                r[k] = fl(r[k])
        r["fire_minute"] = int(float(r["fire_minute"])) if r["fire_minute"] else None
        r["n_prior_bars"] = int(r["n_prior_bars"]) if r.get("n_prior_bars") else None
        r["lane_stop_sessions"] = int(r["lane_stop_sessions"]) if r.get("lane_stop_sessions") else None
    S["stops_pop"] = {"fires": len(rows), "lane_readable": sum(1 for r in rows if r["lane_trail_r"] is not None),
                      "lane_fill_readable": sum(1 for r in rows if r["lane_fill_trail_r"] is not None),
                      "lane_floored_lt0.5pct": sum(1 for r in rows if r["stop_w"] is not None and r["stop_w"] < 0.5),
                      "rpost_one_session_only": sum(1 for r in rows if r["rpost_n"] == "1")}
    # H1b
    L.append("\n" + "=" * 120 + "\nH1b — stop scaled to the stock's range AFTER the gap (k x mean high-low of the last <=3 post-gap sessions, EP day = session 0), trail arm; vs the lane's own stop AND vs 1xADR pre-EP\n" + "=" * 120)
    L.append(f"  population: {len(rows)} first fires; lane readable {S['stops_pop']['lane_readable']}; fillable readable {S['stops_pop']['lane_fill_readable']}; "
             f"lane stops under 0.5% wide {S['stops_pop']['lane_floored_lt0.5pct']} (kept in the primary read, shown ex-floored beside); fires whose post-gap window is the EP day alone {S['stops_pop']['rpost_one_session_only']}")
    S["H1b"] = {}
    for kk in K_POST:
        lab = f"h1b_{int(kk*100):03d}"
        med_w = statistics.median([r[f"{lab}_rec_w"] for r in rows if r.get(f"{lab}_rec_w") is not None])
        med_lane = statistics.median([r["stop_w"] for r in rows if r["stop_w"] is not None])
        items = [{"ticker": r["ticker"], "ep_date": r["ep_date"], "split": r["split"], "week": r["week"], "v": r.get(f"{lab}_rec_trail_r"), "b": r["lane_trail_r"],
                  "fv": r.get(f"{lab}_fill_trail_r"), "fb": r["lane_fill_trail_r"]} for r in rows]
        o = paired_stats(items, labelled, runners, f"k={kk} x post-gap range (median width {med_w:.2f}% vs lane {med_lane:.2f}%), trail, vs the lane's own stop")
        S["H1b"][f"{lab}_vs_lane"] = o
        L.extend(fmt_paired(o))
        items2 = [{"ticker": r["ticker"], "ep_date": r["ep_date"], "split": r["split"], "week": r["week"], "v": r.get(f"{lab}_rec_trail_r"), "b": r["adr100_trail_r"],
                   "fv": None, "fb": None} for r in rows]
        o2 = paired_stats(items2, labelled, runners, f"k={kk} x post-gap range vs 1xADR pre-EP (same fires, trail) — descriptive")
        S["H1b"][f"{lab}_vs_adr100"] = o2
        L.extend(fmt_paired(o2)[:4])
        # ex-floored
        itx = [x for x, r in zip(items, rows) if r["stop_w"] is not None and r["stop_w"] >= 0.5]
        ox = paired_stats(itx, labelled, runners, f"   (same, ex lane stops under 0.5%)")
        L.append(f"    ex-floored: DISC n {ox['DISC']['n']} diff {fm(ox['DISC']['mean_diff'])} drop-2 {fm(ox['DISC'].get('drop2_sum'), '{:+.1f}')} p {fm(ox['DISC'].get('p'), '{:.3f}')}")
        # per pattern (descriptive)
        for pat in PATTERNS:
            it = [x for x, r in zip(items, rows) if r["rung"] == pat and x["split"] == "DISC" and x["v"] is not None and x["b"] is not None]
            if it:
                L.append(f"      DISC {pat:20s} n {len(it):3d} diff {fm(mean([x['v'] - x['b'] for x in it]))} (variant {fm(mean([x['v'] for x in it]))}, lane {fm(mean([x['b'] for x in it]))})")
    # H1c (c1)
    L.append("\n" + "=" * 120 + "\nH1c — the age / testedness of the stop-defining low\n" + "=" * 120)
    S["H1c"] = {}
    for N in H1C_N:
        lab = f"h1c_first{N}"
        items = [{"ticker": r["ticker"], "ep_date": r["ep_date"], "split": r["split"], "week": r["week"], "v": r.get(f"{lab}_rec_trail_r"), "b": r["lane_trail_r"],
                  "fv": r.get(f"{lab}_fill_trail_r"), "fb": r["lane_fill_trail_r"]} for r in rows if r.get(f"{lab}_rec_status") in ("settled", "marked")]
        n_before = sum(1 for r in rows if r.get(f"{lab}_status") == "fire_before_N")
        n_killed = sum(1 for r in rows if r.get(f"{lab}_rec_status") == "killed")
        o = paired_stats(items, labelled, runners, f"(c1) stop = the fire session's first-{N}-minute low, fires at/after {'10:00' if N == 30 else '10:30'} ET (fires before that {n_before}; stop at/above entry {n_killed}), trail, vs the lane's own stop")
        S["H1c"][lab] = o
        L.extend(fmt_paired(o))
    # (c2) age terciles on the lane's own arm
    same = [r for r in rows if r.get("low_age_kind") == "same_session" and r["low_age_bars"] is not None and r["lane_trail_r"] is not None]
    earl = [r for r in rows if r.get("low_age_kind") == "earlier_session" and r["lane_trail_r"] is not None]
    disc_same = sorted([r["low_age_bars"] for r in same if r["split"] == "DISC"])
    if disc_same:
        t1, t2 = disc_same[len(disc_same) // 3], disc_same[2 * len(disc_same) // 3]
    else:
        t1 = t2 = 0
    L.append(f"  (c2) age of the stop-defining low at the fire (5-min bars since the low printed; DISC tercile cuts at {t1} and {t2} bars); "
             f"same-session lows {len(same)}, earlier-session lows {len(earl)} (reclaims only; 620 / high-break stops are day-low-so-far / prior-session lows)")
    for lab, grp in (("youngest tercile", [r for r in same if r["low_age_bars"] < t1]), ("middle", [r for r in same if t1 <= r["low_age_bars"] < t2]),
                     ("oldest tercile", [r for r in same if r["low_age_bars"] >= t2]), ("earlier-session low", earl)):
        for sp in SPLITS:
            g = [r for r in grp if r["split"] == sp]
            if g:
                st2 = sum(1 for r in g if r["lane_none_outcome"] == "stop" and r["lane_stop_sessions"] is not None and r["lane_stop_sessions"] <= 2)
                L.append(f"      {lab:20s} {sp:4s} n {len(g):3d} lane arm mean {fm(mean([r['lane_trail_r'] for r in g]))} | stopped within 2 sessions {100*st2/len(g):.0f}% | 1xADR trail mean {fm(mean([r['adr100_trail_r'] for r in g if r['adr100_trail_r'] is not None]))}")
    items = [{"ticker": r["ticker"], "ep_date": r["ep_date"], "split": r["split"], "week": r["week"], "g": 1, "v": r["lane_trail_r"]} for r in same if r["low_age_bars"] >= t2] + \
            [{"ticker": r["ticker"], "ep_date": r["ep_date"], "split": r["split"], "week": r["week"], "g": 1, "v": r["lane_trail_r"]} for r in earl] + \
            [{"ticker": r["ticker"], "ep_date": r["ep_date"], "split": r["split"], "week": r["week"], "g": 0, "v": r["lane_trail_r"]} for r in same if r["low_age_bars"] < t1]
    o = group_stats(items, labelled, runners, "(c2) oldest tercile + earlier-session lows vs youngest tercile, lane's own arm (predicted: old better)")
    S["H1c"]["age_terciles"] = o
    L.extend(fmt_group(o, "old", "young"))
    # H3
    L.append("\n" + "=" * 120 + "\nH3 — the trigger: fire time of day, and the reclaim bar's volume\n" + "=" * 120)
    S["H3"] = {}
    mf = [r for r in rows if r["fire_minute"] is not None and r["lane_trail_r"] is not None]
    for b in ("0930", "0935_0959", "1000plus"):
        for sp in SPLITS:
            g = [r for r in mf if r["time_bucket"] == b and r["split"] == sp]
            if g:
                L.append(f"    (a) {b:10s} {sp:4s} n {len(g):3d} lane arm mean {fm(mean([r['lane_trail_r'] for r in g]))} | 1xADR trail {fm(mean([r['adr100_trail_r'] for r in g if r['adr100_trail_r'] is not None]))} | "
                         f"stopped within 2 sessions {100*sum(1 for r in g if r['lane_none_outcome']=='stop' and r['lane_stop_sessions'] is not None and r['lane_stop_sessions']<=2)/len(g):.0f}%")
    items = [{"ticker": r["ticker"], "ep_date": r["ep_date"], "split": r["split"], "week": r["week"], "g": int(r["fire_minute"] >= 600), "v": r["lane_trail_r"]} for r in mf]
    o = group_stats(items, labelled, runners, "(a) fires at 10:00 or later vs before 10:00, lane's own arm (predicted: later better)")
    S["H3"]["time_late_vs_early"] = o
    L.extend(fmt_group(o, "10:00+", "<10:00"))
    items = [{"ticker": r["ticker"], "ep_date": r["ep_date"], "split": r["split"], "week": r["week"], "g": int(r["fire_minute"] >= 600), "v": r["adr100_trail_r"]} for r in mf if r["adr100_trail_r"] is not None]
    o = group_stats(items, labelled, runners, "    (same at 1xADR trail — descriptive)")
    L.extend(fmt_group(o, "10:00+", "<10:00")[:4])
    # (b) volume: reclaim bar / defining-low bar
    vb = [r for r in mf if r.get("vol_low_bar") and r.get("vol_fire_bar") and r["vol_low_bar"] > 0 and r["low_age_kind"] == "same_session"]
    items = [{"ticker": r["ticker"], "ep_date": r["ep_date"], "split": r["split"], "week": r["week"], "g": int(r["vol_fire_bar"] / r["vol_low_bar"] >= 1.0), "v": r["lane_trail_r"]} for r in vb]
    o = group_stats(items, labelled, runners, "(b1) reclaim bar volume >= the undercut (defining-low) bar's volume vs below it, lane's own arm (predicted: >= better)")
    S["H3"]["vol_vs_undercut"] = o
    L.extend(fmt_group(o, "vol>=undercut", "vol<undercut"))
    vp = [r for r in mf if r.get("vol_prior_mean") and r.get("vol_fire_bar") and r["n_prior_bars"] and r["n_prior_bars"] >= 3]
    ratios = sorted([r["vol_fire_bar"] / r["vol_prior_mean"] for r in vp if r["split"] == "DISC"])
    if ratios:
        q1, q2 = ratios[len(ratios) // 3], ratios[2 * len(ratios) // 3]
        items = [{"ticker": r["ticker"], "ep_date": r["ep_date"], "split": r["split"], "week": r["week"], "g": int(r["vol_fire_bar"] / r["vol_prior_mean"] >= q2), "v": r["lane_trail_r"]}
                 for r in vp if (r["vol_fire_bar"] / r["vol_prior_mean"] >= q2 or r["vol_fire_bar"] / r["vol_prior_mean"] < q1)]
        o = group_stats(items, labelled, runners, f"(b2) reclaim bar volume / the session's earlier 5-min mean: top tercile (>= {q2:.2f}x) vs bottom (< {q1:.2f}x), >= 3 earlier bars, lane's own arm")
        S["H3"]["vol_terciles"] = o
        L.extend(fmt_group(o, "top tercile", "bottom tercile"))
        items = [{"ticker": r["ticker"], "ep_date": r["ep_date"], "split": r["split"], "week": r["week"], "g": int(r["vol_fire_bar"] / r["vol_prior_mean"] >= q2), "v": r["adr100_trail_r"]}
                 for r in vp if r["adr100_trail_r"] is not None and (r["vol_fire_bar"] / r["vol_prior_mean"] >= q2 or r["vol_fire_bar"] / r["vol_prior_mean"] < q1)]
        L.extend(fmt_group(group_stats(items, labelled, runners, "    (same at 1xADR trail — descriptive)"), "top", "bottom")[:4])
    L.append(f"  opening-bar fires have no earlier bar for (b2): {sum(1 for r in mf if r['fire_minute'] == 570)} of {len(mf)} minute fires; lane-recorded fires (no bars) {sum(1 for r in rows if r['source'] == 'lane_recorded')}")


# ── H4 ─────────────────────────────────────────────────────────────────────────────────────────────────

def report_h4(S, L):
    rows = rd("hyp_rows_h4.tsv")
    for r in rows:
        r["r"] = fl(r["r"])
    L.append("\n" + "=" * 120 + "\nH4 — tape vs rule: the two named cells on ERA A campaigns today's rules ADMIT vs REJECT (undecided separate), vs ERA A overall and ERA B\n" + "=" * 120)
    S["H4"] = {}
    for cell, lab in (("adr100", "1xADR ep_low_reclaim trail"), ("lane", "the lane's own cell (own stop, trail), all patterns")):
        cr = [r for r in rows if r["cell"] == cell and (cell == "lane" or r["rung"] == "ep_low_reclaim")]
        res = {}
        for name, grp in (("ERA A admit", [r for r in cr if r["era"] == "A" and r["admit"] == "admit"]),
                          ("ERA A reject", [r for r in cr if r["era"] == "A" and r["admit"] == "reject"]),
                          ("ERA A undecided", [r for r in cr if r["era"] == "A" and r["admit"].startswith("abstain")]),
                          ("ERA A all", [r for r in cr if r["era"] == "A"]),
                          ("ERA B all", [r for r in cr if r["era"] == "B"]),
                          ("ERA B era-C-scored (6, all admit)", [r for r in cr if r["era"] == "B" and r["admit"] == "admit"])):
            v = [r["r"] for r in grp]
            se = (statistics.pstdev(v) / len(v) ** 0.5) if len(v) > 1 else None
            res[name] = {"n": len(v), "names": len({r["ticker"] for r in grp}), "mean": mean(v), "se": se, "sum": sum(v) if v else None,
                         "ge3": sum(1 for x in v if x >= 3), "stop_pct": 100 * sum(1 for r in grp if r["outcome"] == "stop") / len(v) if v else None}
            L.append(f"  {lab:48s} {name:34s} n {len(v):3d} ({len({r['ticker'] for r in grp})} names) mean {fm(mean(v))} ± {fm(se, '{:.2f}')} SE | sum {fm(sum(v) if v else None, '{:+.1f}')} | >=3R {sum(1 for x in v if x >= 3)} | stopped {fm(res[name]['stop_pct'], '{:.0f}')}%")
        adm = [r for r in cr if r["era"] == "A" and r["admit"] == "admit"]
        rej = [r for r in cr if r["era"] == "A" and r["admit"] == "reject"]
        items = [{"ticker": r["ticker"], "ep_date": r["ep_date"], "split": "DISC", "week": r["week"], "g": 1, "v": r["r"]} for r in adm] + \
                [{"ticker": r["ticker"], "ep_date": r["ep_date"], "split": "DISC", "week": r["week"], "g": 0, "v": r["r"]} for r in rej]
        p = perm_group([x["v"] for x in items], [x["g"] for x in items], [x["week"] for x in items]) if adm and rej else None
        res["admit_vs_reject_p"] = p
        months = {}
        for m in ("2026-05", "2026-06", "2026-07", "2026-08"):
            g = [r["r"] for r in adm if r["month"] == m]
            months[m] = {"n": len(g), "mean": mean(g), "sum": sum(g) if g else None}
        res["admit_by_month"] = months
        L.append(f"      admit vs reject (ERA A, within-week permutation) p {fm(p, '{:.3f}')}; admitted-only by alert month: " +
                 ", ".join(f"{m[5:]}: {fm(v['mean'])} (n {v['n']}, sum {fm(v['sum'], '{:+.1f}')})" for m, v in months.items()))
        S["H4"][cell] = res
        a, al, b = res["ERA A admit"], res["ERA A all"], res["ERA B all"]
        same_as_all = a["mean"] is not None and al["se"] and abs(a["mean"] - al["mean"]) <= al["se"]
        unlike_b = a["mean"] is not None and b["mean"] is not None and b["se"] is not None and abs(a["mean"] - b["mean"]) > 2 * max(b["se"], a["se"] or 0)
        res["read"] = ("admitted-only reads like ERA A overall" if same_as_all else "admitted-only differs from ERA A overall") + \
                      ("; and unlike ERA B -> the era split is tape/time, not the 08-22 rule" if unlike_b else "; not separable from ERA B at this n")
        L.append(f"      => {res['read']}")


# ── H5 ─────────────────────────────────────────────────────────────────────────────────────────────────

def spearman(x, y):
    n = len(x)
    if n < 4:
        return None
    def ranks(v):
        idx = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[idx[j + 1]] == v[idx[i]]:
                j += 1
            for k in range(i, j + 1):
                r[idx[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    rx, ry = ranks(x), ranks(y)
    mx, my = mean(rx), mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else None


def perm_spearman(x, y, weeks, seed=SEED):
    obs = spearman(x, y)
    if obs is None:
        return None
    blocks = defaultdict(list)
    for i, wk in enumerate(weeks):
        blocks[wk].append(i)
    rng = random.Random(seed)
    yy = list(y)
    cnt = 0
    for _ in range(N_PERM):
        for idxs in blocks.values():
            vals = [yy[i] for i in idxs]
            rng.shuffle(vals)
            for i, v in zip(idxs, vals):
                yy[i] = v
        s = spearman(x, yy)
        if s is not None and ((obs >= 0 and s >= obs - 1e-12) or (obs < 0 and s <= obs + 1e-12)):
            cnt += 1
    return (cnt + 1) / (N_PERM + 1)


def report_h5(S, L, labelled, runners):
    rows = rd("hyp_rows_h5.tsv")
    for r in rows:
        for k in ("outcome_adr15", "ext_xadr_eod", "ext_xadr_pregap", "tightness_pct_eod", "composite_rank_eod", "open_range_position"):
            r[k] = fl(r[k])
    L.append("\n" + "=" * 120 + "\nH5 — selection re-cut, stop-independent: max high over sessions 1-15 above the EP close, in ADR$, vs the EP-day features (IN-SAMPLE on discovery by construction — only the held-out sign can count)\n" + "=" * 120)
    ok = [r for r in rows if r["outcome_adr15"] is not None]
    L.append(f"  campaigns with an outcome {len(ok)} of {len(rows)} (censored under 15 sessions: {sum(1 for r in ok if r['censored'] == '1')}, all ERA B); runners (>= 5 ADR) {sum(1 for r in ok if r['outcome_adr15'] >= 5)}; "
             f"his 4 labelled: " + ", ".join(f"{r['ticker']} {fm(r['outcome_adr15'], '{:.1f}')} ADR" for r in ok if r["labelled"] == "1"))
    S["H5"] = {}
    # numeric features: predicted direction per the hypotheses doc — ext lower better (-), tightness lower better (-), composite_rank higher better (+), open_range_position higher better (+)
    for feat, pred in (("ext_xadr_eod", -1), ("ext_xadr_pregap", -1), ("tightness_pct_eod", -1), ("composite_rank_eod", +1), ("open_range_position", +1)):
        res = {"predicted_sign": pred}
        for sp in SPLITS:
            g = [r for r in ok if r["split"] == sp and r[feat] is not None]
            x = [r[feat] for r in g]; y = [r["outcome_adr15"] for r in g]
            rho = spearman(x, y)
            rr = {"n": len(g), "rho": rho}
            if sp == "DISC" and rho is not None:
                rr["p"] = perm_spearman(x, y, [r["week"] for r in g])
                srt = sorted(g, key=lambda r: r[feat] * pred, reverse=True)   # predicted-good end first
                k = len(srt) // 3
                top, bot = srt[:k], srt[-k:]
                rr["top_third_runner_pct"] = 100 * sum(1 for r in top if r["outcome_adr15"] >= 5) / k if k else None
                rr["bottom_third_runner_pct"] = 100 * sum(1 for r in bot if r["outcome_adr15"] >= 5) / k if k else None
                rr["top_third_mean"] = mean([r["outcome_adr15"] for r in top]); rr["bottom_third_mean"] = mean([r["outcome_adr15"] for r in bot])
                rr["runners7_in_top_third"] = sum(1 for r in top if r["runner7"] == "1"); rr["runners7_with_feature"] = sum(1 for r in g if r["runner7"] == "1")
                rr["labelled_in_top_third"] = sum(1 for r in top if r["labelled"] == "1"); rr["labelled_with_feature"] = sum(1 for r in g if r["labelled"] == "1")
            res[sp] = rr
        d = res["DISC"]
        in_dir = d["rho"] is not None and d["rho"] * pred > 0
        ho = {sp: ("can't tell" if res[sp]["n"] < MIN_HELDOUT or res[sp]["rho"] is None else ("+" if res[sp]["rho"] * pred > 0 else "-")) for sp in ("HOA", "B")}
        res["heldout"] = ho
        res["verdict"] = "can't tell (in-sample; held-out direction only)" if not (in_dir and d.get("p") is not None and d["p"] < 0.05) else \
                         ("held-out agrees in direction (in-sample discovery cannot confirm)" if ho["HOA"] == "+" and ho["B"] == "+" else ("can't tell (held-out thin)" if "can't tell" in ho.values() else "fails held-out"))
        S["H5"][feat] = res
        L.append(f"  {feat:22s} predicted {'+' if pred > 0 else '-'} | DISC n {d['n']:3d} rho {fm(d['rho'], '{:+.3f}')} p {fm(d.get('p'), '{:.3f}')} | top third runner share {fm(d.get('top_third_runner_pct'), '{:.1f}')}% vs bottom {fm(d.get('bottom_third_runner_pct'), '{:.1f}')}% "
                 f"(mean {fm(d.get('top_third_mean'), '{:.2f}')} vs {fm(d.get('bottom_third_mean'), '{:.2f}')} ADR; runners in top third {d.get('runners7_in_top_third')}/{d.get('runners7_with_feature')}, labelled {d.get('labelled_in_top_third')}/{d.get('labelled_with_feature')}) "
                 f"| HOA n {res['HOA']['n']} rho {fm(res['HOA']['rho'], '{:+.2f}')} | B n {res['B']['n']} rho {fm(res['B']['rho'], '{:+.2f}')} | {res['verdict']}")
    for feat in ("expct_scheduled", "expct_looking", "expct_beat", "catalyst_type", "tier"):
        res = {}
        for sp in SPLITS:
            g = [r for r in ok if r["split"] == sp]
            byc = defaultdict(list)
            for r in g:
                byc[r[feat] or "none"].append(r)
            res[sp] = {c: {"n": len(v), "mean": mean([r["outcome_adr15"] for r in v]), "runner_pct": 100 * sum(1 for r in v if r["outcome_adr15"] >= 5) / len(v),
                           "runners7": sum(1 for r in v if r["runner7"] == "1"), "labelled": sum(1 for r in v if r["labelled"] == "1")} for c, v in byc.items()}
        S["H5"][feat] = res
        L.append(f"  {feat:22s} " + " | ".join(f"{sp}: " + ", ".join(f"{c} n{v['n']} {fm(v['mean'], '{:.2f}')} ADR {fm(v['runner_pct'], '{:.0f}')}% run (r7 {v['runners7']}, lab {v['labelled']})"
                                                            for c, v in sorted(res[sp].items(), key=lambda kv: -kv[1]["n"])) for sp in SPLITS if res[sp]))
    L.append("  => none of the ten features can 'hold' on this program: the features were chosen on 05-11..08-14 alerts (in-sample) and the held-out parts are 11 and 16 campaigns.")


# ── H12 ─────────────────────────────────────────────────────────────────────────────────────────────────

def report_h12(S, L, labelled, runners):
    rows = rd("hyp_rows_h12.tsv")
    for r in rows:
        for k in list(r):
            if k.endswith("_r") or k in ("entry", "stop", "stop_w", "adr"):
                r[k] = fl(r[k])
    L.append("\n" + "=" * 120 + "\nH12 (operator) — a 620 turn within 0.5xADR of ANY pivot on the fixed list, stop under the turn's session low; per campaign vs the lane's FIRST fire (own stop)\n" + "=" * 120)
    fired = [r for r in rows if r.get("status") == "fired"]
    S["H12"] = {"campaigns": len(rows), "fired": len(fired), "no_fire": sum(1 for r in rows if r.get("status") == "no_h12_fire"),
                "blind_sessions_total": sum(int(r["blind_sessions"] or 0) for r in rows if r.get("blind_sessions")),
                "campaigns_with_blind": sum(1 for r in rows if r.get("blind_sessions") and int(r["blind_sessions"]) > 0),
                "by_era_fired": dict(Counter(r["era"] for r in fired)), "lane_fired": sum(1 for r in rows if r.get("lane_first_rung"))}
    piv = Counter()
    for r in fired:
        for p in (r.get("pivots") or "").split(";"):
            if p:
                piv[p.split("@")[0].split("_s")[0]] += 1
    S["H12"]["pivots_used"] = dict(piv)
    S["H12"]["near_ep_close_share"] = sum(1 for r in fired if r.get("near_ep_close") == "1")
    S["H12"]["median_stop_w"] = statistics.median([r["stop_w"] for r in fired]) if fired else None
    S["H12"]["session_idx"] = dict(Counter(r.get("session_idx") for r in fired))
    L.append(f"  fired on {len(fired)} of {len(rows)} campaigns (ERA {S['H12']['by_era_fired']}); the lane fired on {S['H12']['lane_fired']}; blind sessions {S['H12']['blind_sessions_total']} on {S['H12']['campaigns_with_blind']} campaigns; "
             f"pivots named on the fires {dict(piv)}; within 0.5 ADR of the EP close (the lane's own rung) {S['H12']['near_ep_close_share']} of {len(fired)}; median stop width {fm(S['H12']['median_stop_w'], '{:.2f}')}%; "
             f"fire session {sorted(Counter(int(r['session_idx']) for r in fired).items())[:8]}")
    for arm in ("trail", "none"):
        items = [{"ticker": r["ticker"], "ep_date": r["ep_date"], "split": r["split"], "week": r["week"], "v": r.get(f"turnlow_rec_{arm}_r"), "b": r.get(f"lane_{arm}_r"),
                  "fv": r.get(f"turnlow_rec_{arm}_r") if arm == "none" else r.get("turnlow_fill_trail_r"), "fb": r.get(f"lane_fill_{arm}_r")} for r in fired]
        if arm == "none":
            for x, r in zip(items, fired):
                x["fv"] = r.get("turnlow_fill_none_r")
        o = paired_stats(items, labelled, runners, f"620-near-any-pivot, stop = turn's session low, {arm} arm, vs the lane's first fire (own stop, {arm}) on the same campaigns")
        S["H12"][f"turnlow_{arm}"] = o
        L.extend(fmt_paired(o))
        items = [{"ticker": r["ticker"], "ep_date": r["ep_date"], "split": r["split"], "week": r["week"], "v": r.get(f"adr100_rec_{arm}_r"), "b": r.get(f"lane_{arm}_r"),
                  "fv": r.get(f"adr100_fill_{arm}_r"), "fb": r.get(f"lane_fill_{arm}_r")} for r in fired]
        o2 = paired_stats(items, labelled, runners, f"   (same fires with a 1xADR stop, {arm} — descriptive)")
        S["H12"][f"adr100_{arm}"] = o2
        L.extend(fmt_paired(o2)[:4])
    # vs the lane's BEST first fire (descriptive)
    items = [{"ticker": r["ticker"], "ep_date": r["ep_date"], "split": r["split"], "week": r["week"], "v": r.get("turnlow_rec_trail_r"), "b": r.get("lane_best_trail_r"), "fv": None, "fb": None} for r in fired]
    o3 = paired_stats(items, labelled, runners, "   (vs the lane's BEST first fire on the campaign, trail — descriptive, favours the lane)")
    L.extend(fmt_paired(o3)[:4])
    # tail campaigns by name
    for r in fired:
        if (r["ticker"], r["ep_date"]) in labelled | runners:
            L.append(f"      tail campaign {r['ticker']} {r['ep_date']}: H12 fire {r['h12_fire_date']} s{r['session_idx']} min {r['fire_minute']} entry {r['entry']:.2f} stop {r['stop']:.2f} ({r['stop_w']:.2f}%) near {r['pivots']} -> trail {fm(r.get('turnlow_rec_trail_r'))}R none {fm(r.get('turnlow_rec_none_r'))}R | lane first {r.get('lane_first_rung')} {r.get('lane_first_date')} trail {fm(r.get('lane_trail_r'))}R")
    L.append("\n  TEAM hand-walk (hyp_team_handwalk.txt):")
    L.extend("    " + ln for ln in (HERE / "hyp_team_handwalk.txt").read_text().splitlines())


# ── H13 ─────────────────────────────────────────────────────────────────────────────────────────────────

def report_h13(S, L, labelled, runners):
    rows = rd("hyp_rows_h13.tsv")
    for r in rows:
        for k in ("r", "r_lane_units", "mfe", "mae", "level0", "risk"):
            r[k] = fl(r.get(k))
    L.append("\n" + "=" * 120 + "\nH13 (operator) — close-based stops with a violence override, per fire vs the TOUCH stop at the same level (that level's R; SMA10 rows also in the lane's R)\n" + "=" * 120)
    S["H13"] = {}
    by = defaultdict(dict)
    for r in rows:
        by[(r["ticker"], r["ep_date"], r["rung"], r["level"], r["arm"], r["entry_kind"])][r["rule"]] = r
    for level in ("lane", "sma10"):
        inapp = sum(1 for r in rows if r["level"] == level and r["rule"] == "touch" and r["arm"] == "none" and r["entry_kind"] == "rec" and r["status"] == "inapplicable")
        L.append(f"\n  level = {'the lane\'s own stop' if level == 'lane' else 'SMA10 (through the prior session)'}; inapplicable (level at/above the entry, or no SMA10): {inapp} of 632")
        for arm in ("none", "trail"):
            for rule in H13_RULES:
                items, items_lu = [], []
                blind = 0
                for k, d in by.items():
                    if k[3] != level or k[4] != arm or k[5] != "rec":
                        continue
                    t, v = d.get("touch"), d.get(rule)
                    if not t or not v:
                        continue
                    kf = by.get((k[0], k[1], k[2], level, arm, "fill"), {})
                    tf, vf = kf.get("touch"), kf.get(rule)
                    ok_t = t["status"] in ("settled", "marked"); ok_v = v["status"] in ("settled", "marked")
                    okf = tf and vf and tf["status"] in ("settled", "marked") and vf["status"] in ("settled", "marked")
                    blind += int(v.get("blind") or 0) if ok_v else 0
                    items.append({"ticker": k[0], "ep_date": k[1], "split": t["split"], "week": t["week"], "v": v["r"] if ok_v else None, "b": t["r"] if ok_t else None,
                                  "fv": vf["r"] if okf else None, "fb": tf["r"] if okf else None})
                    items_lu.append({"ticker": k[0], "ep_date": k[1], "split": t["split"], "week": t["week"], "v": v["r_lane_units"] if ok_v else None, "b": t["r_lane_units"] if ok_t else None, "fv": None, "fb": None})
                name = f"{rule:13s} {arm:5s} vs touch at the same level" + (f" (volume override blind on {blind} sessions)" if rule == "close_vol3x" else "")
                o = paired_stats(items, labelled, runners, name)
                if level == "lane":
                    # robustness: the lane's razor stops (< 0.5% wide) turn a held position into hundreds of R either way
                    wide = {(k[0], k[1], k[2]) for k, d in by.items() if k[3] == "lane" and k[4] == arm and k[5] == "rec" and d.get("touch")
                            and fl(d["touch"]["entry"]) and fl(d["touch"]["stop"]) and (fl(d["touch"]["entry"]) - fl(d["touch"]["stop"])) / fl(d["touch"]["entry"]) * 100 >= 0.5}
                    keys_in = [k for k, d in by.items() if k[3] == "lane" and k[4] == arm and k[5] == "rec" and d.get("touch") and d.get(rule)]
                    itx = [x for x, k in zip(items, keys_in) if (k[0], k[1], k[2]) in wide]
                    ox = paired_stats(itx, labelled, runners, "ex-razor")
                    o["ex_razor"] = {sp: {k2: ox[sp][k2] for k2 in ("n", "mean_v", "mean_b", "mean_diff", "worst_v", "n_loss_gt15_v", "n_loss_gt15_b")} | {"p": ox[sp].get("p"), "drop2": ox[sp].get("drop2_sum")} for sp in SPLITS}
                # abstain count for the variant
                o["abstain_v"] = sum(1 for k, d in by.items() if k[3] == level and k[4] == arm and k[5] == "rec" and d.get(rule) and d[rule]["status"] == "abstain")
                S["H13"][f"{level}/{rule}/{arm}"] = o
                L.extend(fmt_paired(o))
                if level == "lane":
                    for sp in SPLITS:
                        e = o["ex_razor"][sp]
                        L.append(f"      ex lane stops under 0.5% wide {sp:4s} n {e['n']:3d} | variant {fm(e['mean_v'])} vs touch {fm(e['mean_b'])} -> diff {fm(e['mean_diff'])} (drop-2 {fm(e.get('drop2'), '{:+.1f}')}; p {fm(e.get('p'), '{:.3f}')}) | worst {fm(e['worst_v'])} | losses<-1.5R {e['n_loss_gt15_v']} (touch {e['n_loss_gt15_b']})")
                if level == "sma10":
                    olu = paired_stats(items_lu, labelled, runners, "   (same, in the lane's R units)")
                    S["H13"][f"{level}/{rule}/{arm}/lane_units"] = {sp: {k2: olu[sp][k2] for k2 in ("n", "mean_v", "mean_b", "mean_diff", "worst_v", "n_loss_gt15_v")} for sp in SPLITS}
                    L.append(f"      in the lane's R: DISC diff {fm(olu['DISC']['mean_diff'])} (variant {fm(olu['DISC']['mean_v'])} vs touch {fm(olu['DISC']['mean_b'])}; worst {fm(olu['DISC']['worst_v'])}; losses<-1.5R {olu['DISC']['n_loss_gt15_v']})")
        # the touch baseline itself, for reference
        for arm in ("none", "trail"):
            t = [r for r in rows if r["level"] == level and r["rule"] == "touch" and r["arm"] == arm and r["entry_kind"] == "rec" and r["status"] in ("settled", "marked")]
            for sp in SPLITS:
                g = [r for r in t if r["split"] == sp]
                if g:
                    L.append(f"      touch baseline {arm:5s} {sp:4s} n {len(g):3d} mean {fm(mean([r['r'] for r in g]))} worst {fm(min(r['r'] for r in g))} stopped {100*sum(1 for r in g if r['outcome']=='stop')/len(g):.0f}%")


# ── the verdict table and the doc-facing summary ────────────────────────────────────────────────────────

def report():
    labelled, runners = tail_sets()
    S = {"draws": N_DRAWS, "noise_max": NOISE_MAX, "family_min": FAMILY_MIN, "seed": SEED, "n_perm": N_PERM, "min_heldout": MIN_HELDOUT,
         "tail_sets": {"labelled": sorted(labelled), "runners": sorted(runners)}}
    L = [f"#327 hypothesis tests — report (pre-registration: hyptests.py docstring). Draws {N_DRAWS}; noise band <= {NOISE_MAX} clearing anywhere; family >= {FAMILY_MIN} on one mechanism; "
         f"permutation {N_PERM} draws seed {SEED}; held-out minimum n {MIN_HELDOUT}.",
         f"tail sets: his labelled EPs in the 277 {sorted(labelled)}; the rerun's 7 big winners {sorted(runners)}"]
    report_h2(S, L)
    report_stops(S, L, labelled, runners)
    report_h4(S, L)
    report_h5(S, L, labelled, runners)
    report_h12(S, L, labelled, runners)
    report_h13(S, L, labelled, runners)
    # verdict table over the 35 draws
    draws = []
    for pat in PATTERNS:
        v = S["H2"][pat]["verdict"]
        draws.append(("H2", f"{pat} scaled-barrier edge", v["disc_pass"], v["heldout"]["HOA"], v["heldout"]["B"], v["verdict"]))
    for kk in K_POST:
        o = S["H1b"][f"h1b_{int(kk*100):03d}_vs_lane"]
        draws.append(("H1b", f"k={kk} post-gap stop vs lane", o["disc_pass"], o["heldout"]["HOA"], o["heldout"]["B"], o["verdict"]))
    for N in H1C_N:
        o = S["H1c"][f"h1c_first{N}"]
        draws.append(("H1c", f"first-{N}-min low stop", o["disc_pass"], o["heldout"]["HOA"], o["heldout"]["B"], o["verdict"]))
    o = S["H1c"]["age_terciles"]; draws.append(("H1c", "old vs young defining low", o["disc_pass"], o["heldout"]["HOA"], o["heldout"]["B"], o["verdict"]))
    for k, lab in (("time_late_vs_early", "10:00+ vs earlier fires"), ("vol_vs_undercut", "reclaim vol >= undercut vol"), ("vol_terciles", "reclaim vol top vs bottom tercile")):
        if k in S["H3"]:
            o = S["H3"][k]; draws.append(("H3", lab, o["disc_pass"], o["heldout"]["HOA"], o["heldout"]["B"], o["verdict"]))
    for cell in ("adr100", "lane"):
        r = S["H4"][cell]
        p = r.get("admit_vs_reject_p")
        draws.append(("H4", f"{cell} admit vs reject", p is not None and p < 0.05 and (r["ERA A admit"]["mean"] or 0) > (r["ERA A reject"]["mean"] or 0), "n/a", "n/a", r["read"]))
    for feat in ("ext_xadr_eod", "ext_xadr_pregap", "tightness_pct_eod", "composite_rank_eod", "open_range_position", "expct_scheduled", "expct_looking", "expct_beat", "catalyst_type", "tier"):
        r = S["H5"][feat]
        if "verdict" in r:
            draws.append(("H5", feat, False, r["heldout"]["HOA"], r["heldout"]["B"], r["verdict"]))
        else:
            draws.append(("H5", feat, False, "—", "—", "descriptive classes only (in-sample)"))
    for arm in ("trail", "none"):
        o = S["H12"][f"turnlow_{arm}"]; draws.append(("H12", f"620-near-pivot {arm} vs lane first fire", o["disc_pass"], o["heldout"]["HOA"], o["heldout"]["B"], o["verdict"]))
    for level in ("lane", "sma10"):
        for rule in H13_RULES:
            o = S["H13"][f"{level}/{rule}/none"]; draws.append(("H13", f"{level} {rule} none vs touch", o["disc_pass"], o["heldout"]["HOA"], o["heldout"]["B"], o["verdict"]))
    S["draw_table"] = [{"h": d[0], "draw": d[1], "disc_pass": bool(d[2]), "HOA": d[3], "B": d[4], "verdict": d[5]} for d in draws]
    n_clear = sum(1 for d in draws if d[5] == "holds")
    n_disc = sum(1 for d in draws if d[2])
    S["verdict"] = {"draws_listed": len(draws), "holds": n_clear, "disc_pass_only": n_disc, "noise": n_clear <= NOISE_MAX}
    L.append("\n" + "=" * 120 + f"\nVERDICT TABLE — {len(draws)} draws listed (pre-registered {N_DRAWS}); HOLDS {n_clear} (noise band <= {NOISE_MAX}); pass discovery only {n_disc}\n" + "=" * 120)
    for d in draws:
        L.append(f"  {d[0]:4s} {d[1]:44s} DISC {'pass' if d[2] else 'fail':4s} HOA {d[3]:11s} B {d[4]:11s} -> {d[5]}")
    txt = "\n".join(L) + "\n"
    (HERE / "hyp_report.txt").write_text(txt)
    (HERE / "hyp_summary.json").write_text(json.dumps(S, indent=1, default=str))
    print(txt)
    print("wrote hyp_report.txt, hyp_summary.json")
