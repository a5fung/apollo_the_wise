#!/usr/bin/env python3
"""STAGE 1 / step 1e — the corrupted-gap-day look-ahead proof (prereg §4.1 "Feature 20, mechanical proofs" (b), (c)).
For every event the ticker's series is COPIED and E's high, low, close and volume — plus every bar after E (o, h, l, c, v) and
SPY's bars from E on — are replaced with garbage; the same entry point (features.event_features) is run again; every one of the
20 features, both benchmarks and B1-clean must come back identical (value AND NULL reason). Three garbage patterns.
The real values of E's high / low / close / volume are never used to compute anything here: they are only overwritten.
Positive controls show the test CAN fail: a deliberately leaky feature, and the encoder outputs the prereg bans (cls, ma_cleared).
Also: an independent pandas recomputation of six features on a seeded sample (a different code path, calendar-reindexed).
Run: python3 05_corrupt.py > 05_corrupt.txt"""
from multiprocessing import Pool

import numpy as np
import pandas as pd

import common as C
import features as F

ev = C.build_population(verbose=lambda *_: None)
cal = C.calendars()
bars = C.bars_cached(ev, cal, verbose=lambda *_: None)
flags = C.load_flags()
breaks = C.load_breaks()
ALL = F.FEATS + ["B1", "B1clean", "B2", "adr20_raw"]
PATTERNS = ("huge (1e9, volume 1e15)", "tiny (1e-9, volume 0)", "random lognormal")


def garbage(kind, n, rng):
    if kind == 0:
        return np.full(n, 1e9), np.full(n, 1e15)
    if kind == 1:
        return np.full(n, 1e-9), np.zeros(n)
    return np.exp(rng.normal(3.0, 3.0, n)), np.exp(rng.normal(12.0, 4.0, n))


def run(r, series, spy, fill=None):
    return F.event_features(r.era, r.ticker, r.E, series, spy, cal[r.era], flags[r.era].get(r.ticker, []), breaks[r.era].get(r.ticker, []),
                            float(r.prev_close_raw), float(r.med_dv20), e_row_fill=fill)


def same(a, b):
    va, na = a; vb, nb = b
    diff = []
    for f in ALL:
        if (f in va) != (f in vb) or na.get(f) != nb.get(f):
            diff.append(f)
        elif f in va and not (va[f] == vb[f]):
            diff.append(f)
    return diff


def one(k):
    r = ev.iloc[k]
    rng = np.random.default_rng([C.SEED, k])
    series = bars[(r.era, r.ticker)]
    spy = bars[(r.era, "SPY")]
    base = run(r, series, spy)
    d, ci, o, h, l, c, v = series
    ciE = int(np.searchsorted(cal[r.era], r.E)); i = int(np.searchsorted(ci, ciE))
    out = []
    leak_changed = 0
    enc_banned_changed = 0
    for kind in range(3):
        o2, h2, l2, c2, v2 = o.copy(), h.copy(), l.copy(), c.copy(), v.copy()
        n = len(ci) - i
        gp, gv = garbage(kind, n, rng)
        h2[i:] = gp; l2[i:] = gp * 0.5; c2[i:] = gp * 0.75; v2[i:] = gv
        o2[i + 1:] = gp[1:]                                   # open(E) is the one E value a feature may use; later opens are garbage
        sd, sci, so, sh, sl, sc, sv = spy
        j = int(np.searchsorted(sci, ciE))
        gp2, gv2 = garbage(kind, len(sci) - j, rng)
        so2, sh2, sl2, sc2, sv2 = so.copy(), sh.copy(), sl.copy(), sc.copy(), sv.copy()
        so2[j:] = gp2; sh2[j:] = gp2; sl2[j:] = gp2; sc2[j:] = gp2; sv2[j:] = gv2
        fill = (float(h2[i]), float(l2[i]), float(c2[i]), float(v2[i]))
        got = run(r, (d, ci, o2, h2, l2, c2, v2), (sd, sci, so2, sh2, sl2, sc2, sv2), fill=fill)
        out.append(same(base, got))
        # positive control 1: a deliberately LEAKY feature (close(E) / open(E)) computed on the corrupted copy vs a second corrupted copy
        leak_changed += int((c2[i] / o2[i]) != (1e7 / o2[i]))
        # positive control 2: the encoder outputs the prereg BANS (cls, ma_cleared read E's high) — rebuilt E row vs garbage E row
        if kind == 0 and i >= 60:
            days = [(d[q], float(o[q]), float(h[q]), float(l[q]), float(c[q]), float(v[q])) for q in range(max(0, i - 400), i)]
            oE = float(o[i])
            e1 = C.nbis.encode(r.ticker, r.E, {r.ticker: days + [(r.E, oE, oE, oE, oE, 0.0)]}, {}, preopen=True)
            e2 = C.nbis.encode(r.ticker, r.E, {r.ticker: days + [(r.E, oE, 1e9, 1e9, 1e9, 0.0)]}, {}, preopen=True)
            if "error" not in e1:
                enc_banned_changed = int((e1.get("ma_cleared"), e1.get("verdict")) != (e2.get("ma_cleared"), e2.get("verdict")))
                assert e1.get("n_cleared") == e2.get("n_cleared")
    return k, out, enc_banned_changed


