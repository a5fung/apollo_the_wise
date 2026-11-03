#!/usr/bin/env python3
"""BLIND verifier: independent measures (own stdlib code, NOT recut.measure) on the per-trade R values the
pinned walker produced (pinned_full.perarm.json), the full 10-16 population and the open-floor KEPT rows.

Checks:
  1. kept walk R == full walk R by key, every arm (licenses computing kept measures from the full walk);
  2. the dropped set's stage census and what it carried;
  3. per-arm measures, full and kept, compared cell by cell with (a) the 10-16 doc's 26 table rows,
     (b) the 1103 claims' kept table (recut_open_floor.txt);
  4. the 95% separation call (week-block p < 0.05 AND week-bootstrap CI excludes 0), plus seed sensitivity;
  5. the pre-registered bar (P1-P6) on the primary, and the exploratory registration rule.
"""
import json
import math
import random
import re
import statistics
import sys
from collections import Counter, defaultdict

V = "/Users/alvinfung/apollo_the_wise/scripts/probes/_runner_recut_1103/verify"
DOC = "/Users/alvinfung/apollo_the_wise/docs/analysis/runner_recut_results_2026-10-16.md"
CLAIMS = "/Users/alvinfung/apollo_the_wise/scripts/probes/_runner_recut_1103/recut_open_floor.txt"
sys.path.insert(0, V)
sys.dont_write_bytecode = True
import floor  # noqa: E402

RULES = ["t3_be", "t5_be", "t10_be", "t20_be", "close_only", "sma10_depth", "sma20_depth",
         "atr1_be", "atr2_be", "gb25_be", "gb50_be"]
ARMS = [f"{fr}|{ru}" for fr in "AB" for ru in RULES]
REFS = ["t20_entry_ref", "era_d", "control_at_close"]
EPS = 1e-9


def load(tag):
    return json.load(open(f"{V}/{tag}.perarm.json"))


def arm_R(t, name):
    return t["arms"][name] if name in t["arms"] else t["refs"][name]


def arm_status(t, name):
    return t["arm_status"][name] if name in t["arm_status"] else t["ref_status"][name]


def week_of(t):
    return tuple(t["week"])


def p90(xs):
    s = sorted(xs)
    pos = (len(s) - 1) * 0.9
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def signflip(block_sums, seed=1017, draws=5000):
    rng = random.Random(seed)
    obs = abs(sum(block_sums))
    hits = 0
    for _ in range(draws):
        tot = 0.0
        for s in block_sums:
            tot += s if rng.random() < 0.5 else -s
        if abs(tot) >= obs - 1e-12:
            hits += 1
    return (hits + 1) / (draws + 1)


def boot(blocks, seed=1017, draws=10000):
    rng = random.Random(seed)
    nb = len(blocks)
    means = []
    for _ in range(draws):
        s = n = 0
        for _ in range(nb):
            bs, bn = blocks[rng.randrange(nb)]
            s += bs
            n += bn
        means.append(s / n)
    means.sort()
    return means[int(0.025 * draws)], means[math.ceil(0.975 * draws) - 1]


