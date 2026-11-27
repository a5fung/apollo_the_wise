#!/usr/bin/env python3
"""STAGE 3a - DISCOVERY OUTCOMES, captured ONCE (prereg 2, 6 step 3; amendments A1, A2 in force).

FORWARD READ IS LIMITED TO DISCOVERY. Bars are stream-read from the era-A file only; a row is KEPT at parse only when its ticker
holds a discovery event (seed 1124 or 2411, E <= 2020-12-31) AND its date <= the session ci(2020-12-31)+90; every other row is
discarded unparsed (never stored). The main (+60) outcomes read a copy cut at ci(2020-12-31)+60 (asserted); the +90 rows are read
only by the pre-stated "window length +50%, discovery only" extra reading (5.5), in a separate pass. No era-B file, no check event
(E >= 2021-01-01), no Qullamaggie-only row, no row after 2024-12-31 is touched. Refuses to overwrite its output.

READINGS FIXED HERE, BEFORE ANY OUTCOME IS COMPUTED
 O1 window = bars whose era-A calendar index is in [ci(E), ci(E)+60] (calendar sessions; missing bars = fewer bars, not a longer window).
 O2 truncation (prereg 2): the window keeps only bars dated BEFORE the first of (i) a guard break date (pre_v2 symbol_guard.tsv, the
    file the list chain reads) in E+1..E+W, (ii) a bar in E+1..E+W where raw/adjusted close factor steps (|F/F_prev - 1| > 0.005 =
    the replay's BRIDGE_TOL, as stage 1e counted them) AND the adjusted close-to-close move from the name's previous bar is >= +70%
    or <= -50%. A factor step on E itself is not in the rule (E+1..E+60 as written); counted and printed.
 O3 proxy = max(level(D), open(E)); big winner = max close of the window >= 1.5 x proxy (E's close counts); monster >= 2.0 x;
    failed = max close < 1.10 x proxy; ADR-scaled tail = max close >= proxy x (1 + 8 x ADR20), ADR20 the gate's FRACTION (0.05 = 5%).
 O4 clean winner = big winner with no session low under low(E) on the bars after E up to AND INCLUDING the first +50% close bar.
 O5 extra outcomes (5.5): un-truncated window; proxy max(level, high(E)) on the truncated window; E+1..E+60 (E's close excluded,
    same proxy; no bar after E -> not a winner); window 30 and 90 sessions (same truncation rule over E+1..E+W).
 O6 'full window' = not truncated and all 61 calendar sessions present.
"""
import gzip, hashlib, json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stage2"))
import s2lib as L                                                 # outcome-free: shas, table loader

A2 = L.REPO / "docs/analysis/breakout_winner_study_prereg_amendment_A2_2026-11-26.md"
A2_SHA = "0a6cc4174ef27d187e49100e966023340f7eb0e31cc2d552f4c5ea594f622f6b"
DATA = Path("/Users/alvinfung/apollo_data")
PRE = DATA / "cb702_pre_v2"
DISC_LAST = "2020-12-31"
OUT = HERE / "discovery_outcomes.tsv.gz"
TOL = 0.005
BIG, MON, FAIL, ADRK = 1.5, 2.0, 1.10, 8.0
LOG = []


def P(s=""):
    print(s, flush=True); LOG.append(s)


t0 = time.time()
assert not OUT.exists(), "captured once - discovery_outcomes.tsv.gz exists; read the file"
L.assert_docs()
assert L.sha(A2) == A2_SHA, "A2 sha256 differs - STOP"
P("# STAGE 3a - discovery outcomes (captured once)")
P(f"prereg {L.PREREG_SHA[:8]} / A1 {L.A1_SHA[:8]} / A2 {A2_SHA[:8]} / feature table {L.TABLE_SHA[:8]} asserted")

