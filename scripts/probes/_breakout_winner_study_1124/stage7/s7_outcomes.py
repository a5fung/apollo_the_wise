#!/usr/bin/env python3
"""STAGE 7a - CHECK OUTCOMES, captured ONCE (prereg 2, 6 step 7; A1, A2, A3; stage-6 freeze). Refuses to overwrite its output.

POPULATION: feature-table rows set == CHECK and kept (seed 1124): 6,266 events, E 2021-01-04 .. 2024-10-04 (era A 2,910, era B 3,356).
SEAL: no row dated after 2024-12-31 is opened. Era B reads ONLY the sealed copy of the cb702 export (rows < 2025-01-01, written by the
replay's sealed_copy_of_daily; its .src.json asserted) - the cb702 export itself and the Alpaca raw pull (A1: discarded) are never
opened. Era-B guard and split-list rows are filtered on their date column at parse (> 2024-12-31 dropped, counted). Every bar row is
kept at parse only when its ticker holds a check event of its era AND its date lies in [the era's first D, the era's last ci(E)+60];
the last window end of each era is asserted <= 2024-12-31.

READINGS FIXED HERE (same as stage 3's s3_outcomes.py, O1-O6, unless stated)
 O1 window = bars whose era calendar index is in [ci(E), ci(E)+60] (calendar sessions; bws1124_eraA/B_list_ctx.cal.txt).
 O2 truncation: bars dated BEFORE the first of (i) a guard break date in E+1..E+60 (era A: pre_v2 symbol_guard.tsv, the file the era-A
    store reads; era B: symbol_guard_B.tsv, the file stage 1e read), (ii) era A: a bar in E+1..E+60 where the raw/adjusted factor steps
    (|F/F_prev - 1| > 0.005) AND the adjusted close-to-close move is >= +70% or <= -50%; era B (no per-bar raw close): a bar in
    E+1..E+60 dated on a split-list row (cb702_splits.psv rows < 2025-01-01, every row, the dates stage 1e's win_dates used) AND the
    same move. Cross-check vs stage 1e (fixed before the run): guard-truncated must be a SUBSET of stage 1e's w_guard (a guard date with
    no bar on/after it inside the window truncates nothing; the difference is printed); split-truncated a subset of w_split.
 O3/O4/O5 as stage 3 (proxy max(level, open(E)); big 1.5x, monster 2.0x, failed < 1.10x, ADR-scaled 1 + 8 x ADR20; clean; un-truncated;
    from max(level, high(E)); E+1..E+60). No 30 / 90 window (5.5: discovery only).
 O6 full window = not truncated and all 61 calendar sessions present. ends_inside = the ticker's last bar in the era store < ci(E)+60.
 O7 QQQ above its 50-day at D: close(D) > mean of the last 50 QQQ closes <= D, from the same era's bar file (rows <= the era's last D).
Prints no outcome rate (the stats run reads the file).
"""
import gzip, hashlib, json, sys, time
from bisect import bisect_left
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = HERE.parents[3]
sys.path.insert(0, str(ROOT / "stage2"))
import s2lib as L                                     # noqa: E402

DOCS = {"docs/analysis/breakout_winner_study_prereg_amendment_A2_2026-11-26.md": "0a6cc4174ef27d187e49100e966023340f7eb0e31cc2d552f4c5ea594f622f6b",
        "docs/analysis/breakout_winner_study_prereg_amendment_A3_2026-11-26.md": "a0c11a3685bc83369a9fba29766368e82734432ea9a3a464fd363787e6d34268",
        "docs/analysis/breakout_winner_study_stage6_freeze_2026-11-26.md": "28e40825e0729aaab48e96bcb677db697cb9527f895257b6c425368eb4e4bd18"}
DATA = Path("/Users/alvinfung/apollo_data")
PRE = DATA / "cb702_pre_v2"
SEALED = Path("/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/bws1124/pop/cb702_daily_lt2025.csv.gz")
CUT = "2024-12-31"
OUT = HERE / "check_outcomes.tsv.gz"
TOL = 0.005
BIG, MON, FAIL, ADRK = 1.5, 2.0, 1.10, 8.0
COLS = ["era", "ci", "D", "E", "ticker", "kept", "kept2411", "Ey", "month", "maxc", "big", "monster", "failed", "adr_tail", "clean", "first_hit",
        "big_untrunc", "maxc_untrunc", "big_fromhigh", "big_e1", "nbars", "nbars_untrunc", "truncated", "ends_inside", "full_window", "proxy", "qqq_above50"]
LOG = []


def P(s=""):
    print(s, flush=True); LOG.append(s)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


