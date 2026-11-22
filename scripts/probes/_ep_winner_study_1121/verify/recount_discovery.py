#!/usr/bin/env python3
"""EP big-winner study — STEP 4 BLIND RECOUNT of the DISCOVERY read (prereg docs/analysis/ep_winner_study_prereg_2026-11-21.md, §5.1-5.2 + §10).

Independent second build, written from the prereg text alone:
  * does NOT import stage1/common.py, stage1/stats.py or any stage-3 code; stage3/ is never opened;
  * reuses ONLY stage1/feature_table.tsv.gz (feature values) and stage1/population.tsv (open(E) cross-check);
  * outcomes computed here from the RAW era-A daily file (not the stage-1 bar cache);
  * CONFIRM firewall: only DISCOVERY events (E <= 2020-12-31, era A) are kept at read; bars are cut AT READ at the
    calendar session ci(last discovery E) + 60, so no confirm-event forward window can be formed (asserted);
  * events_scored.tsv.gz of _594 is never opened; run.txt is used only for its 4 'per year' 2017-2020 lines (A3, hard-coded below).
$0, local files only.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ST1 = HERE.parent / "build" / "stage1"
DAILY_A = "/Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz"
CAL_A = "/Users/alvinfung/apollo_data/cb702_pre_v2/sessions.txt"
FT_SHA = "ade1d7802eaf70aa60a9b5514d79b72084876d9601b0999328c9b1aad0cf0de7"
DISC_LAST = "2020-12-31"
N_SHUF = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
SEED = 1121
FEATS = [f"f{i:02d}" for i in range(1, 21)]
TWO = {"f15", "f16"}
SHELF_REL = {"f05", "f07"}                               # §10 / stage-1 shelf_relatives
FLOOR3, FLOOR4, FLOOR5 = 1.10, 1.15, 1.10                # §10 final floors
GROUPS = {"gap": ["f01", "f02"], "runup": ["f03", "f04", "f17"], "highs": ["f05", "f06", "f07"], "base": ["f08", "f09"],
          "tight": ["f10", "f11"], "volume": ["f12", "f13"], "strength": ["f14"], "structure": ["f15", "f16", "f20"],
          "size": ["f18", "f19"]}
# A3: run.txt 'per year' lines (2017-2020), the ONLY lines read from that file
RUN_TXT_B1 = {"2017": (337, 0.043, 0.056, 1.30), "2018": (419, 0.021, 0.037, 1.78),
              "2019": (442, 0.039, 0.063, 1.61), "2020": (706, 0.192, 0.303, 1.57)}

OUT = []


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    OUT.append(s)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for ch in iter(lambda: fh.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


# ---------------------------------------------------------------- independent helpers
def thirds_of(vals, tick, midrank=True):
    """0/1/2 = bottom/middle/top by np.array_split of the sorted order. midrank: a tied block goes whole to the third of
    position floor((first+last)/2). midrank=False: ticker tie-break (B1 only, PRE-REG 6)."""
    n = len(vals)
    order = np.lexsort((tick, vals))
    pos3 = np.empty(n, dtype=np.int8)
    for k, chunk in enumerate(np.array_split(np.arange(n), 3)):
        pos3[chunk] = k
    out = np.empty(n, dtype=np.int8)
    if not midrank:
        out[order] = pos3
        return out
    sv = vals[order]
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sv[j + 1] == sv[i]:
            j += 1
        out[order[i:j + 1]] = pos3[(i + j) // 2]
        i = j + 1
    return out


def thirds_within(df, col, keycol, min_n, mask=None, midrank=True):
    x = df[col].to_numpy(float)
    ok = np.isfinite(x) if mask is None else (np.isfinite(x) & mask)
    out = np.full(len(df), -1, dtype=np.int8)
    keys = df[keycol].to_numpy()
    tick = df.ticker.to_numpy()
    for k in pd.unique(keys[ok]):
        pos = np.flatnonzero(ok & (keys == k))
        if len(pos) < min_n:
            continue
        out[pos] = thirds_of(x[pos], tick[pos], midrank)
    return out


def two_within(df, col, keycol, mask=None, min_each=2):
    """2 = yes, 0 = no, within strata holding >= min_each of each; -1 otherwise."""
    x = df[col].to_numpy(float)
    ok = np.isfinite(x) if mask is None else (np.isfinite(x) & mask)
    out = np.full(len(df), -1, dtype=np.int8)
    keys = df[keycol].to_numpy()
    for k in pd.unique(keys[ok]):
        pos = np.flatnonzero(ok & (keys == k))
        yes = x[pos] == 1
        if yes.sum() < min_each or (~yes).sum() < min_each:
            continue
        out[pos] = np.where(yes, 2, 0)
    return out


def rate(w, n, smooth):
    return (w + 0.5) / (n + 1) if smooth else w / n


def thirds_ratio(y, g):
    """pooled top rate / bottom rate; smoothed (w+0.5)/(n+1) ONLY when the top or bottom third holds zero winners."""
    t, b = g == 2, g == 0
    wt, nt, wb, nb = y[t].sum(), t.sum(), y[b].sum(), b.sum()
    sm = wt == 0 or wb == 0
    return rate(wt, nt, sm) / rate(wb, nb, sm), (wt, nt, wb, nb, y[g == 1].sum(), (g == 1).sum())


def mh_ratio(y, g, strat):
    """Mantel-Haenszel RISK ratio yes vs no over strata: sum a*n0/N / sum c*n1/N (a, c = winners among yes, no)."""
    m = g >= 0
    num = den = 0.0
    for k in pd.unique(strat[m]):
        s = m & (strat == k)
        yes, no = s & (g == 2), s & (g == 0)
        n1, n0 = yes.sum(), no.sum()
        N = n1 + n0
        a, c = y[yes].sum(), y[no].sum()
        num += a * n0 / N
        den += c * n1 / N
    if num == 0 or den == 0:                             # zero-winner guard (never fired on real labels; reported)
        return float("nan")
    return num / den


def ratio_of(f, y, g, strat):
    if f in TWO:
        return mh_ratio(y, g, strat), None
    return thirds_ratio(y, g)


# ---------------------------------------------------------------- permutation (vectorised)
class Perm:
    """Per-event keys u[s, event] (one draw per event per shuffle, shared by all features; events in fixed order
    (era, E, ticker)). For a feature, within each month the labels of the events SCORED on it are reassigned among those
    same events in the order of their keys (a uniform within-month permutation of the scored subset)."""

    def __init__(self, n_events, n_shuf, seed):
        self.rng = np.random.default_rng(seed)
        self.U = self.rng.random((n_shuf, n_events), dtype=np.float64)
        self.S = n_shuf

    def log_ratios(self, f, y, g, month_code, scored, chunk=1000):
        idx = np.flatnonzero(scored)                      # events scored on f (assigned or not; unassigned carry g=-1)
        mc = month_code[idx]
        base = np.lexsort((idx, mc))                     # positional order within month
        idx = idx[base]
        mc = mc[base]
        yi = y[idx].astype(np.int32)
        gi = g[idx]
        out = np.empty(self.S)
        if f in TWO:
            asg = gi >= 0
            ks = np.unique(mc[asg])
            kpos = {k: i for i, k in enumerate(ks)}
            K = len(ks)
            kk = np.array([kpos.get(k, -1) for k in mc])
            Ym = np.zeros((len(idx), K)); Nm = np.zeros((len(idx), K))
            yes = (gi == 2); no = (gi == 0)
            Iy = np.zeros((len(idx), K)); In = np.zeros((len(idx), K))
            Iy[np.flatnonzero(yes), kk[yes]] = 1
            In[np.flatnonzero(no), kk[no]] = 1
            n1 = Iy.sum(0); n0 = In.sum(0); N = n1 + n0
        for s0 in range(0, self.S, chunk):
            s1 = min(self.S, s0 + chunk)
            key = mc[None, :].astype(np.float64) * 2.0 + self.U[s0:s1][:, idx]
            perm = np.argsort(key, axis=1, kind="stable")    # k-th event (by month then key) gives its label to k-th positional event
            Yp = yi[perm]
            if f in TWO:
                a = Yp @ Iy; c = Yp @ In
                num = (a * n0 / N).sum(1); den = (c * n1 / N).sum(1)
                num = np.where(num == 0, np.nan, num); den = np.where(den == 0, np.nan, den)
                out[s0:s1] = np.log(num / den)
            else:
                t, b = gi == 2, gi == 0
                wt = Yp[:, t].sum(1); wb = Yp[:, b].sum(1)
                nt, nb = t.sum(), b.sum()
                sm = (wt == 0) | (wb == 0)
                rt = np.where(sm, (wt + 0.5) / (nt + 1), wt / nt)
                rb = np.where(sm, (wb + 0.5) / (nb + 1), wb / max(nb, 1))
                with np.errstate(divide="ignore"):
                    out[s0:s1] = np.log(rt / rb)
        return out


def main():
    P("# STEP 4 BLIND RECOUNT — DISCOVERY (prereg §5.1-5.2, §10 floors + A1 + A3). $0, local files, no network/DB.")
    P(f"prereg sha256 {sha(HERE.parents[3] / 'docs/analysis/ep_winner_study_prereg_2026-11-21.md')}")
    ft_sha = sha(ST1 / "feature_table.tsv.gz")
    P(f"feature_table.tsv.gz sha256 {ft_sha} (stage-1 record {FT_SHA[:8]}…: {'MATCH' if ft_sha == FT_SHA else 'MISMATCH'})")
    assert ft_sha == FT_SHA

    # ------------------------------------------------------------ discovery events only (firewall)
    ft = pd.read_csv(ST1 / "feature_table.tsv.gz", sep="\t", dtype={"ticker": str, "E": str, "month": str, "year": str, "quarter": str},
                     keep_default_na=False, na_values=[""])
    n_all = len(ft)
    ft = ft[(ft.set == "DISC")].copy()
    assert (ft.era == "A").all() and ft.E.max() <= DISC_LAST and len(ft) == 2414, (ft.era.unique(), ft.E.max(), len(ft))
    assert ((ft.E <= DISC_LAST) == True).all()
    P(f"feature table rows {n_all}; DISCOVERY kept {len(ft)} (era A only, E {ft.E.min()} .. {ft.E.max()}); "
      f"CONFIRM rows ({n_all - len(ft)}) dropped at read and never touched")
    ft = ft.sort_values(["era", "E", "ticker"], kind="mergesort").reset_index(drop=True)
    for c in FEATS + ["B1", "B2", "adr20_raw"]:
        ft[c] = pd.to_numeric(ft[c], errors="coerce")

    pop = pd.read_csv(ST1 / "population.tsv", sep="\t", dtype={"ticker": str, "E": str})
    pop = pop[(pop.era == "A") & (pop.E <= DISC_LAST)]
    ft = ft.merge(pop[["ticker", "E", "open"]].rename(columns={"open": "open_pop"}), on=["ticker", "E"], how="left", validate="1:1")
    assert ft.open_pop.notna().all()

    # ------------------------------------------------------------ outcomes (own read of the raw era-A daily file)
    cal = np.array([s.strip() for s in open(CAL_A) if s.strip()], dtype="U10")
    assert (np.sort(cal) == cal).all() and len(np.unique(cal)) == len(cal)
    ciE = np.searchsorted(cal, ft.E.to_numpy(dtype="U10"))
    assert (cal[ciE] == ft.E.to_numpy(dtype="U10")).all()
    last_ci = int(ciE.max()) + 60
    cut_date = cal[last_ci]
    P(f"forward read cut AT READ: bars dated <= {cut_date} (= calendar session ci(last discovery E {ft.E.max()}) + 60)")
    need = set(ft.ticker)
    parts = []
    for ch in pd.read_csv(DAILY_A, header=None, names=["t", "d", "o", "h", "l", "c", "v"], dtype={"t": str, "d": str},
                          keep_default_na=False, chunksize=2_000_000):
        ch = ch[(ch.d <= cut_date) & ch.t.isin(need)]
        parts.append(ch[["t", "d", "o", "c"]])
    bars = pd.concat(parts, ignore_index=True)
    assert bars.d.max() <= cut_date
    P(f"era-A bars read for {bars.t.nunique()} discovery tickers; latest bar date read {bars.d.max()}")
    bci = np.searchsorted(cal, bars.d.to_numpy(dtype="U10"))
    on = (bci < len(cal)) & (cal[np.minimum(bci, len(cal) - 1)] == bars.d.to_numpy(dtype="U10"))
    P(f"off-calendar bar rows dropped: {int((~on).sum())}")
    bars = bars[on].copy(); bars["ci"] = bci[on]
    assert not bars.duplicated(["t", "ci"]).any()
    by_t = {t: (g.ci.to_numpy(), g.o.to_numpy(), g.c.to_numpy()) for t, g in bars.sort_values(["t", "ci"]).groupby("t", sort=False)}
    big = np.zeros(len(ft), dtype=np.int8); mon = np.zeros(len(ft), dtype=np.int8)
    short = 0; open_mis = 0; max_ci_used = 0
    for i, (t, e_ci, op_pop) in enumerate(zip(ft.ticker, ciE, ft.open_pop)):
        assert ft.E.iat[i] <= DISC_LAST                  # FIREWALL: an outcome is built only for a discovery event
        c_i, o_a, c_a = by_t[t]
        k = np.searchsorted(c_i, e_ci)
        assert k < len(c_i) and c_i[k] == e_ci, (t, ft.E.iat[i])
        op = o_a[k]
        if abs(op / op_pop - 1) > 1e-6:
            open_mis += 1
        w = (c_i >= e_ci) & (c_i <= e_ci + 60)
        if c_i[w].max() < e_ci + 60:
            short += 1
        max_ci_used = max(max_ci_used, int(c_i[w].max()))
        hc = c_a[w].max()
        big[i] = hc >= 1.5 * op
        mon[i] = hc >= 2.0 * op
    assert cal[max_ci_used] <= cut_date
    P(f"open(E) from bars vs population.tsv open: {open_mis} mismatches > 1e-6; events whose window ends before E+60 (kept, no survivorship drop): {short}")
    ft["big"] = big; ft["mon"] = mon
    y = big.astype(np.int64)

    P("")
    P("## BASE RATE — big winner = highest close over calendar sessions E..E+60 (E's close included) >= 1.5 x open(E)")
    P(f"  DISCOVERY: {y.sum()} of {len(y)} = {y.mean():.4f}  | monster (>= 2.0x): {mon.sum()} = {mon.mean():.4f}")
    for yr, g in ft.groupby("year"):
        P(f"    {yr}: {int(g.big.sum()):4d} / {len(g):4d} = {g.big.mean():.4f}")
    ex20 = (ft.year != "2020").to_numpy()
    P(f"  2016-19: {y[ex20].sum()} / {ex20.sum()} = {y[ex20].mean():.4f}")

    b1s = np.isfinite(ft.B1.to_numpy(float))
    for lab, mm in (("2016-19", ex20), ("2020", ~ex20)):
        P(f"  {lab}: B1-scored {y[mm & b1s].sum()}/{(mm & b1s).sum()} = {y[mm & b1s].mean():.4f} | B1-null (short history) {y[mm & ~b1s].sum()}/{(mm & ~b1s).sum()} = {y[mm & ~b1s].mean():.4f}")
    month = ft.month.to_numpy()
    mcode = pd.factorize(month)[0]
    ft["mkey"] = month

    # ------------------------------------------------------------ A3: B1 reproduction gate
    P("")
    P("## A3 GATE — B1 shelf distance (dmin), thirds within month (>= 6 scored), TICKER tie-break, top = high dmin")
    gB1 = thirds_within(ft, "B1", "mkey", 6, midrank=False)
    ok_all = True
    for yr in ["2017", "2018", "2019", "2020"]:
        m = (ft.year == yr).to_numpy()
        t, b = m & (gB1 == 2), m & (gB1 == 0)
        n = int((m & (gB1 >= 0)).sum())
        rb, rt = y[b].mean(), y[t].mean()
        exp = RUN_TXT_B1[yr]
        match = n == exp[0] and round(rb, 3) == exp[1] and round(rt, 3) == exp[2] and round(rt / rb, 2) == exp[3]
        ok_all &= match
        P(f"    {yr}: n {n:4d} bottom {rb:.3f} top {rt:.3f} ratio {rt / rb:.2f}   run.txt n {exp[0]} {exp[1]:.3f} {exp[2]:.3f} {exp[3]:.2f} -> {'MATCH' if match else 'MISS'}")
    r16 = ((ft.year == "2016").to_numpy() & (gB1 >= 0)).sum()
    P(f"    (2016 assigned {r16}; total assigned {(gB1 >= 0).sum()} of {np.isfinite(ft.B1).sum()} scored)")
    if not ok_all:
        P("A3 REPRODUCTION FAILED -> STOP (no feature verdict printed)")
        (HERE / "recount_discovery.txt").write_text("\n".join(OUT) + "\n")
        sys.exit(2)
    P("  A3: all four discovery years reproduce run.txt -> feature verdicts may print")

    # ------------------------------------------------------------ assignments
    adr = ft.adr20_raw.to_numpy(float)
    assert np.isfinite(adr).all()
    ft["qkey"] = ft.era + ft.quarter
    gADR = thirds_within(ft, "adr20_raw", "qkey", 1)   # ADR third over ALL discovery events of the era-quarter (stage-1 res.)
    ft["adr_strat"] = ft.qkey + "_" + gADR.astype(str)
    gDM = thirds_within(ft, "B1", "qkey", 1)            # dmin third of the era-quarter, non-NULL dmin only
    ft["dm_strat"] = np.where(gDM >= 0, ft.qkey + "_" + gDM.astype(str), "NA")
    dm_ok = gDM >= 0

    def assign(f, keycol, mask=None, min_n=6):
        if f in TWO:
            return two_within(ft, f, keycol, mask)
        return thirds_within(ft, f, keycol, min_n, mask)

    perm = Perm(len(ft), N_SHUF, SEED)
    P("")
    P(f"## PERMUTATION: {N_SHUF} shuffles, default_rng({SEED}), one key per event per shuffle (fixed order era,E,ticker), "
      "labels permuted within month among events scored on the feature; p = (1 + #|log r*| >= |log r|) / (S + 1)")

    res = {}
    for f in FEATS:
        x = ft[f].to_numpy(float)
        scored = np.isfinite(x)
        g = assign(f, "mkey")
        r_obs, cnt = ratio_of(f, y, g, month)
        lr = perm.log_ratios(f, y, g, mcode, scored)
        lo = np.log(r_obs)
        p = (1 + np.sum(np.abs(lr) >= abs(lo) - 1e-12)) / (N_SHUF + 1)
        sd = np.nanstd(lr)
        # cond 3 (ex-2020)
        g3 = g.copy(); g3[~ex20] = -1
        r3, _ = ratio_of(f, y, g3, month)
        # cond 4 ADR-neutral
        if f in TWO:
            g4 = two_within(ft, f, "adr_strat")
            r4 = mh_ratio(y, g4, ft.adr_strat.to_numpy())
        else:
            g4 = thirds_within(ft, f, "adr_strat", 9)
            r4, _ = thirds_ratio(y, g4)
        # cond 5 (shelf relatives)
        r5 = np.nan
        if f in SHELF_REL:
            g5 = thirds_within(ft, f, "dm_strat", 9, mask=dm_ok)
            r5, _ = thirds_ratio(y, g5)
        # monster ratio (description)
        rm, _ = ratio_of(f, mon.astype(np.int64), g, month)
        up = r_obs >= 1
        c1 = r_obs >= 1.25 or r_obs <= 0.80
        c2 = p <= 0.05
        c3 = (r3 >= FLOOR3) if up else (r3 <= 0.91)
        c4 = (r4 >= FLOOR4) if up else (r4 <= 0.87)
        c5 = True if f not in SHELF_REL else ((r5 >= FLOOR5) if up else (r5 <= 1 / FLOOR5 + 1e-9 and r5 <= 0.91))
        # tie-heavy check (thirds features): pooled top / bottom share of scored
        tie = ""
        if f not in TWO:
            nsc = scored.sum()
            tie = f"top {np.sum(g == 2) / nsc:.3f} bot {np.sum(g == 0) / nsc:.3f}"
        else:
            yes_n, no_n = int(np.sum(x == 1)), int(np.sum(x == 0))
            tie = f"yes {yes_n} no {no_n} small {min(yes_n, no_n) / (yes_n + no_n):.3f}"
        layout = (int(np.sum(g3 == 2)), int(np.sum(g3 == 0)), int(np.sum(g4 >= 0)),
                  int(np.sum(thirds_within(ft, f, "dm_strat", 9, mask=dm_ok) >= 0)) if f not in TWO else int(np.sum(two_within(ft, f, "dm_strat", mask=dm_ok) >= 0)))
        res[f] = dict(layout=layout, r=r_obs, cnt=cnt, p=p, sd=sd, r3=r3, r4=r4, r5=r5, rm=rm, c1=c1, c2=c2, c3=c3, c4=c4, c5=c5,
                      n_sc=int(scored.sum()), n_as=int((g >= 0).sum()), tie=tie)

    P("")
    P("## PER-FEATURE TABLE (discovery, own full scored set). ratio = top/bottom third (f15, f16: MH yes/no). "
      "dir = carried direction if any. c1 |r|>=1.25/<=0.80; c2 p<=0.05; c3 ex-2020 >=1.10/<=0.91; c4 ADR-neutral >=1.15/<=0.87; c5 shelf rel. >=1.10/<=0.91")
    P(f"{'feat':5} {'scored':>6} {'assgn':>6} {'bottom w/n':>12} {'middle w/n':>12} {'top w/n':>12} {'ratio':>6} {'p':>7} "
      f"{'ex2020':>6} {'ADRneu':>6} {'dminth':>6} {'monst':>6}  c1 c2 c3 c4 c5  1-4  ties/groups")
    for f in FEATS:
        d = res[f]
        if d["cnt"] is not None:
            wt, nt, wb, nb, wm, nm = d["cnt"]
            bw, mw, tw = f"{wb}/{nb}", f"{wm}/{nm}", f"{wt}/{nt}"
        else:
            g = two_within(ft, f, "mkey")
            bw = f"{y[g == 0].sum()}/{(g == 0).sum()}(no)"
            tw = f"{y[g == 2].sum()}/{(g == 2).sum()}(yes)"
            mw = "-"
        r5s = f"{d['r5']:6.3f}" if np.isfinite(d["r5"]) else "     -"
        pass14 = d["c1"] and d["c2"] and d["c3"] and d["c4"]
        d["pass14"] = pass14
        d["pass15"] = pass14 and d["c5"]
        yn = lambda b: " Y" if b else " ."
        P(f"{f:5} {d['n_sc']:6d} {d['n_as']:6d} {bw:>12} {mw:>12} {tw:>12} {d['r']:6.3f} {d['p']:7.4f} {d['r3']:6.3f} {d['r4']:6.3f} {r5s} {d['rm']:6.3f} "
          f"{yn(d['c1'])} {yn(d['c2'])} {yn(d['c3'])} {yn(d['c4'])} {yn(d['c5']) if f in SHELF_REL else ' -'}  {' YES' if pass14 else '  no'}  {d['tie']}")
    P("  stratum layout (outcome-free; compare stage1/06_calibration.txt lines 7-26): ex-2020 top / bottom | ADR strata | dmin strata")
    for f in FEATS:
        a, b, c, d4 = res[f]["layout"]
        P(f"    {f} ex-2020 top {a:4d} bottom {b:4d} | ADR strata {c:4d} | dmin strata {d4:4d}")
    for f in TWO:
        g = two_within(ft, f, "mkey")
        r_pool = y[g == 2].mean() / y[g == 0].mean()
        P(f"  {f}: pooled rate(yes)/rate(no) (the biased pre-A1 statistic, description only) = {r_pool:.3f}; MH = {res[f]['r']:.3f}")

    # A1 sanity: MH on synthetic no-effect labels centres near 1.0 (the stage-1 synthetic base rates)
    rng = np.random.default_rng(SEED)
    pr = np.where(ex20, 0.049, 0.25)
    mhs = {f: [] for f in TWO}
    for _ in range(300):
        ys = (rng.random(len(ft)) < pr).astype(np.int64)
        for f in TWO:
            g = two_within(ft, f, "mkey")
            mhs[f].append(mh_ratio(ys, g, month))
    P("  A1 check, synthetic NO-effect labels (4.9% 2016-19 / 25% 2020, 300 draws): MH median "
      + ", ".join(f"{f} {np.nanmedian(mhs[f]):.3f}" for f in sorted(TWO)))

    passers14 = [f for f in FEATS if res[f]["pass14"]]
    passers15 = [f for f in FEATS if res[f]["pass15"]]
    P("")
    P(f"## CONDITIONS 1-4 PASS: {passers14 if passers14 else 'none'}")
    P(f"## CONDITIONS 1-5 PASS (cond 5 applies to shelf relatives f05, f07 only): {passers15 if passers15 else 'none'}")
    for f in passers14:
        d = res[f]
        P(f"   {f}: direction {'HIGH values win' if d['r'] >= 1 else 'LOW values win'} (ratio {d['r']:.3f})")

    # ------------------------------------------------------------ condition 6: group winners + cap (z on common sets)
    cands = FEATS[:]                                     # no feature ruled description-only (stage-1 decisions; recomputed tie shares above)

    def z_on(mask, flist):
        zs = {}
        for f in flist:
            x = ft[f].to_numpy(float)
            sc = mask & np.isfinite(x)
            g = assign(f, "mkey", mask=mask)
            r, _ = ratio_of(f, y, g, month)
            lr = perm.log_ratios(f, y, g, mcode, sc)
            zs[f] = (abs(np.log(r)) / np.nanstd(lr), r, (1 + np.sum(np.abs(lr) >= abs(np.log(r)) - 1e-12)) / (N_SHUF + 1))
        return zs

    P("")
    P("## CONDITION 6 — group winner = largest z = |log ratio| / SD(permuted log ratios) on the events scored on every candidate member of the group")
    winners = []
    for gname, members in GROUPS.items():
        m = np.ones(len(ft), bool)
        for f in members:
            m &= np.isfinite(ft[f].to_numpy(float))
        zs = z_on(m, members)
        best = sorted(members, key=lambda f: (-zs[f][0], zs[f][2], int(f[1:])))[0]
        winners.append(best)
        P(f"  {gname:9} common n {int(m.sum()):4d}: " + "  ".join(f"{f} z {zs[f][0]:.2f} (r {zs[f][1]:.3f})" for f in members) + f"  -> winner {best}")
    mall = np.ones(len(ft), bool)
    for f in cands:
        mall &= np.isfinite(ft[f].to_numpy(float))
    zall = z_on(mall, winners)
    cap = sorted(winners, key=lambda f: (-zall[f][0], zall[f][2], int(f[1:])))[:4]
    P(f"  cap common set (scored on ALL {len(cands)} candidates): n {int(mall.sum())}; group winners z: "
      + "  ".join(f"{f} {zall[f][0]:.2f}" for f in sorted(winners, key=lambda f: -zall[f][0])))
    P(f"  top four group winners: {cap}")
    carried = [f for f in FEATS if res[f]["pass15"] and f in cap]
    P("")
    P(f"## CARRIED SET (all six conditions, literal reading: group winner among ALL candidates): {carried if carried else 'none'}")
    # alternative reading: group winner chosen among the 1-5 passers only
    alt = []
    for gname, members in GROUPS.items():
        pm = [f for f in members if res[f]["pass15"]]
        if not pm:
            continue
        m = np.ones(len(ft), bool)
        for f in members:
            m &= np.isfinite(ft[f].to_numpy(float))
        zs = z_on(m, pm)
        alt.append(sorted(pm, key=lambda f: (-zs[f][0], zs[f][2], int(f[1:])))[0])
    if alt:
        za = z_on(mall, alt)
        alt = sorted(alt, key=lambda f: (-za[f][0], za[f][2], int(f[1:])))[:4]
    P(f"## CARRIED SET (alternative reading: group winner among the 1-5 passers only): {alt if alt else 'none'}")

    P("")
    P("## READINGS USED (any difference vs stage 3 should trace to one of these)")
    P("  R1 smoothing (w+0.5)/(n+1) applied ONLY when a top or bottom third holds zero winners (observed or per shuffle); never fired on observed data unless printed ratio is 0/inf")
    P("  R2 f15/f16: Mantel-Haenszel RISK ratio sum(a*n0/N)/sum(c*n1/N), strata = months with >= 2 yes and >= 2 no (no >= 6 floor); same in cond 3 (2016-19 months) and cond 4 (ADR strata, >= 2 each)")
    P("  R3 ADR-neutral: ADR third (encoder adr20_raw) within era-quarter over ALL discovery events, mid-rank ties; feature thirds within (quarter, ADR third) strata with >= 9 scored")
    P("  R4 cond 5: dmin third within era-quarter over discovery events with non-NULL dmin; feature thirds within strata >= 9 scored")
    P("  R5 mid-rank tie: a tied block goes whole to the third of sorted position floor((first+last)/2); B1 alone ticker tie-break")
    P("  R6 permutation: one key per event per shuffle shared by all features; within-month reassignment among events scored on f; same shuffles reused for cond-6 SDs")
    P("  R7 cond 6: candidates = all 20 (none description-only); z SD = std of the permuted log ratios on the common set; ties -> smaller own p -> lower number")
    P("  R8 open(E) mismatches vs population.tsv are print rounding only (EXPE 2018-04-27, SQQQ 2020-02-28, QCOM 2020-11-05: |diff| < 5e-6 relative)")
    P("  R9 two-group months: >= 2 of each gave the same 2151 / 1877 assigned events as stage 1's '>= 6 and >= 2 of each'")
    P("  NOT computed (not needed for carry): 90% bootstrap intervals, family-wide p, §5.5 extra readings")
    (HERE / "recount_discovery.txt").write_text("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