# ------------------------------------------------------------------ events: DISCOVERY kept (1124 or 2411) only
T = L.load()
T = T[(T.set == "DISC") & ((T.kept == True) | (T.kept2411 == True))].reset_index(drop=True)      # noqa: E712  CHECK rows and Qullamaggie-only rows dropped at load
assert (T.era == "A").all() and T.E.max() <= DISC_LAST and len(T) == 5330 + 5314 - 676, len(T)
EV = pd.read_parquet(DATA / "cb702/bws1124_events_postdrop.parquet", columns=["era", "ci", "ticker", "level", "adr20", "close", "oE", "hE", "lE", "E", "D", "last_ci"])
EV = EV[(EV.era == "A") & (EV.E <= DISC_LAST)]
X = T[["era", "ci", "D", "E", "ticker", "kept", "kept2411", "Ey", "month"]].merge(EV, on=["era", "ci", "ticker", "D", "E"], how="left", validate="1:1")
assert X.level.notna().all() and len(X) == len(T)
N = len(X)
cal = [l.strip() for l in open(DATA / "cb702/bws1124_eraA_list_ctx.cal.txt")]
cix = {d: i for i, d in enumerate(cal)}
iL = cix[DISC_LAST]; CI60, CI90 = iL + 60, iL + 90
assert CI90 < len(cal)
assert all(cal[c] == d and cal[c + 1] == e for c, d, e in zip(X.ci, X.D, X.E)), "calendar index does not match D / E"
need = set(X.ticker)
P(f"events: {N} discovery rows (seed 1124 {int((X.kept == True).sum())}, seed 2411 {int((X.kept2411 == True).sum())}, both {int(((X.kept == True) & (X.kept2411 == True)).sum())}); max E {X.E.max()} (ASSERT <= {DISC_LAST}); tickers {len(need)}")   # noqa: E712
P(f"cuts: main ci({DISC_LAST})+60 = {cal[CI60]} ; +90 pass = {cal[CI90]}")

# ------------------------------------------------------------------ stream-read: only discovery tickers, only dates <= the +90 cut
cut90 = cal[CI90]
rows = {t: [] for t in need}
qqq = {}                                                           # QQQ closes dated <= 2020-12-31 only (5.5: QQQ vs its 50-day AT D; no forward read)
n_seen = n_kept = 0
with gzip.open(PRE / "daily_closes_all.csv.gz", "rt") as fh:
    for ln in fh:
        n_seen += 1
        t, rest = ln.split(",", 1)
        if t == "QQQ" and rest[:10] <= DISC_LAST:
            qqq[rest[:10]] = float(rest.split(",")[4])
        if t not in need:
            continue
        if rest[:10] > cut90:
            continue                                               # a row after the cut is never stored
        rows[t].append(rest)
        n_kept += 1
raw = {t: {} for t in need}
with gzip.open(PRE / "daily_raw_close.csv.gz", "rt") as fh:
    for ln in fh:
        t, d, c = ln.rstrip("\n").split(",")
        if t in need and d <= cut90:
            raw[t][d] = float(c)
bars = {}
last_date_full = {}
for t, rs in rows.items():
    a = [r.rstrip("\n").split(",") for r in rs]
    d = [r[0] for r in a]
    assert d == sorted(d) and len(set(d)) == len(d)
    ci = np.array([cix[x] for x in d], dtype=np.int64)
    o, h, l, c = (np.array([float(r[k]) for r in a]) for k in (1, 2, 3, 4))
    rc = np.array([raw[t].get(x, np.nan) for x in d])
    bars[t] = (d, ci, o, h, l, c, rc / c)
del rows, raw
mx = max(b[0][-1] for b in bars.values())
assert mx <= cut90
P(f"bar file: {n_seen:,} rows streamed, {n_kept:,} kept (discovery tickers, date <= {cut90}); latest bar held {mx}")
guard = {}
gl = (PRE / "symbol_guard.tsv").read_text().splitlines()
hd = gl[0].split("\t"); ks, kb = hd.index("symbol"), hd.index("breaks")
for ln in gl[1:]:
    f = ln.split("\t")
    if len(f) > kb and f[kb] and f[ks] in need:
        guard[f[ks]] = sorted(x.split(":")[0] for x in f[kb].split(";"))


def view(t, cimax):
    d, ci, o, h, l, c, F = bars[t]
    k = int(np.searchsorted(ci, cimax, side="right"))
    return d[:k], ci[:k], o[:k], h[:k], l[:k], c[:k], F[:k]