t0 = time.time()
assert not OUT.exists(), "captured once - check_outcomes.tsv.gz exists; read the file"
L.assert_docs()
for p, h in DOCS.items():
    assert sha(REPO / p) == h, f"{p} sha256 differs - STOP"
src = json.loads(Path(str(SEALED) + ".src.json").read_text())
assert src["seal"] == "2025-01-01" and src["source"].endswith("cb702/daily_closes_all.csv.gz"), src
P("# STAGE 7a - check outcomes (captured once)")
P(f"prereg / A1 / A2 / A3 / stage-6 freeze / feature table asserted; era-B bars = the sealed copy (seal {src['seal']}, {src['kept']:,} rows kept, source sha {src['source_sha256'][:12]})")

# ------------------------------------------------------------------ events
T = L.load()
T = T[(T.set == "CHECK") & (T.kept == True)].reset_index(drop=True)          # noqa: E712  discovery rows dropped at load
assert len(T) == 6266 and T.E.min() >= "2021-01-01" and T.E.max() <= CUT
EV = pd.read_parquet(DATA / "cb702/bws1124_events_postdrop.parquet", columns=["era", "ci", "ticker", "level", "adr20", "close", "oE", "hE", "lE", "E", "D", "last_ci"])
EV = EV[EV.E >= "2021-01-01"]
X = T[["era", "ci", "D", "E", "ticker", "kept", "kept2411", "Ey", "month"]].merge(EV, on=["era", "ci", "ticker", "D", "E"], how="left", validate="1:1")
assert X.level.notna().all() and len(X) == len(T)
N = len(X)
CAL, CIX, CUTCI, LOCI = {}, {}, {}, {}
for e, fn in (("A", "bws1124_eraA_list_ctx.cal.txt"), ("B", "bws1124_eraB_list_ctx.cal.txt")):
    cal = [l.strip() for l in open(DATA / "cb702" / fn)]
    assert cal == sorted(cal) and cal[-1] <= CUT
    CAL[e] = cal; CIX[e] = {d: i for i, d in enumerate(cal)}
    x = X[X.era == e]
    assert all(cal[c] == d and cal[c + 1] == ee for c, d, ee in zip(x.ci, x.D, x.E)), f"calendar index does not match D / E, era {e}"
    CUTCI[e] = int(x.ci.max()) + 1 + 60; LOCI[e] = max(int(x.ci.min()) - 60, 0)          # 60 bars of lead-in for QQQ's 50-day
    assert CUTCI[e] < len(cal) and cal[CUTCI[e]] <= CUT, (e, CUTCI[e])
    P(f"era {e}: {len(x)} events, E {x.E.min()}..{x.E.max()}; bars read {cal[LOCI[e]]}..{cal[CUTCI[e]]} (last window end, ASSERT <= {CUT})")
need = {e: set(X.ticker[X.era == e]) for e in ("A", "B")}


def read_bars(e, path):
    lo, hi = CAL[e][LOCI[e]], CAL[e][CUTCI[e]]
    rows = {t: [] for t in need[e] | {"QQQ"}}
    n_seen = n_kept = 0
    with gzip.open(path, "rt") as fh:
        for ln in fh:
            n_seen += 1
            t, rest = ln.split(",", 1)
            if t not in rows:
                continue
            d = rest[:10]
            if d < lo or d > hi:
                continue                                              # never stored
            assert d <= CUT, "a row after the seal - STOP"
            rows[t].append(rest)
            n_kept += 1
    P(f"era {e} bar file {path.name}: {n_seen:,} rows streamed, {n_kept:,} kept ({len(need[e])} tickers + QQQ, {lo}..{hi})")
    return rows


def arrays(e, rs, raw=None):
    a = sorted((r.rstrip("\n").split(",") for r in rs), key=lambda r: r[0])
    d = [r[0] for r in a]
    assert len(set(d)) == len(d)
    ci = np.array([CIX[e][x] for x in d], dtype=np.int64)
    o, h, l, c = (np.array([float(r[k]) for r in a]) for k in (1, 2, 3, 4))
    F = np.array([raw.get(x, np.nan) for x in d]) / c if raw is not None else np.full(len(d), np.nan)
    return d, ci, o, h, l, c, F


rowsA = read_bars("A", PRE / "daily_closes_all.csv.gz")
rawA = {t: {} for t in need["A"]}
loA, hiA = CAL["A"][LOCI["A"]], CAL["A"][CUTCI["A"]]
with gzip.open(PRE / "daily_raw_close.csv.gz", "rt") as fh:
    for ln in fh:
        t, d, c = ln.rstrip("\n").split(",")
        if t in rawA and loA <= d <= hiA:
            rawA[t][d] = float(c)
