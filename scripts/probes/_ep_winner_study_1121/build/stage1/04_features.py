#!/usr/bin/env python3
"""STAGE 1 / step 1d — the feature table for all 4,665 events (prereg §4, §6 step 1). THIS SCRIPT CONTAINS NO FORWARD READ:
every value comes from features.event_features (bars with calendar index < ci(E) + open(E)); see features.py.
Run: python3 04_features.py > 04_features.txt"""
import sys
from collections import Counter
from multiprocessing import Pool

import numpy as np
import pandas as pd

import common as C
import features as F
import stats as S

ev = C.build_population(verbose=lambda *_: None)
cal = C.calendars()
bars = C.bars_cached(ev, cal, verbose=lambda *_: None)
flags = C.load_flags()
breaks = C.load_breaks()
ALL = F.FEATS + ["B1", "B1clean", "B2"]


def one(k):
    r = ev.iloc[k]
    vals, nulls = F.event_features(r.era, r.ticker, r.E, bars[(r.era, r.ticker)], bars[(r.era, "SPY")], cal[r.era],
                                   flags[r.era].get(r.ticker, []), breaks[r.era].get(r.ticker, []), float(r.prev_close_raw), float(r.med_dv20))
    return k, vals, nulls


if __name__ == "__main__":
    print("# STAGE 1 / 04 feature table (prereg §4 + §6 step 1). No forward read: bars < E and open(E) only.")
    print(f"prereg sha256 {C.sha(C.PREREG)}")
    print(f"population {len(ev)} events; flags loaded A {sum(len(v) for v in flags['A'].values())} / B {sum(len(v) for v in flags['B'].values())} (ticker, date) pairs;"
          f" identity-break symbols A {len(breaks['A'])} / B {len(breaks['B'])}")
    with Pool(8) as pool:
        res = pool.map(one, range(len(ev)), chunksize=40)
    T = ev[["era", "ticker", "E", "set", "year", "month", "quarter", "sectype", "hist_n", "vr20_mean"]].copy()
    for f in ALL + ["adr20_raw", "f14_base_fallback"]:
        T[f] = np.nan
    for f in ALL:
        T[f + "_null"] = ""
    for k, vals, nulls in res:
        for f, x in vals.items():
            T.at[k, f] = x
        for f, why in nulls.items():
            T.at[k, f + "_null"] = why
        assert set(vals) & set(nulls) == set() and set(ALL) <= set(vals) | set(nulls), (k, set(ALL) - set(vals) - set(nulls))
    for f in ALL:
        assert (T[f].notna() == (T[f + "_null"] == "")).all(), f
        assert np.isfinite(T[f].dropna()).all(), f
    # ---- checks against the event list (outcome-free columns)
    assert np.allclose(T.f01 * 100.0, ev.gap_pct, rtol=1e-4, atol=1e-4), "feature 1 != the event list's gap_pct"
    print("feature 1 equals the event list's gap_pct on every event (ASSERT OK)")

    # ---- NULL counts
    print("\n## NULL counts per feature (reason: n), by era; full feature x era x year x reason table in null_counts.tsv")
    rows = []
    for f in ALL:
        for (era, year, why), n in T[T[f + "_null"] != ""].groupby(["era", "year", f + "_null"]).size().items():
            rows.append((f, era, year, why, n))
    NC = pd.DataFrame(rows, columns=["feature", "era", "year", "reason", "n"])
    NC.to_csv(C.HERE / "null_counts.tsv", sep="\t", index=False)
    print(f"{'feature':8} {'name':46} {'window':>6} | {'scored':>6} {'NULL':>5} | {'A scored':>8} {'A NULL':>6} | {'B scored':>8} {'B NULL':>6} | DISC scored / CONF scored | reasons")
    for f in ALL:
        nul = T[f + "_null"] != ""
        rs = Counter(T.loc[nul, f + "_null"])
        a = T.era == "A"
        print(f"{f:8} {F.NAMES[f][:46]:46} {str(F.WINDOW.get(f, '5y')):>6} | {int((~nul).sum()):6d} {int(nul.sum()):5d} | {int((~nul & a).sum()):8d} {int((nul & a).sum()):6d} |"
              f" {int((~nul & ~a).sum()):8d} {int((nul & ~a).sum()):6d} | {int((~nul & (T.set == 'DISC')).sum())} / {int((~nul & (T.set == 'CONF')).sum())} | "
              + ", ".join(f"{k}: {v}" for k, v in sorted(rs.items(), key=lambda x: -x[1])))
    print("\n## NULL counts per feature x era x year (all reasons pooled; scored/NULL)")
    yrs = sorted(set(zip(T.era, T.year)))
    print(f"{'feature':8} " + " ".join(f"{e}{y}".rjust(9) for e, y in yrs))
    for f in ALL:
        cells = []
        for e, y in yrs:
            g = T[(T.era == e) & (T.year == y)]
            cells.append(f"{int((g[f + '_null'] == '').sum())}/{int((g[f + '_null'] != '').sum())}".rjust(9))
        print(f"{f:8} " + " ".join(cells))
    print("\n## NULL reasons per feature x era x year (only non-zero cells)")
    for f in ALL:
        g = NC[NC.feature == f]
        if len(g):
            print(f"{f}: " + " | ".join(f"{r.era}{r.year} {r.reason} {r.n}" for r in g.itertuples(index=False)))
    # frozen expectations about coverage
    f16_2016 = T[(T.year == "2016")]
    assert (f16_2016.f16_null != "").all(), "feature 16 should be NULL for all of 2016"
    b16 = T[(T.era == "B") & (T.f16_null == "")]
    print(f"\nfeature 16: NULL for all {len(f16_2016)} events of 2016 (ASSERT OK); first era-B event scored on it: {b16.E.min() if len(b16) else 'none'}"
          f" (frozen text: NULL for era-B events before ~2022-09-26)")
    for f in ("f05", "f16", "f20", "B1"):
        g = T[(T.era == "B") & (T[f + "_null"] == "")]
        print(f"  first era-B event scored on {f}: {g.E.min() if len(g) else 'none'}")
    print(f"feature 14: base bar taken from the fallback (no bar on session E-61, latest bar within the 5 sessions before): {int((T.f14_base_fallback == 1).sum())} events"
          f" (SPY is read at the SAME session the ticker's base bar sits on)")
    d = T.B2.notna() & T.adr20_raw.notna()
    print(f"ADR20: encoder value present {int(T.adr20_raw.notna().sum())} of {len(T)}; B2 (with the §4.0 NULL rules, window 20) scored {int(T.B2.notna().sum())};"
          f" NULL by rule but the encoder value exists {int((T.B2.isna() & T.adr20_raw.notna()).sum())} (ADR strata of §2 use the encoder value)")

    # ---- thirds, tie shares, tie-heavy fallback, two-group minimums (all outcome-free; DISCOVERY decides)
    D = T[T.set == "DISC"].reset_index(drop=True)
    print("\n## §5.1 ties and the tie-heavy fallback (decided here, without outcomes) — DISCOVERY events")
    print(f"{'feature':8} {'scored':>6} {'in months>=6':>12} {'moved by mid-rank':>18} {'bottom':>7} {'middle':>7} {'top':>7} {'top share':>9} {'bottom share':>12}  decision")
    decisions = {}
    for f in F.FEATS:
        scored = int(D[f].notna().sum())
        if f in F.TWO_GROUP:
            continue
        t_mid = S.assign_thirds(D, f, ["era", "month"], S.MIN_MONTH, midrank=True)
        t_tic = S.assign_thirds(D, f, ["era", "month"], S.MIN_MONTH, midrank=False)
        inm = int((t_mid >= 0).sum())
        moved = int(((t_mid != t_tic) & (t_mid >= 0)).sum())
        nb, nm, nt = (int((t_mid == k).sum()) for k in (0, 1, 2))
        ts, bs = nt / scored, nb / scored
        fallback = ts < 0.20 or bs < 0.20
        ts2, bs2 = nt / inm, nb / inm
        note = ""
        if (ts2 < 0.20 or bs2 < 0.20) != fallback:
            note = " [differs if the denominator is 'events in months >= 6']"
        decisions[f] = "TWO-GROUP (tie-heavy fallback)" if fallback else "thirds"
        print(f"{f:8} {scored:6d} {inm:12d} {moved:8d} ({100 * moved / max(inm, 1):5.1f}%) {nb:7d} {nm:7d} {nt:7d} {100 * ts:8.1f}% {100 * bs:11.1f}%  {decisions[f]}{note}")
    print("  'moved by mid-rank' = events whose third differs from a ticker-order split of the same sorted values. Shares are of the feature's scored discovery events (frozen bar: under 20% -> two-group).")
    print("\n## two-group features (15, 16, and any fallback): group sizes on scored DISCOVERY events; minimum = smaller group >= 100 events AND >= 15%")
    two = {}
    for f in F.FEATS:
        if f in F.TWO_GROUP:
            g = D[f].dropna()
            ny, nn = int((g == 1).sum()), int((g == 0).sum())
            lab = "yes / no"
            two[f] = None
        elif decisions[f].startswith("TWO"):
            g = D[f].dropna()
            mode = g.value_counts().idxmax()
            ny, nn = int((g == mode).sum()), int((g != mode).sum())
            lab = f"most common value ({mode:g}) / everything else"
            two[f] = float(mode)
        else:
            continue
        small = min(ny, nn); tot = ny + nn
        ok = small >= 100 and small / tot >= 0.15
        decisions[f] = ("two-group" if f in F.TWO_GROUP else decisions[f]) + (" — candidate" if ok else " — DESCRIPTION ONLY (cannot be carried)")
        print(f"  {f} {F.NAMES[f]}: {lab} = {ny} / {nn} of {tot} scored; smaller group {small} = {100 * small / tot:.1f}% -> {decisions[f]}")
        gc = T[(T.set == 'CONF')][f].dropna()
        if f in F.TWO_GROUP:
            print(f"      (confirm, outcome-free) yes / no = {int((gc == 1).sum())} / {int((gc == 0).sum())}")
    print("\n## step-1 decisions per feature")
    for f in F.FEATS:
        print(f"  {f} {F.NAMES[f]}: {decisions[f]}")
    pd.DataFrame([(f, decisions[f], two.get(f)) for f in F.FEATS], columns=["feature", "decision", "two_group_mode_value"]).to_csv(C.HERE / "feature_decisions.tsv", sep="\t", index=False)

    # ---- feature 12 vs vr20_mean (collider), within-month rank correlation
    print("\n## feature 12 vs vr20_mean — Pearson correlation of within-(era, month) percentile ranks (= pooled within-month Spearman), outcome-free")
    for nm, g in (("discovery", T[T.set == "DISC"]), ("confirm", T[T.set == "CONF"]), ("all", T)):
        g = g.reset_index(drop=True); m = g.f12.notna().to_numpy()
        a = S.pct_rank_within(g, "f12", ["era", "month"], m)[m]; b = S.pct_rank_within(g, "vr20_mean", ["era", "month"], m)[m]
        print(f"  {nm}: rho {S.pearson(a, b):+.3f} on {int(m.sum())} events")

    # ---- shelf relatives
    print("\n## shelf relatives — Spearman of each feature with dmin on within-(era, month) percentile ranks, DISCOVERY events scored on both (|rho| >= 0.5 -> 'shelf relative')")
    rel = []
    for f in F.FEATS + ["B2"]:
        m = (D[f].notna() & D.B1.notna()).to_numpy()
        a = S.pct_rank_within(D, f, ["era", "month"], m)[m]; b = S.pct_rank_within(D, "B1", ["era", "month"], m)[m]
        rho = S.pearson(a, b)
        tag = "SHELF RELATIVE — confirm partly seen" if abs(rho) >= 0.5 else ""
        if tag and f in F.FEATS:
            rel.append(f)
        print(f"  {f:4} {F.NAMES[f][:46]:46} rho {rho:+.3f}  n {int(m.sum()):5d}  {tag}")
    print(f"  shelf relatives: {rel if rel else 'NONE (condition 5 of §5.2 applies to no feature)'}")
    (C.HERE / "shelf_relatives.txt").write_text("\n".join(rel) + ("\n" if rel else ""))

    # ---- B1 / B2 description
    print(f"\n## benchmarks: B1 dmin scored {int(T.B1.notna().sum())} (A {int((T.B1.notna() & (T.era == 'A')).sum())} / B {int((T.B1.notna() & (T.era == 'B')).sum())};"
          f" DISC {int((T.B1.notna() & (T.set == 'DISC')).sum())} / CONF {int((T.B1.notna() & (T.set == 'CONF')).sum())}); B1-clean scored {int(T.B1clean.notna().sum())}"
          f" (dropped by the adjustment / identity rules over the 5-year slice: {int((T.B1.notna() & T.B1clean.isna()).sum())})")
    print("   B1 scored per year: " + " · ".join(f"{e}{y} {int(((T.era == e) & (T.year == y) & T.B1.notna()).sum())}" for e, y in yrs))
    print("   (the B1 reproduction asserts of RESULT 8 need outcomes and belong to the discovery / confirm scripts, not here)")
    # ---- outcome-free confirm n per feature per era (§3 asks for it before the confirm read; printed now as well)
    print("\n## confirm n per feature per era (scored), outcome-free")
    for f in ALL:
        g = T[T.set == "CONF"]
        print(f"  {f:8} A {int((g[f].notna() & (g.era == 'A')).sum()):4d} · B {int((g[f].notna() & (g.era == 'B')).sum()):4d}")
    out = C.HERE / "feature_table.tsv.gz"
    T.to_csv(out, sep="\t", index=False, float_format="%.10g", compression={"method": "gzip", "mtime": 0})
    print(f"\nfeature_table.tsv.gz written: {len(T)} rows x {T.shape[1]} columns; sha256 {C.sha(out)}")
    print(f"null_counts.tsv sha256 {C.sha(C.HERE / 'null_counts.tsv')} | feature_decisions.tsv sha256 {C.sha(C.HERE / 'feature_decisions.tsv')}")
    print(f"code: features.py {C.sha(C.HERE / 'features.py')} | common.py {C.sha(C.HERE / 'common.py')} | stats.py {C.sha(C.HERE / 'stats.py')} | this script {C.sha(__file__)}")