def window(t, iE, W, cimax, truncate=True):
    """(i, j, cut reason): bar positions [i, j) of the window E..E+W; reads only the view cut at cimax."""
    d, ci, o, h, l, c, F = view(t, cimax)
    assert iE + W <= cimax
    i = int(np.searchsorted(ci, iE)); assert ci[i] == iE
    j = int(np.searchsorted(ci, iE + W, side="right"))
    reason = ""
    if truncate:
        lo, hi = cal[iE + 1], cal[iE + W]
        for g in guard.get(t, ()):
            if lo <= g <= hi:
                jj = next((p for p in range(i, j) if d[p] >= g), j)       # first bar dated on or after the break
                if jj < j:
                    j, reason = jj, "guard"
                break
        for p in range(i + 1, j):
            if np.isfinite(F[p]) and np.isfinite(F[p - 1]) and abs(F[p] / F[p - 1] - 1) > TOL:
                mv = c[p] / c[p - 1] - 1
                if mv >= 0.70 or mv <= -0.50:
                    j, reason = p, (reason + "+split" if reason else "split")
                    break
    return i, j, reason


res = []
n_stepE = 0
for r in X.itertuples(index=False):
    assert r.E <= DISC_LAST and r.era == "A"                      # CHECK OUTCOMES ARE NEVER READ
    iE = int(r.ci) + 1
    d, ci, o, h, l, c, F = view(r.ticker, CI60)
    i, j, reason = window(r.ticker, iE, 60, CI60)
    assert d[i] == r.E and iE + 60 <= CI60
    for a_, b_ in ((o[i], r.oE), (h[i], r.hE), (l[i], r.lE)):
        assert abs(a_ - b_) <= 1e-9 * max(1.0, abs(b_)), (r.ticker, r.E, a_, b_)
    assert i > 0 and ci[i - 1] == iE - 1 and abs(c[i - 1] - r.close) <= 1e-9 * max(1.0, r.close)
    if np.isfinite(F[i]) and np.isfinite(F[i - 1]) and abs(F[i] / F[i - 1] - 1) > TOL:
        n_stepE += 1
    proxy = max(float(r.level), float(r.oE))
    w = c[i:j]
    mxc = float(w.max())
    big = mxc >= BIG * proxy
    q = int(np.argmax(w >= BIG * proxy)) if big else -1
    clean = bool(big and (q == 0 or (l[i + 1:i + q + 1] >= r.lE).all()))
    iu, ju, _ = window(r.ticker, iE, 60, CI60, truncate=False)
    mxu = float(c[iu:ju].max())
    e1 = float(w[1:].max()) if len(w) > 1 else np.nan
    i3, j3, _ = window(r.ticker, iE, 30, CI60)
    mx30 = float(c[i3:j3].max())
    last_ci_held = int(bars[r.ticker][1][-1])                      # last bar HELD here (cut at +90)
    assert last_ci_held == min(int(r.last_ci), last_ci_held) and (last_ci_held == int(r.last_ci) or int(r.last_ci) > last_ci_held)
    hole_past_cut = int(last_ci_held < iE + 60 <= int(r.last_ci))  # bars stop inside the window and resume only after the +90 cut (a hole)
    res.append(dict(maxc=mxc / proxy, big=int(big), monster=int(mxc >= MON * proxy), failed=int(mxc < FAIL * proxy),
                    adr_tail=int(mxc >= proxy * (1 + ADRK * float(r.adr20))), clean=int(clean), first_hit=q,
                    big_untrunc=int(mxu >= BIG * proxy), maxc_untrunc=mxu / proxy,
                    big_fromhigh=int(mxc >= BIG * max(float(r.level), float(r.hE))),
                    big_e1=int(np.isfinite(e1) and e1 >= BIG * proxy), big_w30=int(mx30 >= BIG * proxy),
                    nbars=j - i, nbars_untrunc=ju - iu, truncated=reason, ends_inside=int(int(r.last_ci) < iE + 60), hole_past_cut=hole_past_cut,
                    full_window=int(reason == "" and (j - i) == 61), proxy=proxy))