rowsB = read_bars("B", SEALED)
BARS = {"A": {t: arrays("A", rowsA[t], rawA[t]) for t in need["A"]}, "B": {t: arrays("B", rowsB[t]) for t in need["B"]}}
QQQ = {"A": arrays("A", rowsA["QQQ"]), "B": arrays("B", rowsB["QQQ"])}
del rowsA, rowsB, rawA
for e in ("A", "B"):
    mx = max(b[0][-1] for b in BARS[e].values())
    assert mx <= CAL[e][CUTCI[e]] <= CUT
    P(f"era {e}: latest bar held {mx} (ASSERT <= {CUT})")

# guard / split dates (date column filtered at parse)
GUARD = {"A": {}, "B": {}}
ndrop = {"A": 0, "B": 0}
for e, path in (("A", PRE / "symbol_guard.tsv"), ("B", REPO / "scripts/backtest_data_audit/runs_2026-10-23/universe/symbol_guard_B.tsv")):
    gl = path.read_text().splitlines()
    hd = gl[0].split("\t"); ks, kb = hd.index("symbol"), hd.index("breaks")
    for ln in gl[1:]:
        f = ln.split("\t")
        if len(f) > kb and f[kb] and f[ks] in need[e]:
            ds = [x.split(":")[0] for x in f[kb].split(";")]
            keep = sorted(x for x in ds if x <= CUT); ndrop[e] += len(ds) - len(keep)
            if keep:
                GUARD[e][f[ks]] = keep
SPLIT = {}
nsd = 0
for ln in (DATA / "cb702/cb702_splits.psv").read_text().splitlines():
    f = ln.split("|")
    if len(f) < 4:
        continue
    if f[1] > CUT:
        nsd += 1; continue
    if f[0] in need["B"]:
        SPLIT.setdefault(f[0], set()).add(f[1])
assert all(max(v) <= CUT for v in GUARD["B"].values()) and all(max(v) <= CUT for v in SPLIT.values())
P(f"guard dates after {CUT} dropped at parse: era A {ndrop['A']}, era B {ndrop['B']}; split-list rows after {CUT} dropped at parse: {nsd}; era-B tickers with a split date: {len(SPLIT)}")


def window(e, t, iE, W=60, truncate=True):
    d, ci, o, h, l, c, F = BARS[e][t]
    i = int(np.searchsorted(ci, iE)); assert ci[i] == iE
    j = int(np.searchsorted(ci, iE + W, side="right"))
    reason = ""
    if truncate:
        lo, hi = CAL[e][iE + 1], CAL[e][iE + W]
        for g in GUARD[e].get(t, ()):
            if lo <= g <= hi:
                jj = next((p for p in range(i, j) if d[p] >= g), j)
                if jj < j:
                    j, reason = jj, "guard"
                break
        sd = SPLIT.get(t, set()) if e == "B" else None
        for p in range(i + 1, j):
            step = (d[p] in sd) if e == "B" else (np.isfinite(F[p]) and np.isfinite(F[p - 1]) and abs(F[p] / F[p - 1] - 1) > TOL)
            if step:
                mv = c[p] / c[p - 1] - 1
                if mv >= 0.70 or mv <= -0.50:
                    j, reason = p, (reason + "+split" if reason else "split")
                    break
    return i, j, reason


# ------------------------------------------------------------------ windows first (cross-checks before any outcome is computed)
S1E = pd.read_csv(ROOT / "stage1de/events_kept_seed1124.tsv", sep="\t", usecols=["era", "ci", "ticker", "ends_in", "w_guard", "w_split"], dtype={"ticker": str}, keep_default_na=False)
J = X[["era", "ci", "ticker"]].merge(S1E, on=["era", "ci", "ticker"], how="left", validate="1:1")
assert J.ends_in.notna().all() and (J.ends_in != "").all()
WIN = []
for r in X.itertuples(index=False):
    iE = int(r.ci) + 1
    i, j, reason = window(r.era, r.ticker, iE)
    WIN.append((i, j, reason, int(int(r.last_ci) < iE + 60)))