def measures(trades, name, frame=None, seed=1017):
    pairs = [t for t in trades if arm_R(t, name) is not None and t["ctrl"] is not None]
    pairs.sort(key=lambda t: (t["d"], t["t"]))
    R = [arm_R(t, name) for t in pairs]
    C = [t["ctrl"] for t in pairs]
    D = [r - c for r, c in zip(R, C)]
    n = len(pairs)
    m = dict(n=n, mean=sum(R) / n, median=statistics.median(R), win=sum(x > 0 for x in R) / n, total=sum(R),
             tail=sum(x >= 4 - EPS for x in R), tail_c=sum(x >= 4 - EPS for x in C), be=sum(x >= 1.5 - EPS for x in R),
             p90=p90(R), d_tot=sum(D), d_mean=sum(D) / n)
    m["engaged"] = sum(1 for t in pairs if t["trig" + frame]) if frame else None
    diff = [i for i in range(n) if abs(D[i]) > 0.005]
    m["differ"] = len(diff)
    m["differ_weeks"] = len({week_of(pairs[i]) for i in diff})
    m["drop2"] = sum(R) - sum(sorted(R, reverse=True)[:2])
    gains = sorted([x for x in D if x > 1e-12], reverse=True)
    m["d_ex2"] = sum(D) - sum(gains[:2])
    m["d_top5_share"] = sum(gains[:5]) / sum(D) if sum(D) > 1e-12 else None
    m["own_top2"] = sum(sorted(R, reverse=True)[:2]) / sum(R) if sum(R) else None
    m["own_top5"] = sum(sorted(R, reverse=True)[:5]) / sum(R) if sum(R) else None
    m["h1"] = sum(x for t, x in zip(pairs, D) if t["d"] <= "2026-06-30")
    m["h2"] = sum(x for t, x in zip(pairs, D) if t["d"] > "2026-06-30")
    m["h1_n"] = sum(1 for t in pairs if t["d"] <= "2026-06-30")
    m["open_end"] = sum(1 for t in pairs if arm_status(t, name) == "data_end")
    blk = defaultdict(lambda: [0.0, 0])
    for t, x in zip(pairs, D):
        blk[week_of(t)][0] += x
        blk[week_of(t)][1] += 1
    order = sorted(blk)
    m["n_blocks"] = len(order)
    m["p"] = signflip([blk[w][0] for w in order], seed=seed)
    m["lo"], m["hi"] = boot([tuple(blk[w]) for w in order], seed=seed)
    m["sep95"] = m["p"] < 0.05 and (m["lo"] > 0 or m["hi"] < 0)
    keys = [(t["t"], t["d"]) for t in pairs]
    m["tail_lost"] = [keys[i] for i in range(n) if C[i] >= 4 - EPS and R[i] < 4 - EPS]
    m["tail_gained"] = [keys[i] for i in range(n) if C[i] < 4 - EPS and R[i] >= 4 - EPS]
    if frame:
        F = [(t["F" + frame] - t["entry"]) / t["risk"] for t in pairs if t["trig" + frame]]
        m["F_ok"] = all(f >= -EPS for f in F)
    return m


def ctrl_measures(trades):
    sc = sorted([t for t in trades if t["ctrl"] is not None], key=lambda t: (t["d"], t["t"]))
    C = [t["ctrl"] for t in sc]
    return dict(n=len(C), mean=sum(C) / len(C), median=statistics.median(C), win=sum(x > 0 for x in C) / len(C),
                total=sum(C), tail=sum(x >= 4 - EPS for x in C), be=sum(x >= 1.5 - EPS for x in C), p90=p90(C),
                drop2=sum(C) - sum(sorted(C, reverse=True)[:2]),
                open_end=sum(1 for t in sc if t["ctrl_status"] == "data_end"),
                own_top2=sum(sorted(C, reverse=True)[:2]) / sum(C), own_top5=sum(sorted(C, reverse=True)[:5]) / sum(C),
                tail_names=sorted((t["t"], t["d"]) for t in sc if t["ctrl"] >= 4 - EPS))


def s2(x):
    return f"{x:+.2f}"


def doc_cells(m, kind):
    """The 16 numeric cells of the 10-16 table layout (paired n .. open at end), my own formatter."""
    if kind == "control":
        return [str(m["n"]), "-", "-", f"{m['tail']} ({100 * m['tail'] / m['n']:.1f}%)", str(m["be"]), s2(m["p90"]),
                s2(m["total"]), f"{m['mean']:+.3f}", "-", "-", s2(m["drop2"]), "-", "-", f"{m['median']:+.3f}",
                f"{100 * m['win']:.1f}%", str(m["open_end"])]
    eng = "-" if m["engaged"] is None else str(m["engaged"])
    ref = kind == "ref"
    return [str(m["n"]), eng, str(m["differ"]), f"{m['tail']} ({100 * m['tail'] / m['n']:.1f}%)", str(m["be"]), s2(m["p90"]),
            s2(m["total"]), f"{m['mean']:+.3f}", s2(m["d_tot"]), "-" if ref else s2(m["d_ex2"]),
            "-" if ref else s2(m["drop2"]), "-" if ref else f"{s2(m['h1'])} / {s2(m['h2'])}",
            "-" if ref else f"{m['p']:.3f}", f"{m['median']:+.3f}", f"{100 * m['win']:.1f}%", str(m["open_end"])]


def parse_table_rows(text):
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("| "):
            line = line[2:]
        elif line.startswith("|"):
            line = line[1:]
        else:
            continue
        cells = [c.strip() for c in line.rstrip("|").split("|")]
        if len(cells) != 18 or cells[0] in ("frame", "---"):
            continue
        fr, rule = cells[0], cells[1].replace("*", "")
        if rule.startswith("control (depth)"):
            key = "control"
        elif fr == "ref":
            key = rule
        else:
            key = f"{fr}|{rule.split(' ')[0]}"
        out.setdefault(key, []).append(cells[2:])
    return out


