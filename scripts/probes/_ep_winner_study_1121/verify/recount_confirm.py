#!/usr/bin/env python3
"""BLIND RECOUNT of the EP winner study CONFIRM run (prereg docs/analysis/ep_winner_study_prereg_2026-11-21.md, §5.3/§5.5/§5.6/§10/§11).

Independent re-implementation from the prereg text. NOT imported: stage1/stats.py, stage4_freeze/hreads.py, stage3/discovery.py.
NOT opened: build/stage5_confirm/ (the run being recounted), scripts/probes/_594_outcome_qm_1121/build/events_scored.tsv.gz.
Inputs: stage1/population.tsv + feature_table.tsv.gz (features), stage4_freeze/h_reads.tsv.gz (frozen H1-H4),
stage4_freeze/confirm_n.tsv (outcome-free counts, reproduced as a gate), stage3/discovery_outcomes.tsv.gz (positive control
for the label function on era A), and the raw daily files (own loader). $0, local, no network.
Sealed (#710): every era-B row dated after 2024-12-31 is dropped AT READ and asserted.
"""
from __future__ import annotations

import hashlib
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BUILD = ROOT / "build"
REPO = ROOT.parents[2]
PREREG = REPO / "docs/analysis/ep_winner_study_prereg_2026-11-21.md"
DATA = "/Users/alvinfung/apollo_data"
DAILY = {"A": f"{DATA}/cb702_pre_v2/daily_closes_all.csv.gz", "B": f"{DATA}/cb702/daily_closes_all.csv.gz"}
CAL = {"A": f"{DATA}/cb702_pre_v2/sessions.txt",
       "B": f"{DATA}/cb702/qm_streams/track_a_1023/spy_sessions_eraB_le_2024-12-31.txt"}
CUT_B = "2024-12-31"
NSHUF = 10_000
NBOOT = 2_000
SEED = 1121

OUT = []