tr = np.array([w[2] for w in WIN]); ends = np.array([w[3] for w in WIN])
for e in ("A", "B"):
    m = (X.era == e).to_numpy()
    eq_end = bool((J.ends_in[m].astype(str).eq("True").to_numpy() == (ends[m] == 1)).all())
    g_tr = np.char.find(tr[m].astype(str), "guard") >= 0; s_tr = np.char.find(tr[m].astype(str), "split") >= 0
    wg = J.w_guard[m].astype(str).eq("True").to_numpy(); ws = J.w_split[m].astype(str).eq("True").to_numpy()
    P(f"cross-check era {e}: ends-inside equals stage 1e on all {int(m.sum())} events: {eq_end} | guard-truncated {int(g_tr.sum())} (subset of stage 1e w_guard {int(wg.sum())}: {bool((~g_tr | wg).all())};"
      f" w_guard not truncated {int((wg & ~g_tr).sum())}) | split-truncated {int(s_tr.sum())} (subset of w_split {int(ws.sum())}: {bool((~s_tr | ws).all())})")
    assert eq_end and (~g_tr | wg).all() and (~s_tr | ws).all(), f"cross-check against stage 1e failed, era {e} - STOP"

# ------------------------------------------------------------------ outcomes
res = []
n_stepE = 0
for r, (i, j, reason, ei) in zip(X.itertuples(index=False), WIN):
    assert r.E >= "2021-01-01" and r.E <= CUT
    iE = int(r.ci) + 1
    d, ci, o, h, l, c, F = BARS[r.era][r.ticker]
    assert d[i] == r.E and d[j - 1] <= CUT
    for a_, b_ in ((o[i], r.oE), (h[i], r.hE), (l[i], r.lE)):
        assert abs(a_ - b_) <= 1e-9 * max(1.0, abs(b_)), (r.era, r.ticker, r.E, a_, b_)
    assert i > 0 and ci[i - 1] == iE - 1 and abs(c[i - 1] - r.close) <= 1e-9 * max(1.0, r.close), (r.era, r.ticker, r.D)
    if r.era == "A" and np.isfinite(F[i]) and np.isfinite(F[i - 1]) and abs(F[i] / F[i - 1] - 1) > TOL:
        n_stepE += 1
    proxy = max(float(r.level), float(r.oE))
    w = c[i:j]
    mxc = float(w.max())
    bg = mxc >= BIG * proxy
    q = int(np.argmax(w >= BIG * proxy)) if bg else -1
    clean = bool(bg and (q == 0 or (l[i + 1:i + q + 1] >= r.lE).all()))
    iu, ju, _ = window(r.era, r.ticker, iE, truncate=False)
    mxu = float(c[iu:ju].max())
    e1 = float(w[1:].max()) if len(w) > 1 else np.nan
    qd, qci, _, _, _, qc, _ = QQQ[r.era]
    k = int(np.searchsorted(qci, int(r.ci))); assert qci[k] == int(r.ci) and k >= 49
    res.append(dict(maxc=mxc / proxy, big=int(bg), monster=int(mxc >= MON * proxy), failed=int(mxc < FAIL * proxy),
                    adr_tail=int(mxc >= proxy * (1 + ADRK * float(r.adr20))), clean=int(clean), first_hit=q,
                    big_untrunc=int(mxu >= BIG * proxy), maxc_untrunc=mxu / proxy,
                    big_fromhigh=int(mxc >= BIG * max(float(r.level), float(r.hE))),
                    big_e1=int(np.isfinite(e1) and e1 >= BIG * proxy),
                    nbars=j - i, nbars_untrunc=ju - iu, truncated=reason, ends_inside=ei,
                    full_window=int(reason == "" and (j - i) == 61), proxy=proxy,
                    qqq_above50=int(qc[k] > qc[k - 49:k + 1].mean())))
O = pd.concat([X[["era", "ci", "D", "E", "ticker", "kept", "kept2411", "Ey", "month"]], pd.DataFrame(res)], axis=1)[COLS]
assert len(O) == N and O.E.max() <= CUT and O.E.min() >= "2021-01-01"
P(f"cross-check: open / high / low of E and close of D from the bar files equal the stage-1 event rows on all {N} events (asserted per event)")
P(f"factor step on E itself, era A (not in the truncation rule, counted): {n_stepE}")
for e in ("A", "B"):
    x = O[O.era == e]
    P(f"window facts era {e} (n {len(x)}): truncated {int((x.truncated != '').sum())} {x[x.truncated != ''].truncated.value_counts().to_dict()}; fewer than 61 bars {int((x.nbars < 61).sum())};"
      f" bars end inside the window {int(x.ends_inside.sum())}; full windows {int(x.full_window.sum())}")
O.to_csv(OUT, sep="\t", index=False, float_format="%.10g", compression={"method": "gzip", "mtime": 0})
P(f"wrote {OUT.name}: {N} rows (check, seed 1124), sha256 {sha(OUT)}")
P(f"this script sha256 {sha(__file__)} | {time.time() - t0:.0f}s")
(HERE / "7a_outcomes.txt").write_text("\n".join(LOG) + "\n")