def compare_tables(my, theirs, label):
    bad, n_rows = [], 0
    for key, rows in theirs.items():
        for cells in rows:
            n_rows += 1
            mine = my.get(key)
            if mine is None:
                bad.append((key, "missing in mine"))
                continue
            for i, (a, b) in enumerate(zip(mine, cells)):
                if a != b:
                    bad.append((key, i, "mine", a, "theirs", b))
    print(f"[{label}] table rows compared: {n_rows}; cell mismatches: {len(bad)}")
    for b in bad[:40]:
        print("   MISMATCH", b)
    return n_rows, bad


def main():
    full = load("pinned_full")["trades"]
    kept_walk = load("pinned_kept")["trades"]
    drop_walk = load("pinned_dropped")["trades"]
    dk = floor.dropped_keys()
    fmap = {(t["t"], t["d"]): t for t in full}

    # 1. kept walk == full walk, by key, every arm
    mism = []
    for t in kept_walk + drop_walk:
        f = fmap[(t["t"], t["d"])]
        for nm in ARMS + REFS + ["ctrl"]:
            a = t["ctrl"] if nm == "ctrl" else arm_R(t, nm)
            b = f["ctrl"] if nm == "ctrl" else arm_R(f, nm)
            if (a is None) != (b is None) or (a is not None and abs(a - b) > 1e-12):
                mism.append(((t["t"], t["d"]), nm, a, b))
    print(f"1. kept+dropped walk R vs full walk R: {len(kept_walk)}+{len(drop_walk)} trades x {len(ARMS) + len(REFS) + 1} arms; mismatches {len(mism)} {mism[:5]}")
    assert {(t['t'], t['d']) for t in kept_walk} == {k for k in fmap if k not in dk}
    kept = [t for t in full if (t["t"], t["d"]) not in dk]
    dropped = [t for t in full if (t["t"], t["d"]) in dk]

    # 2. dropped census
    print("\n2. DROPPED SET")
    print(f"   filled: dropped {len(dropped)} of {len(full)}; kept {len(kept)}")
    sc_d = [t for t in dropped if t["ctrl"] is not None]
    sc_k = [t for t in kept if t["ctrl"] is not None]
    print(f"   scored (control R not None): dropped {len(sc_d)} of {len(sc_d) + len(sc_k)}; kept {len(sc_k)}")
    print(f"   control status, dropped filled: {dict(Counter(t['ctrl_status'] for t in dropped))}; kept filled: {dict(Counter(t['ctrl_status'] for t in kept))}")
    print(f"   dropped acct (build_trades on the dropped rows): {load('pinned_dropped')['acct']}; kept acct: {load('pinned_kept')['acct']}")
    ct = ctrl_measures(full)
    tail_d = sorted(k for k in ct["tail_names"] if k in dk)
    print(f"   control +4R winners dropped: {len(tail_d)} of {len(ct['tail_names'])} -> {tail_d}")
    engA = sorted((t["t"], t["d"]) for t in full if t["ctrl"] is not None and t["trigA"])
    engA_d = [k for k in engA if k in dk]
    print(f"   Frame A engaged (scored, reached +8 ORB-R): {len(engA)}; dropped {len(engA_d)} -> {engA_d}")
    print(f"   dropped scored carried: control {sum(t['ctrl'] for t in sc_d):+.2f}R of {ct['total']:+.2f}R; "
          f"primary {sum(t['arms']['A|t20_be'] for t in sc_d if t['arms']['A|t20_be'] is not None):+.2f}R; "
          f"paired diff {sum(t['arms']['A|t20_be'] - t['ctrl'] for t in sc_d if t['arms']['A|t20_be'] is not None):+.2f}R")
    cd = ctrl_measures(dropped)
    print(f"   dropped control n {cd['n']} total {cd['total']:+.2f} mean {cd['mean']:+.3f} median {cd['median']:+.3f} win {100 * cd['win']:.1f}% drop-best-2 {cd['drop2']:+.2f}")

    # 3. per-arm measures, full + kept; compare with the doc and the claims
    results = {}
    for popname, pop in (("full", full), ("kept", kept)):
        res = {"control": ctrl_measures(pop)}
        for a in ARMS:
            res[a] = measures(pop, a, frame=a[0])
        res["t20_entry_ref"] = measures(pop, "t20_entry_ref", frame="A")
        res["era_d"] = measures(pop, "era_d")
        res["control_at_close"] = measures(pop, "control_at_close")
        results[popname] = res

    print("\n3. TABLE COMPARISONS (my own measures + my own formatter vs the printed cells)")
    for popname, src, label in (("full", open(DOC).read(), "10-16 doc, full population"),
                                ("kept", open(CLAIMS).read().split("THE 10-16 TABLE LAYOUT, KEPT ROWS")[1].split("PER ARM, KEPT ROWS")[0],
                                 "1103 claims, kept rows")):
        res = results[popname]
        my = {"control": doc_cells(res["control"], "control")}
        for a in ARMS:
            my[a] = doc_cells(res[a], "arm")
        for r in REFS:
            my[r] = doc_cells(res[r], "ref")
        compare_tables(my, parse_table_rows(src), label)

    # the claims' PER ARM table (kept and full): n, mean, median, win, total, +4R, own top2/top5, d tot, d/trade, CI, p, d ex2, d top5, sep95
    print("\n   claims' PER ARM tables vs mine:")
    txt = open(CLAIMS).read()
    for popname, start, end in (("kept", "PER ARM, KEPT ROWS", "control: its top 5"),
                                ("full", "PER ARM, FULL 10-16 POPULATION", "control: its top 5")):
        seg = txt.split(start)[1].split(end)[0]
        bad = 0
        nrow = 0
        for line in seg.splitlines():
            line = line.strip()
            if not line or line.startswith("frame|rule") or line.startswith("—") or line.startswith("("):
                continue
            nm = line.split()[0] if not line.startswith("control (depth)") else "control"
            nm = nm.replace("ref|", "")
            m = results[popname][nm]
            if nm == "control":
                mine = f"{m['n']} {m['mean']:+.3f} {m['median']:+.3f} {100 * m['win']:.1f} {m['total']:+.2f} {m['tail']} {100 * m['own_top2']:.0f}% {100 * m['own_top5']:.0f}%"
                theirs = " ".join(line.split()[2:])
            else:
                share = "n/a" if m["d_top5_share"] is None else f"{100 * m['d_top5_share']:.0f}%"
                mine = (f"{m['n']} {m['mean']:+.3f} {m['median']:+.3f} {100 * m['win']:.1f} {m['total']:+.2f} {m['tail']} "
                        f"{100 * m['own_top2']:.0f}% {100 * m['own_top5']:.0f}% {m['d_tot']:+.2f} {m['d_mean']:+.3f} "
                        f"[{m['lo']:+.3f}, {m['hi']:+.3f}] {m['p']:.3f} {m['d_ex2']:+.2f} {share} {'YES' if m['sep95'] else 'no'}")
                theirs = " ".join(line.split()[1:])
            nrow += 1
            if mine.split() != theirs.split():
                bad += 1
                print(f"     MISMATCH {popname} {nm}\n        mine   {mine}\n        theirs {theirs}")
        print(f"   [{popname}] PER-ARM rows compared {nrow}; mismatching rows {bad}")

    # 4. separation + seed sensitivity
    print("\n4. 95% SEPARATION (week-block p < 0.05 AND week-bootstrap 95% CI of the per-trade paired difference excludes 0)")
    for popname in ("full", "kept"):
        res = results[popname]
        yes = [(a, round(res[a]["d_tot"], 2), round(res[a]["p"], 4), round(res[a]["lo"], 3), round(res[a]["hi"], 3))
               for a in ARMS + REFS if res[a]["sep95"]]
        p05 = [a for a in ARMS + REFS if res[a]["p"] < 0.05]
        print(f"   {popname}: sep95 YES = {yes}; p<0.05 = {p05}")
    print("   seed sensitivity (seeds 1..50, same draws): share of seeds where sep95 holds / p<0.05 holds; p range; CI-lo range")
    for popname, arms in (("kept", ["A|t3_be", "A|atr1_be", "A|atr2_be", "B|atr2_be", "A|gb25_be", "B|t5_be"]),
                          ("full", ["A|gb25_be"])):
        pop = full if popname == "full" else kept
        for a in arms:
            ms = [measures(pop, a, frame=a[0], seed=s) for s in range(1, 51)]
            print(f"     {popname} {a:<10} sep95 {sum(m['sep95'] for m in ms)}/50  p<0.05 {sum(m['p'] < 0.05 for m in ms)}/50  "
                  f"p [{min(m['p'] for m in ms):.4f}, {max(m['p'] for m in ms):.4f}]  CI-lo [{min(m['lo'] for m in ms):+.3f}, {max(m['lo'] for m in ms):+.3f}]  "
                  f"CI-hi [{min(m['hi'] for m in ms):+.3f}, {max(m['hi'] for m in ms):+.3f}]")
    # exact-p for kept arms near the line: full enumeration impossible (19 blocks -> 2^19 = 524,288 sign patterns is feasible)
    print("   exact week-block sign-flip p by full enumeration of 2^blocks sign patterns (no RNG):")
    for popname, arms in (("kept", ["A|t3_be", "A|atr1_be", "A|atr2_be", "B|atr2_be", "A|t20_be"]), ("full", ["A|gb25_be", "A|t20_be"])):
        pop = full if popname == "full" else kept
        for a in arms:
            pairs = sorted([t for t in pop if arm_R(t, a) is not None and t["ctrl"] is not None], key=lambda t: (t["d"], t["t"]))
            blk = defaultdict(float)
            for t in pairs:
                blk[week_of(t)] += arm_R(t, a) - t["ctrl"]
            sums = [blk[w] for w in sorted(blk)]
            obs = abs(sum(sums))
            nb = len(sums)
            hits = 0
            for mask in range(1 << nb):
                tot = 0.0
                for i, s in enumerate(sums):
                    tot += s if (mask >> i) & 1 else -s
                if abs(tot) >= obs - 1e-12:
                    hits += 1
            print(f"     {popname} {a:<10} blocks {nb}  exact two-sided p = {hits / (1 << nb):.4f}")

    # 5. bar on the primary + exploratory registration
    print("\n5. PRE-REGISTERED BAR ON THE PRIMARY (A|t20_be)")
    for popname in ("full", "kept"):
        m = results[popname]["A|t20_be"]
        P1 = m["differ"] >= 10 and m["differ_weeks"] >= 6
        P2 = m["d_tot"] > 0 and m["p"] < 0.05
        P3 = m["d_ex2"] > 0
        P4 = m["h1"] > 0 and m["h2"] > 0
        P5 = m["tail"] >= m["tail_c"]
        P6 = m["F_ok"]
        word = "TOO FEW" if not P1 else ("PROPOSAL" if all((P2, P3, P4, P5, P6)) else "STANDS")
        print(f"   {popname}: P1 {P1} (differ {m['differ']}, weeks {m['differ_weeks']}) | P2 {P2} (d {m['d_tot']:+.2f}, p {m['p']:.4f}) | "
              f"P3 {P3} ({m['d_ex2']:+.2f}) | P4 {P4} (H1 {m['h1']:+.2f} n={m['h1_n']} / H2 {m['h2']:+.2f}) | P5 {P5} ({m['tail']} vs {m['tail_c']}) | "
              f"P6(F>=entry) {P6} -> {word}; tail lost {m['tail_lost']} gained {m['tail_gained']}; CI [{m['lo']:+.3f}, {m['hi']:+.3f}]")
        cands = []
        for a in ARMS:
            if a == "A|t20_be":
                continue
            x = results[popname][a]
            ok = (x["differ"] >= 10 and x["differ_weeks"] >= 6 and x["d_ex2"] > 0 and x["h1"] > 0 and x["h2"] > 0
                  and x["tail"] >= x["tail_c"] and x["p"] < 0.05 and x["d_tot"] > 0)
            if ok:
                cands.append((round(x["d_tot"], 2), a))
        print(f"   {popname}: exploratory arms meeting P1,P3,P4,P5 + p<0.05 + positive total: {sorted(cands, reverse=True)}")
    k = results["kept"]["control"]
    print(f"\n   kept control: n {k['n']} total {k['total']:+.2f} mean {k['mean']:+.4f} median {k['median']:+.3f} win {100 * k['win']:.1f}% "
          f"+4R {k['tail']} {k['tail_names']} open-at-end {k['open_end']}")
    json.dump({p: {a: {kk: vv for kk, vv in m.items()} for a, m in r.items()} for p, r in results.items()},
              open(f"{V}/indep_results.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