def P(*a):
    s = " ".join(str(x) for x in a)
    OUT.append(s)
    print(s, flush=True)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for ch in iter(lambda: fh.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


# ---------------------------------------------------------------- 0. prereg hash gate
ph = sha(PREREG)
P("# BLIND RECOUNT — EP winner study CONFIRM (E >= 2021-01-01)")
P(f"prereg sha256 {ph}")
if not ph.startswith("6c581b6a"):
    P("STOP: prereg sha256 does not begin 6c581b6a")
    sys.exit(2)
P("prereg hash gate OK (begins 6c581b6a)")
for f in ("build/stage1/feature_table.tsv.gz", "build/stage1/population.tsv", "build/stage4_freeze/h_reads.tsv.gz",
          "build/stage4_freeze/confirm_n.tsv", "build/stage3/discovery_outcomes.tsv.gz"):
    P(f"input {f} sha256 {sha(ROOT / f)[:16]}…")
assert sha(BUILD / "stage4_freeze/h_reads.tsv.gz").startswith("0b995389"), "h_reads hash != §11.1"
assert sha(BUILD / "stage1/feature_table.tsv.gz").startswith("ade1d780"), "feature table hash != §10"

# ---------------------------------------------------------------- 1. population + frozen values
pop = pd.read_csv(BUILD / "stage1/population.tsv", sep="\t", dtype={"ticker": str, "E": str, "era": str, "month": str},
                  keep_default_na=False)
ft = pd.read_csv(BUILD / "stage1/feature_table.tsv.gz", sep="\t", dtype=str, keep_default_na=False)
hr = pd.read_csv(BUILD / "stage4_freeze/h_reads.tsv.gz", sep="\t", dtype=str, keep_default_na=False)
for d in (pop, ft, hr):
    assert len(d) == 4665
key = ["era", "ticker", "E"]
ev = pop[pop.E >= "2021-01-01"].copy()
ev = ev.sort_values(["era", "E", "ticker"], kind="mergesort").reset_index(drop=True)
assert len(ev) == 2251 and (ev.era == "A").sum() == 867 and (ev.era == "B").sum() == 1384, len(ev)
assert ev.E.max() <= "2024-09-30" and ev[ev.era == "A"].E.max() <= "2022-04-04" and ev[ev.era == "B"].E.min() == "2022-04-05"
ftc = ft[ft.E >= "2021-01-01"][key + ["set", "f02", "f03", "f09", "f18", "B2", "adr20_raw"]]
hrc = hr[hr.E >= "2021-01-01"][key + ["set", "H1", "H2", "H3", "H4"]]
assert (ftc.set == "CONF").all() and (hrc.set == "CONF").all()
ev = ev.merge(ftc.drop(columns="set"), on=key, how="left", validate="1:1").merge(hrc.drop(columns="set"), on=key, how="left", validate="1:1")
assert len(ev) == 2251


def num(s):
    return pd.to_numeric(s.replace("", np.nan), errors="raise").to_numpy(dtype=float)


for c in ("f02", "f03", "f09", "f18", "B2", "adr20_raw", "H1", "H2", "H3", "H4"):
    ev[c] = num(ev[c])
b2, h4 = ev.B2.to_numpy(), ev.H4.to_numpy()
assert np.array_equal(np.isnan(b2), np.isnan(h4)) and np.allclose(b2[~np.isnan(b2)], h4[~np.isnan(h4)], rtol=0, atol=1e-9)
P("H4 == stage-1 B2 on every confirm row (ASSERT OK)")
for c in ("H1", "H2", "H3"):
    v = ev[c].to_numpy()
    assert set(np.unique(v[~np.isnan(v)])) <= {0.0, 1.0}
N = len(ev)
era = ev.era.to_numpy()
month_key = (ev.era + "|" + ev.month).to_numpy()
quarter_key = (ev.era + "|" + ev.quarter).to_numpy()


# ---------------------------------------------------------------- 2. assignment (own code, from prereg text)
def thirds_block(vals):
    """np.array_split of the sorted order; a tied block goes whole to the third holding its mid-rank position
    ((first+last)//2, i.e. the lower middle on a half-integer — stage-1 resolution accepted in §10)."""
    n = len(vals)
    order = np.argsort(vals, kind="mergesort")
    sv = vals[order]
    bounds = np.cumsum([len(x) for x in np.array_split(np.arange(n), 3)])  # end positions (exclusive)
    pos_third = np.searchsorted(bounds, np.arange(n), side="right")
    out = np.empty(n, dtype=int)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sv[j + 1] == sv[i]:
            j += 1
        t = pos_third[(i + j) // 2]
        out[order[i:j + 1]] = t
        i = j + 1
    return out


def assign_thirds(x, strata, min_n=6):
    """-1 = not in test; 0 bottom, 1 middle, 2 top within each stratum with >= min_n scored events."""
    a = np.full(len(x), -1)
    sc = ~np.isnan(x)
    groups = defaultdict(list)
    for i in np.where(sc)[0]:
        groups[strata[i]].append(i)
    for g, idx in groups.items():
        if len(idx) >= min_n:
            idx = np.array(idx)
            a[idx] = thirds_block(x[idx])
    return a


def assign_two(x, strata, min_n=6, min_each=2):
    """-1 = not in test; 1 = yes, 0 = no; strata with >= min_n scored and >= min_each of each group."""
    a = np.full(len(x), -1)
    sc = ~np.isnan(x)
    groups = defaultdict(list)
    for i in np.where(sc)[0]:
        groups[strata[i]].append(i)
    for g, idx in groups.items():
        idx = np.array(idx)
        y = x[idx]
        if len(idx) >= min_n and (y == 1).sum() >= min_each and (y == 0).sum() >= min_each:
            a[idx] = y.astype(int)
    return a


def pct_rank_within(x, strata, mask):
    """(average rank - 0.5)/n within stratum, among mask events."""
    out = np.full(len(x), np.nan)
    groups = defaultdict(list)
    for i in np.where(mask)[0]:
        groups[strata[i]].append(i)
    for g, idx in groups.items():
        idx = np.array(idx)
        r = pd.Series(x[idx]).rank(method="average").to_numpy()
        out[idx] = (r - 0.5) / len(idx)
    return out


# combination §5.6: f02 (1-rank), f03, f09, f18 (1-rank), equal weight, HIGH wins
allm = ~(np.isnan(ev.f02.to_numpy()) | np.isnan(ev.f03.to_numpy()) | np.isnan(ev.f09.to_numpy()) | np.isnan(ev.f18.to_numpy()))
combo = np.full(N, np.nan)
r02 = 1 - pct_rank_within(ev.f02.to_numpy(), month_key, allm)
r03 = pct_rank_within(ev.f03.to_numpy(), month_key, allm)
r09 = pct_rank_within(ev.f09.to_numpy(), month_key, allm)
r18 = 1 - pct_rank_within(ev.f18.to_numpy(), month_key, allm)
combo[allm] = ((r02 + r03 + r09 + r18) / 4)[allm]
ev["combo"] = combo

# tests: (name, label, column, kind, direction). direction for thirds: "LOW"/"HIGH"; for two-group: "NO"/"YES"
TESTS = [
    ("f02", "gap size in daily ranges", "f02", "thirds", "LOW"),
    ("f03", "short run-up (20)", "f03", "thirds", "HIGH"),
    ("f09", "base depth (40)", "f09", "thirds", "HIGH"),
    ("f18", "price (raw)", "f18", "thirds", "LOW"),
    ("combo", "combination f02+f03+f09+f18", "combo", "thirds", "HIGH"),
    ("H1", "below the 200-day at the open", "H1", "two", "NO"),
    ("H2", "in a downtrend", "H2", "two", "NO"),
    ("H3", "above all moving averages at the open", "H3", "two", "YES"),
    ("H4", "ADR20 (his ruling)", "H4", "thirds", "HIGH"),
]
ASG = {}
for name, _, col, kind, _d in TESTS:
    x = ev[col].to_numpy()
    ASG[name] = assign_thirds(x, month_key) if kind == "thirds" else assign_two(x, month_key)

# ---------------------------------------------------------------- 3. OUTCOME-FREE GATE: reproduce confirm_n.tsv
cn = pd.read_csv(BUILD / "stage4_freeze/confirm_n.tsv", sep="\t", dtype={"row": str, "era": str})
P("\n## outcome-free gate: confirm n per test per era vs stage4_freeze/confirm_n.tsv (BEFORE any label)")
bad = 0
for name, _, col, kind, _d in TESTS:
    x = ev[col].to_numpy()
    a = ASG[name]
    for e in ("A", "B", "A+B"):
        m = np.ones(N, bool) if e == "A+B" else (era == e)
        sc = int((~np.isnan(x) & m).sum())
        it = (a >= 0) & m
        months = len(set(month_key[it]))
        if kind == "thirds":
            b, mid, t = int(((a == 0) & m).sum()), int(((a == 1) & m).sum()), int(((a == 2) & m).sum())
        else:
            b, mid, t = int(((a == 1) & m).sum()), 0, int(((a == 0) & m).sum())
        mine = (int(m.sum()), sc, months, int(it.sum()), b, mid, t)
        r = cn[(cn.row == name) & (cn.era == e)].iloc[0]
        ref = (int(r.events), int(r.scored), int(r.months), int(r.in_test), int(r.bottom_or_yes), int(r.middle), int(r.top_or_no))
        ok = mine == ref
        bad += not ok
        P(f"   {name:5s} {e:3s} events/scored/months/in_test/bottom|yes/middle/top|no mine {mine} ref {ref} -> {'MATCH' if ok else 'MISMATCH'}")
if bad:
    P(f"STOP: {bad} confirm_n rows do not reproduce")
    (HERE / "recount_confirm.txt").write_text("\n".join(OUT) + "\n")
    sys.exit(3)
P("   all 27 rows reproduce (ASSERT OK)")


# ---------------------------------------------------------------- 4. labels: own loader on the raw daily files
def read_cal(e):
    d = [ln.strip() for ln in open(CAL[e]) if ln.strip()]
    if e == "B":
        d = [x for x in d if x <= CUT_B]
    arr = np.array(sorted(d), dtype="U10")
    assert len(np.unique(arr)) == len(arr)
    return arr


cal = {e: read_cal(e) for e in "AB"}
assert cal["B"][-1] <= CUT_B
disc = pd.read_csv(BUILD / "stage3/discovery_outcomes.tsv.gz", sep="\t", dtype={"ticker": str, "E": str, "era": str}, keep_default_na=False)
assert (disc.E <= "2020-12-31").all() and len(disc) == 2414
need = {"A": set(ev.loc[ev.era == "A", "ticker"]) | set(disc.ticker), "B": set(ev.loc[ev.era == "B", "ticker"])}
bars = {}
for e in "AB":
    parts, dropped, nread = [], 0, 0
    for ch in pd.read_csv(DAILY[e], header=None, names=["t", "d", "o", "h", "l", "c", "v"],
                          dtype={"t": str, "d": str, "o": float, "h": float, "l": float, "c": float, "v": float},
                          keep_default_na=False, chunksize=2_000_000):
        nread += len(ch)
        if e == "B":
            m = ch.d <= CUT_B
            dropped += int((~m).sum())
            ch = ch[m]
        ch = ch[ch.t.isin(need[e])][["t", "d", "o", "c"]]
        parts.append(ch)
    df = pd.concat(parts, ignore_index=True)
    if e == "B":
        assert df.d.max() <= CUT_B, df.d.max()   # SEALED (#710)
    dv = df.d.to_numpy(dtype="U10")
    ci = np.searchsorted(cal[e], dv)
    on = (ci < len(cal[e])) & (cal[e][np.minimum(ci, len(cal[e]) - 1)] == dv)
    df = df[on].copy()
    df["ci"] = ci[on]
    df.sort_values(["t", "ci"], inplace=True, kind="mergesort")
    assert not df.duplicated(["t", "ci"]).any()
    for t, g in df.groupby("t", sort=False):
        bars[(e, t)] = (g.ci.to_numpy(), g.o.to_numpy(), g.c.to_numpy(), g.d.to_numpy())
    P(f"era {e} daily read: rows {nread}, dropped after {CUT_B} at read {dropped}, off-calendar {int((~on).sum())}, "
      f"kept {len(df)}, latest kept {df.d.max()}")
    del df, parts
assert max(b[3][-1] for (e, _), b in bars.items() if e == "B") <= CUT_B


def label(e, t, E, open_e, adr):
    ciE = int(np.searchsorted(cal[e], E))
    assert cal[e][ciE] == E
    b = bars.get((e, t))
    assert b is not None, (e, t)
    cis, o, c, _ = b
    k = np.searchsorted(cis, ciE)
    assert k < len(cis) and cis[k] == ciE, ("no bar on E", e, t, E)
    w = (cis >= ciE) & (cis <= ciE + 60)
    mx = c[w].max()
    r = mx / open_e
    return dict(maxr=r, big=int(r >= 1.5), mon=int(r >= 2.0), adrt=int(mx >= open_e * (1 + 8 * adr / 100)),
                nfwd=int(w.sum()), omis=int(abs(o[k] / open_e - 1) > 1e-6), odiff=abs(o[k] / open_e - 1))


# positive control: discovery labels vs stage3
dpop = pop[pop.E <= "2020-12-31"].merge(ft[key + ["adr20_raw"]], on=key, validate="1:1")
dpop["adr20_raw"] = num(dpop.adr20_raw)
dl = [label(r.era, r.ticker, r.E, r.open, r.adr20_raw) for r in dpop.itertuples()]
dchk = dpop[key].assign(big_m=[x["big"] for x in dl], mon_m=[x["mon"] for x in dl], adr_m=[x["adrt"] for x in dl]).merge(
    disc[key + ["big_winner", "monster", "adr_tail"]], on=key, validate="1:1")
mism = int((dchk.big_m != dchk.big_winner).sum() + (dchk.mon_m != dchk.monster).sum() + (dchk.adr_m != dchk.adr_tail).sum())
P(f"\n## positive control (label function on the 2,414 discovery events vs stage3/discovery_outcomes): "
  f"big {int(dchk.big_m.sum())} (stage3 {int(dchk.big_winner.sum())}), mismatching labels {mism}")
assert mism == 0

L = [label(r.era, r.ticker, r.E, r.open, r.adr20_raw) for r in ev.itertuples()]
for k_ in ("big", "mon", "adrt", "nfwd", "omis", "maxr", "odiff"):
    ev[k_] = [x[k_] for x in L]
P(f"confirm labels: every event has a bar on E (ASSERT OK); bar open(E) vs population open mismatches (>1e-6): {int(ev.omis.sum())} (max relative difference {ev.odiff.max():.1e}: 6-significant-digit rounding in the event file; labels use the population open); "
  f"events with < 61 bars in E..E+60 (kept): {int((ev.nfwd < 61).sum())} (A {int(((ev.nfwd < 61) & (ev.era == 'A')).sum())}, "
  f"B {int(((ev.nfwd < 61) & (ev.era == 'B')).sum())})")

P("\n## big-winner base rate (confirm; highest close E..E+60 >= 1.5 x open(E))")
for nm, m in (("era A (2021-01-01..2022-04-04)", era == "A"), ("era B (2022-04-05..2024-09-30)", era == "B"), ("pooled", np.ones(N, bool))):
    n = int(m.sum())
    P(f"   {nm:32s} n {n:5d} | big {int(ev.big[m].sum()):4d} ({ev.big[m].mean():.3f}) | monster {int(ev.mon[m].sum()):4d} "
      f"({ev.mon[m].mean():.3f}) | ADR tail {int(ev.adrt[m].sum()):4d} ({ev.adrt[m].mean():.3f})")
for y in sorted(ev.year.unique()):
    m = (ev.year == y).to_numpy()
    P(f"   {y} n {int(m.sum()):4d} big {int(ev.big[m].sum()):4d} ({ev.big[m].mean():.3f})")


# ---------------------------------------------------------------- 5. statistics
def oriented_thirds(a, y, d, sub=None, smooth=True):
    m = np.ones(len(a), bool) if sub is None else sub
    b, t = (a == 0) & m, (a == 2) & m
    wb, nb, wt, nt = y[b].sum(), b.sum(), y[t].sum(), t.sum()
    if smooth:
        rb, rt = (wb + 0.5) / (nb + 1), (wt + 0.5) / (nt + 1)
    else:
        rb = wb / nb if nb else np.nan
        rt = wt / nt if nt else np.nan
    with np.errstate(divide="ignore", invalid="ignore"):
        r = rt / rb if d == "HIGH" else rb / rt
    return r, (int(wb), int(nb), int(wt), int(nt))


def mh_yes_no(a, y, strata, sub=None):
    m = (a >= 0) if sub is None else ((a >= 0) & sub)
    num_, den = 0.0, 0.0
    groups = defaultdict(list)
    for i in np.where(m)[0]:
        groups[strata[i]].append(i)
    for g, idx in groups.items():
        idx = np.array(idx)
        yes = a[idx] == 1
        n1, n0 = yes.sum(), (~yes).sum()
        if n1 == 0 or n0 == 0:
            continue
        Nn = len(idx)
        a_ = y[idx][yes].sum()
        c_ = y[idx][~yes].sum()
        num_ += a_ * n0 / Nn
        den += c_ * n1 / Nn
    return num_, den


def oriented_two(a, y, d, strata, sub=None):
    nu, de = mh_yes_no(a, y, strata, sub)
    with np.errstate(divide="ignore", invalid="ignore"):
        rr = nu / de if de > 0 else (np.inf if nu > 0 else np.nan)
        return rr if d == "YES" else (1 / rr if rr != 0 else np.inf), (nu, de)


def counts_two(a, y, sub=None):
    m = np.ones(len(a), bool) if sub is None else sub
    yes, no = (a == 1) & m, (a == 0) & m
    return int(y[yes].sum()), int(yes.sum()), int(y[no].sum()), int(no.sum())


y_big = ev.big.to_numpy().astype(float)
y_mon = ev.mon.to_numpy().astype(float)
y_adr = ev.adrt.to_numpy().astype(float)

# permutation keys: one uniform per event per shuffle, events in fixed order (era, E, ticker), shared by all tests
U = np.random.default_rng(SEED).random((NSHUF, N))
P(f"\n## permutation: U = np.random.default_rng({SEED}).random(({NSHUF}, {N})); rows = shuffles, columns = confirm events in order "
  f"(era, E, ticker); within (era, month) the in-test events are sorted by key and the k-th in key order gets the k-th label in fixed order. "
  f"One-sided in the frozen direction: p = (1 + #(perm stat >= obs)) / {NSHUF + 1}.")


def perm_labels(a, y):
    """returns (NSHUF, N) float matrix of permuted labels (only in-test events meaningful)."""
    Y = np.zeros((NSHUF, N), dtype=np.float32)
    groups = defaultdict(list)
    for i in np.where(a >= 0)[0]:
        groups[month_key[i]].append(i)
    for g, idx in groups.items():
        idx = np.array(idx)              # already in fixed order (ev sorted)
        order = np.argsort(U[:, idx], axis=1, kind="mergesort")   # (S, m): k-th in key order
        dest = idx[order]
        Y[np.arange(NSHUF)[:, None], dest] = y[idx][None, :]
    return Y


def perm_stat_thirds(a, Y, d):
    b, t = (a == 0), (a == 2)
    wb, wt = Y[:, b].sum(1), Y[:, t].sum(1)
    rb, rt = (wb + 0.5) / (b.sum() + 1), (wt + 0.5) / (t.sum() + 1)
    return np.log(rt / rb) if d == "HIGH" else np.log(rb / rt)


def perm_stat_two(a, Y, d):
    num_ = np.zeros(NSHUF)
    den = np.zeros(NSHUF)
    groups = defaultdict(list)
    for i in np.where(a >= 0)[0]:
        groups[month_key[i]].append(i)
    for g, idx in groups.items():
        idx = np.array(idx)
        yes = a[idx] == 1
        n1, n0, Nn = yes.sum(), (~yes).sum(), len(idx)
        num_ += Y[:, idx[yes]].sum(1) * n0 / Nn
        den += Y[:, idx[~yes]].sum(1) * n1 / Nn
    with np.errstate(divide="ignore", invalid="ignore"):
        lr = np.log(num_) - np.log(den)
    lr = np.where(np.isnan(lr), 0.0, lr)
    return lr if d == "YES" else -lr


def boot(a, y, d, kind):
    rng = np.random.default_rng(SEED)
    blocks = sorted(set(month_key[a >= 0]))
    bidx = {g: np.where((month_key == g) & (a >= 0))[0] for g in blocks}
    vals = []
    for _ in range(NBOOT):
        pick = rng.integers(0, len(blocks), len(blocks))
        if kind == "thirds":
            wb = nb = wt = nt = 0.0
            for p_ in pick:
                ii = bidx[blocks[p_]]
                aa = a[ii]
                wb += y[ii][aa == 0].sum(); nb += (aa == 0).sum()
                wt += y[ii][aa == 2].sum(); nt += (aa == 2).sum()
            rb, rt = (wb + 0.5) / (nb + 1), (wt + 0.5) / (nt + 1)
            vals.append(rt / rb if d == "HIGH" else rb / rt)
        else:
            nu = de = 0.0
            for p_ in pick:
                ii = bidx[blocks[p_]]
                yes = a[ii] == 1
                n1, n0, Nn = yes.sum(), (~yes).sum(), len(ii)
                nu += y[ii][yes].sum() * n0 / Nn
                de += y[ii][~yes].sum() * n1 / Nn
            rr = nu / de if de > 0 else np.inf
            vals.append(rr if d == "YES" else (1 / rr if rr > 0 else np.inf))
    return np.percentile(np.array(vals), [5, 95])


# ADR-neutral strata: (era, quarter, ADR20 third of that era-quarter over all confirm events with ADR20)
adr_third = assign_thirds(ev.B2.to_numpy(), quarter_key, min_n=1)
adr_strata = np.array([f"{q}|{t}" for q, t in zip(quarter_key, adr_third)])


def adr_neutral(name, col, kind, d):
    x = ev[col].to_numpy().copy()
    x[adr_third < 0] = np.nan
    if kind == "thirds":
        a = assign_thirds(x, adr_strata, min_n=9)
        return oriented_thirds(a, y_big, d)[0]
    a = assign_two(x, adr_strata, min_n=9)
    return oriented_two(a, y_big, d, adr_strata)[0]


res = []
for name, lab, col, kind, d in TESTS:
    a = ASG[name]
    if kind == "thirds":
        r_s, cnts = oriented_thirds(a, y_big, d)
        r_raw, _ = oriented_thirds(a, y_big, d, smooth=False)
        obs = np.log(r_s)
        Y = perm_labels(a, y_big)
        ps = perm_stat_thirds(a, Y, d)
        per = {e: oriented_thirds(a, y_big, d, sub=(era == e))[0] for e in "AB"}
        per_raw = {e: oriented_thirds(a, y_big, d, sub=(era == e), smooth=False)[0] for e in "AB"}
        per_c = {e: oriented_thirds(a, y_big, d, sub=(era == e))[1] for e in "AB"}
        mon = oriented_thirds(a, y_mon, d, smooth=False)[0]
        adt = oriented_thirds(a, y_adr, d, smooth=False)[0]
        wb, nb, wt, nt = cnts
        mid = (a == 1)
        desc = (f"bottom {wb}/{nb} = {wb / nb:.3f} | middle {int(y_big[mid].sum())}/{int(mid.sum())} = {y_big[mid].mean():.3f} | "
                f"top {wt}/{nt} = {wt / nt:.3f}")
        percnt = {e: f"bottom {per_c[e][0]}/{per_c[e][1]} top {per_c[e][2]}/{per_c[e][3]}" for e in "AB"}
    else:
        r_s, (nu, de) = oriented_two(a, y_big, d, month_key)
        if nu == 0 or de == 0:
            P(f"STOP: zero MH numerator/denominator on pooled {name}")
            sys.exit(4)
        r_raw = r_s
        obs = np.log(r_s)
        Y = perm_labels(a, y_big)
        ps = perm_stat_two(a, Y, d)
        per = {e: oriented_two(a, y_big, d, month_key, sub=(era == e))[0] for e in "AB"}
        per_raw = per
        mon = oriented_two(a, y_mon, d, month_key)[0]
        adt = oriented_two(a, y_adr, d, month_key)[0]
        wy, ny, wn, nn = counts_two(a, y_big)
        desc = f"yes {wy}/{ny} = {wy / ny:.3f} | no {wn}/{nn} = {wn / nn:.3f} | pooled (unstratified) {'no/yes' if d == 'NO' else 'yes/no'} " \
               f"{((wn / nn) / (wy / ny) if d == 'NO' else (wy / ny) / (wn / nn)):.3f}"
        percnt = {}
        for e in "AB":
            q = counts_two(a, y_big, sub=(era == e))
            percnt[e] = f"yes {q[0]}/{q[1]} no {q[2]}/{q[3]}"
    cnt = int((ps >= obs - 1e-12).sum())
    p = (1 + cnt) / (NSHUF + 1)
    lo, hi = boot(a, y_big, d, kind)
    adrn = None if name == "H4" else adr_neutral(name, col, kind, d)
    res.append(dict(name=name, lab=lab, kind=kind, d=d, r=r_s, r_raw=r_raw, p=p, cnt=cnt, per=per, per_raw=per_raw, percnt=percnt,
                    lo=lo, hi=hi, mon=mon, adt=adt, adrn=adrn, desc=desc, n=int((a >= 0).sum())))

# Holm over the 9
m_ = len(res)
order = np.argsort([x["p"] for x in res], kind="mergesort")
running = 0.0
for rank, i in enumerate(order):
    adj = min(1.0, (m_ - rank) * res[i]["p"])
    running = max(running, adj)
    res[i]["holm"] = running


def verdict(x, r):
    if r < 1.0:
        return "REVERSED"
    if r < 1.2:
        return "NOT CONFIRMED"
    if x["holm"] > 0.05:
        return "DIRECTIONAL, NOT PROVEN"
    same = all(x["per"][e] > 1.0 for e in "AB")
    return "PICKS THE TAIL" if same else "PICKS THE TAIL (one era only)"


P(f"\n## CONFIRM — {m_} tests, one Holm family (§11.2), one-sided in the frozen direction, {NSHUF:,} within-(era, month) shuffles each")
for x in res:
    x["verdict"] = verdict(x, x["r"])
    x["verdict_raw"] = verdict(x, x["r_raw"])
    tags = []
    if x["name"] != "H4" and ((x["adrn"] is not None and x["adrn"] < 1.2) or x["adt"] < 1.10):
        tags.append("— a volatility proxy (description only, §11.3)")
    dirw = {"LOW": "LOW third wins", "HIGH": "HIGH third wins", "NO": "NO wins (rate no / rate yes, MH)", "YES": "YES wins (rate yes / rate no, MH)"}[x["d"]]
    P(f"\n{x['name']} — {x['lab']} | {dirw} | n in test {x['n']}")
    P(f"   big winner: {x['desc']}")
    P(f"   ratio (frozen direction) {x['r']:.3f}" + (f" (smoothed; raw {x['r_raw']:.3f})" if x["kind"] == "thirds" else " (Mantel-Haenszel by (era, month))")
      + f" | 90% block-bootstrap {x['lo']:.2f}-{x['hi']:.2f} ({NBOOT} draws)")
    P(f"   one-sided p {x['p']:.4f} ({x['cnt']} of {NSHUF:,} shuffles >= observed) | Holm-adjusted p (family of 9) {x['holm']:.4f}")
    P(f"   per era: A {x['per']['A']:.3f} [{x['percnt']['A']}] | B {x['per']['B']:.3f} [{x['percnt']['B']}]"
      + (f" | raw A {x['per_raw']['A']:.3f} B {x['per_raw']['B']:.3f}" if x["kind"] == "thirds" else ""))
    P(f"   monster ratio {x['mon']:.2f} | ADR-scaled tail ratio {x['adt']:.2f} | ADR-neutral {'n/a' if x['adrn'] is None else format(x['adrn'], '.3f')}")
    P(f"   VERDICT: {x['verdict']}" + ("" if x["verdict"] == x["verdict_raw"] else f"  [raw ratio would read {x['verdict_raw']} — FLAG]")
      + (" " + " ".join(tags) if tags else ""))

P("\n## SUMMARY (ratio in frozen direction; thirds = smoothed rates, raw in brackets; H1-H3 = MH)")
P(f"{'test':6s} {'dir':5s} {'ratio':>14s} {'90% int':>11s} {'p (1-sided)':>11s} {'Holm p':>7s} {'era A':>7s} {'era B':>7s} {'monster':>7s} {'ADRtail':>7s} {'ADRneut':>7s}  verdict")
for x in res:
    rr = f"{x['r']:.3f}" + (f" [{x['r_raw']:.3f}]" if x["kind"] == "thirds" else "")
    an = "n/a" if x["adrn"] is None else f"{x['adrn']:.3f}"
    P(f"{x['name']:6s} {x['d']:5s} {rr:>14s} {x['lo']:5.2f}-{x['hi']:<5.2f} {x['p']:11.4f} {x['holm']:7.4f} {x['per']['A']:7.3f} {x['per']['B']:7.3f} "
      f"{x['mon']:7.2f} {x['adt']:7.2f} {an:>7s}  {x['verdict']}")
P("tags: no shelf-relative among the 9 (shelf relatives are f05, f07); 'era-B population thinned…' not applied (§10: D2 0 excluded days).")
(HERE / "recount_confirm.txt").write_text("\n".join(OUT) + "\n")