O = pd.concat([X[["era", "ci", "D", "E", "ticker", "kept", "kept2411", "Ey", "month"]], pd.DataFrame(res)], axis=1)
# ---- separate +90 pass (5.5 window +50%, discovery only)
w90 = []
for r in X.itertuples(index=False):
    assert r.E <= DISC_LAST
    iE = int(r.ci) + 1
    d, ci, o, h, l, c, F = view(r.ticker, CI90)
    i9, j9, _ = window(r.ticker, iE, 90, CI90)
    w90.append(int(float(c[i9:j9].max()) >= BIG * max(float(r.level), float(r.oE))))
O["big_w90"] = w90
qd = sorted(qqq); qc = np.array([qqq[x] for x in qd]); qpos = {x: k for k, x in enumerate(qd)}
assert qd[-1] <= DISC_LAST and all(x in qpos for x in X.D)
O["qqq_above50"] = [int(qc[qpos[x]] > qc[qpos[x] - 49:qpos[x] + 1].mean()) for x in X.D]      # close(D) > SMA50(D), bars <= D
assert len(O) == N and (O.E <= DISC_LAST).all()

# ------------------------------------------------------------------ cross-checks vs stage 1e (outcome-free facts)
K = O[O.kept == True]                                              # noqa: E712
ends = K[K.ends_inside == 1].groupby("Ey").size().reindex([2017, 2018, 2019, 2020], fill_value=0).tolist()
trunc = K[K.truncated != ""].groupby("Ey").size().reindex([2017, 2018, 2019, 2020], fill_value=0).tolist()
P(f"cross-check 1 (stage 1e: kept events whose bars end inside E..E+60, 2017-20 = 5 / 9 / 5 / 21): here {ends}")
P(f"cross-check 2 (stage 1e: kept events with a guard / factor-step / flag date in the window = 3 / 1 / 3 / 7 - an upper bound): truncated here {trunc} ; by reason {K[K.truncated != ''].truncated.value_counts().to_dict()}")
P(f"cross-check 3: open / high / low of E and close of D from the stream equal the stage-1 event rows on all {N} events (asserted per event)")
P(f"factor step on E itself (not in the truncation rule, counted): {n_stepE}")
S1E = pd.read_csv(HERE.parent / "stage1de/events_kept_seed1124.tsv", sep="\t", usecols=["era", "ci", "ticker", "ends_in", "w_guard"], dtype={"ticker": str}, keep_default_na=False)
S1E = S1E[S1E.era == "A"]
J = K.merge(S1E, on=["ci", "ticker"], how="left", validate="1:1")
assert J.ends_in.notna().all()
ok1 = ends == [5, 9, 5, 21] and (J.ends_in.astype(str).eq("True") == (J.ends_inside == 1)).all()   # ends_inside = stage 1's last bar date (a date fact), per event
ok2 = ((J.truncated.str.contains("guard")) == J.w_guard.astype(str).eq("True")).all() and all(a <= b for a, b in zip(trunc, [3, 1, 3, 7]))
P(f"   per event: ends-inside equals stage 1e's column on all {len(J)} kept events: {ok1}; guard-truncated equals stage 1e's guard-in-window column: {ok2}")
P(f"   events whose bars stop inside the window and resume only after the +90 cut (a hole; window read as held, counted): {int(O.hole_past_cut.sum())} (seed 1124: {int(K.hole_past_cut.sum())})")
assert ok1 and ok2, "cross-check against stage 1e failed - STOP (window / alignment bug)"
O.to_csv(OUT, sep="\t", index=False, float_format="%.10g", compression={"method": "gzip", "mtime": 0})
P(f"wrote {OUT.name}: {N} rows (discovery only), sha256 {L.sha(OUT)}")
P(f"window facts (seed 1124, n {len(K)}): truncated {int((K.truncated != '').sum())}; fewer than 61 bars {int((K.nbars < 61).sum())}; full windows {int(K.full_window.sum())}")
P(f"this script sha256 {L.sha(__file__)[:16]} | {time.time() - t0:.0f}s")
(HERE / "3a_outcomes.txt").write_text("\n".join(LOG) + "\n")