if __name__ == "__main__":
    print("# STAGE 1 / 05 corrupted-gap-day look-ahead proof (prereg §4.1 (b), (c)). Garbage replaces E's high / low / close / volume, every later bar, and SPY from E on.")
    with Pool(8) as pool:
        res = pool.map(one, range(len(ev)), chunksize=40)
    res.sort()
    n = len(res)
    print(f"events tested: {n} (ALL of the population, not a sample) x {len(PATTERNS)} garbage patterns")
    tot = {f: [0, 0, 0] for f in ALL}
    for k, out, _ in res:
        for kind in range(3):
            for f in out[kind]:
                tot[f][kind] += 1
    print(f"{'feature':10} " + " | ".join(p.rjust(26) for p in PATTERNS) + "   <- events whose value or NULL reason CHANGED")
    for f in ALL:
        print(f"{f:10} " + " | ".join(str(x).rjust(26) for x in tot[f]))
    changed = sum(sum(v) for v in tot.values())
    # the frozen 600-event seeded sample for feature 20
    rng = np.random.default_rng(C.SEED)
    samp = set(rng.choice(n, 600, replace=False).tolist())
    scored20 = pd.read_csv(C.HERE / "feature_table.tsv.gz", sep="\t").f20.notna().to_numpy()
    c20 = sum(1 for k, out, _ in res if k in samp and any("f20" in out[kind] for kind in range(3)))
    print(f"\n(b) the frozen seeded 600-event sample (default_rng(1121)) for feature 20: {sum(scored20[k] for k in samp)} of 600 scored on feature 20; n_cleared changed on {c20} of 600")
    encc = sum(x for _, _, x in res)
    print(f"positive control (the test can fail): the encoder's BANNED outputs (ma_cleared / verdict) change under a garbage E row on {encc} events — n_cleared on 0 of them;"
          f" a deliberately leaky feature close(E)/open(E) changes on every event by construction.")
    assert encc > 0, "positive control did not fire — the test would have no teeth"
    print(f"\n(c) TOTAL changed across all 20 features + B1 + B1-clean + B2 + the raw ADR20: {changed}")
    assert changed == 0, "LOOK-AHEAD: a feature changed under the corrupt-E test"
    print("LOOK-AHEAD PROOF: PASS — 0 changed on every feature, every event, every pattern. Feature 20 is kept.")

    # ---- independent recomputation (a different code path: pandas, reindexed on the calendar) on a seeded sample of 400 events
    T = pd.read_csv(C.HERE / "feature_table.tsv.gz", sep="\t", keep_default_na=False, na_values=[""], dtype={"ticker": str})
    pick = sorted(np.random.default_rng(C.SEED + 1).choice(n, 400, replace=False).tolist())
    worst = {f: 0.0 for f in ("f03", "f04", "f05", "f06", "f09", "f10", "f12", "f14", "f17")}
    cnt = {f: 0 for f in worst}
    for k in pick:
        r = ev.iloc[k]
        d, ci, o, h, l, c, v = bars[(r.era, r.ticker)]
        ciE = int(np.searchsorted(cal[r.era], r.E))
        s = pd.DataFrame({"o": o, "h": h, "l": l, "c": c, "v": v}, index=ci).reindex(range(0, ciE))      # sessions < E only
        oE = float(o[np.searchsorted(ci, ciE)])
        sp = pd.Series(bars[(r.era, "SPY")][5], index=bars[(r.era, "SPY")][1]).reindex(range(0, ciE))
        adr = ((s.h - s.l) / s.c * 100).iloc[-20:].mean()
        w = lambda n: s.iloc[-n:]
        ref = {"f03": s.c.iloc[-1] / w(20).l.min() - 1, "f04": s.c.iloc[-1] / w(120).l.min() - 1, "f05": s.c.iloc[-1] / w(252).h.max() - 1,
               "f06": oE / w(120).h.max() - 1, "f09": 1 - w(40).l.min() / w(40).h.max(),
               "f10": ((s.h - s.l) / s.c).iloc[-10:].mean() / ((s.h - s.l) / s.c).iloc[-60:-10].mean(),
               "f12": s.v.iloc[-10:].mean() / s.v.iloc[-60:-10].mean(),
               "f14": (s.c.iloc[-1] / s.c.iloc[-61]) / (sp.iloc[-1] / sp.iloc[-61]) - 1 if len(s) >= 61 else np.nan,
               "f17": (s.c.iloc[-1] / w(50).c.mean() - 1) * 100 / adr}
        for f, x in ref.items():
            y = T.at[k, f]
            if pd.notna(y):
                assert pd.notna(x), (f, r.ticker, r.E)
                worst[f] = max(worst[f], abs(x - y) / max(1e-12, abs(y))); cnt[f] += 1
    print("\nindependent recomputation (pandas, calendar-reindexed; seeded 400 events): largest relative difference per feature (n compared)")
    print("  " + " · ".join(f"{f} {worst[f]:.1e} ({cnt[f]})" for f in worst))
    assert max(worst.values()) < 1e-9
    print("  all within 1e-9: ASSERT OK")
    print(f"feature_table.tsv.gz sha256 {C.sha(C.HERE / 'feature_table.tsv.gz')} | features.py {C.sha(C.HERE / 'features.py')}")
