#!/usr/bin/env python3
"""#717 shape checks: the STUDY (exploration BEFORE any definition; nothing here is a check). Prints, in daily-range (ADR)
units, the bars of the target "no" charts, his ok charts and Qullamaggie's 56 listed High-tier buys, plus a set of
descriptive measures, to see WHY the previous card's tightness (5a-5c) and higher-low (3a-3e) definitions missed.

    python3 scripts/probes/_717_shape_1114/02_study.py > scripts/probes/_717_shape_1114/02_study.out
"""
import numpy as np, pandas as pd
import lib
pd.set_option("display.width", 320); pd.set_option("display.max_columns", 60); pd.set_option("display.max_rows", 200)
f, sc, hi, hi_all, gr, nights, cal, WF, WX = lib.load()


def desc(w, adr, level, base_len):
    o, h, l, c = (np.asarray(x, float) for x in w)
    u = adr * level                                           # one daily range, in price
    m = {}
    rng = (h - l) / c / adr
    for n in (10, 15, 20):
        m[f"big{n}_125"] = int((rng[-n:] > 1.25).sum()); m[f"big{n}_15"] = int((rng[-n:] > 1.5).sum())
        m[f"hl{n}"] = (h[-n:].max() - l[-n:].min()) / u       # the high-low box of the last n sessions
        dc = np.abs(np.diff(c[-n - 1:]))
        m[f"path{n}"] = dc.sum() / u / n                      # mean |close-to-close move| in daily ranges
        m[f"eff{n}"] = abs(c[-1] - c[-n - 1]) / dc.sum()
        m[f"dn{n}"] = int((np.diff(c[-n - 1:]) / u < -1.0).sum())    # down closes bigger than one daily range
    for n in (20, 40, 60):
        m[f"off{n}"] = (np.nanmax(h[-n:]) - level) / u        # the buy level under the n-session high
    m["close_off_lvl"] = (level - c[-1]) / u
    m["near5"] = int(((level - c[-10:]) / u <= 2.0).sum())    # of the last 10 closes, how many sit within 2 daily ranges of the level
    for k in (1.5, 2.0, 3.0):
        n = min(60, max(20, int(base_len) + 10))
        for look, tag in ((40, "40"), (60, "60")):
            piv = lib.zigzag(h[-look:], l[-look:], k * u)             # (first-look version used a rougher swing finder; this is lib's final one)
            H = [p for p in piv if p[2] == 1]; L = [p for p in piv if p[2] == -1]
            m[f"nsw{tag}_{k}"] = len(piv)
            m[f"lh{tag}_{k}"] = (H[-1][1] - H[-2][1]) / u if len(H) >= 2 else np.nan       # < 0 = the latest swing high is LOWER
            m[f"ll{tag}_{k}"] = (L[-1][1] - L[-2][1]) / u if len(L) >= 2 else np.nan       # < 0 = the latest swing low is LOWER
            m[f"lvl_lastH{tag}_{k}"] = (H[-1][1] - level) / u if H else np.nan
    return m


def table(d, W):
    return pd.DataFrame([desc(W[r.w], r.adr20, r.level, r.base_len) for r in d.itertuples()], index=d.index)


G = pd.concat([gr[["card", "ticker", "Dd", "grade", "base_len", "u50", "s50_chg10"]], table(gr, WF)], axis=1)
G["after1d"] = ~((G.u50 < -0.03) & (G.s50_chg10 < 0))
H = pd.concat([hi[["ticker", "E", "base_len"]], table(hi, WX)], axis=1)
cols = [c for c in G.columns if c not in ("card", "ticker", "Dd", "grade", "base_len", "u50", "s50_chg10", "after1d", "words")]
print("== THE 36 GRADED PICKS (after1d = still on the list after the 50-day check) ==")
for a in range(0, len(cols), 18):
    print(G.sort_values(["grade", "after1d", "ticker"])[["ticker", "Dd", "grade", "after1d", "base_len"] + cols[a:a + 18]].round(2).to_string(index=False)); print()
print("his words:"); [print(f"  {r.ticker:5s} {r.grade:11s} {r.words}") for r in gr.sort_values('grade').itertuples()]
print("\n== QULLAMAGGIE'S 56 LISTED HIGH-TIER BUYS: quantiles ==")
print(H[cols].describe(percentiles=[.05, .1, .25, .5, .75, .9, .95]).T.round(2).to_string())
print("\n== the 56, the 4 most extreme each side ==")
for c in cols:
    s = H.sort_values(c).dropna(subset=[c])
    print(f"  {c:16s} low: " + ", ".join(f"{r.ticker} {r.E[2:]} {getattr(r, c.replace('.', '_')) if False else s.loc[r.Index, c]:.2f}" for r in s.head(4).itertuples()) + " | high: " + ", ".join(f"{r.ticker} {r.E[2:]} {s.loc[r.Index, c]:.2f}" for r in s.tail(4).itertuples()))
samp = f.sample(4000, random_state=717)
S = table(samp, WF)
print("\n== ERA-A FIRES (random 4,000): quantiles ==")
print(S[cols].describe(percentiles=[.05, .1, .25, .5, .75, .9, .95]).T.round(2).to_string())
print("\n== BARS in daily ranges from the buy level, last 40 sessions (close | low..high), the third-sheet picks ==")
for r in gr[gr.card.notna()].tail(12).itertuples():
    o, h, l, c = (np.asarray(x[-40:], float) for x in WF[r.w]); u = r.adr20 * r.level
    print(f"{r.ticker} {r.Dd} {r.grade} base_len {r.base_len} | {r.words}")
    print("   close: " + " ".join(f"{(x - r.level) / u:5.1f}" for x in c))
    print("   high : " + " ".join(f"{(x - r.level) / u:5.1f}" for x in h))
    print("   low  : " + " ".join(f"{(x - r.level) / u:5.1f}" for x in l))
