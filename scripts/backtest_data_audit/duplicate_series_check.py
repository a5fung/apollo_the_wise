#!/usr/bin/env python3
"""Backtest-data audit, lens DUPLICATE SERIES: one company carried under two symbols (rename / de-SPAC / share class / a copy on a
different price scale) so every event on it is counted twice.  Read-only; stdlib + pandas/numpy.

  python3 scripts/backtest_data_audit/duplicate_series_check.py EXPORT.csv.gz --label eraA --out OUTDIR [--cut 2024-12-31]
         [--assets assets.tsv] [--tol 1e-4] [--min-run 5] [--window 8] [--no-probes]
  python3 scripts/backtest_data_audit/duplicate_series_check.py --selftest

EXPORT = ticker,date,open,high,low,close,volume  (no header).  Rows dated after --cut are DROPPED ON LOAD (default and maximum
2024-12-31: the 2025-26 table is sealed and is never analysed).

Test 1 -- STRICT twin.  Two different symbols on the SAME date with open/high/low/close/volume all equal within --tol (relative; 0 =
  exact).  Exact matches would be found by a full group-by; near matches compare each row with its next --window neighbours after
  sorting each date by (close, volume), so a near-duplicate hidden in a cluster of >window same-close rows can be missed.  Only rows with
  volume > 0 and close > 0 are eligible.  Pair class, from the SHAPE of the data (names are only a hint -- the asset list gives the
  CURRENT holder of a symbol and symbols get reused: INT is World Fuel Services in these bars, 'Corgi INTC 2x Daily ETF' in the list):
    coincidence_short   fewer than --min-run matched days
    coincidence_thin    median matched dollar volume < $1,000, or every matched bar flat (o=h=l=c)
    share_class_or_derivative   ticker B = ticker A + unit/warrant/right/class suffix
    coincidence_sparse  matched on < 5% of the days both symbols have bars (when-issued / spin-off window, not a twin)
    partial_overlap     matched on 5-90% of the days both symbols have bars (a de-SPAC whose merged ticker shares only the SPAC history)
    retired_symbol      exactly one symbol has NO bars after the last matched day while the other carries on = rename/merger
                        successor.  retired = OLD symbol; switch date = last matched day + 1 session
    diverged_after_run  both symbols keep trading after the identical run ends (a symbol was reused by a different instrument)
    both_retired        both stop together
    twin_to_window_end  identical history to the END of the export (rename happens after the window, or two live symbols share one
                        history)
  Confirmed = any class except coincidence_*.
Test 2 -- SCALED twin (probe).  The same company on a different PRICE SCALE: close ratio constant (sd of log ratio < 0.005) and volume
  ratio inverse, so dollar volume is identical.  Found via days with equal 4-decimal returns (|ret| >= 3%, >= 20 days), then every
  overlap day whose close ratio is within 0.5% of the pair's median ratio AND whose dollar volume agrees within 5% is flagged.  Cause: reverse-split factors of one issuer applied to another's bars.
Test 3 -- OHLC-only (probe): equal O/H/L/C on bars with >= 1% intraday range, different volume, >= --min-run days (share-class / feed-difference duplicates).
Excess rows = per date, rows that have a confirmed partner with a SMALLER symbol (k identical series -> k-1 excess rows).
Breakout-scale rows: gap >= 10% (open vs prior close) or return >= 15% (close vs prior close) or return >= 50%, each with close*volume >=
$1M; counted before/after removing the excess rows.
Seam (--vs OTHER): same symbol, same date, two exports -> closes must agree within 1%.
Outputs OUT/<label>_*: pairs.tsv, scaled_twins.tsv, flagged_rows.tsv, per_year.tsv, probe_ohlc_only.tsv, summary.txt (also printed)."""
import argparse, os, re, sys
import numpy as np
import pandas as pd

SEALED_AFTER = "2024-12-31"
COLS = ["t", "d", "o", "h", "l", "c", "v"]
OHLCV = ("o", "h", "l", "c", "v")


# ---------------------------------------------------------------- load
def load(path, cut):
    if cut > SEALED_AFTER:
        sys.exit(f"refusing --cut {cut}: the 2025-26 table is sealed (max {SEALED_AFTER})")
    parts = []
    for ch in pd.read_csv(path, header=None, names=COLS, chunksize=2_000_000,
                          dtype={"t": "string", "d": "string", "o": "float64", "h": "float64", "l": "float64", "c": "float64", "v": "float64"}):
        parts.append(ch[ch.d <= cut])           # sealed rows are discarded the moment they are parsed
    df = pd.concat(parts, ignore_index=True)
    df["t"] = df["t"].astype("category")        # categories are sorted, so code order == symbol order
    return df


class Bars:
    """Per-symbol bar index: session idx, close, volume sorted by (symbol code, session)."""
    def __init__(self, df):
        self.cats = np.array(df.t.cat.categories)
        self.dates = np.sort(df.d.unique())
        didx = pd.Series(np.arange(len(self.dates)), index=self.dates)
        self.tc = df.t.cat.codes.values.astype("int32")
        self.di = df.d.map(didx).values.astype("int32")
        order = np.lexsort((self.di, self.tc))
        self.tc, self.di = self.tc[order], self.di[order]
        self.c, self.v = df.c.values[order], df.v.values[order]
        self.o, self.h, self.l = df.o.values[order], df.h.values[order], df.l.values[order]
        self.bounds = np.searchsorted(self.tc, np.arange(len(self.cats) + 1))

    def sl(self, code):
        return slice(self.bounds[code], self.bounds[code + 1])


# ---------------------------------------------------------------- matching
def _rel_ok(a, b, tol):
    return (a == b) if tol == 0 else (np.abs(a - b) <= tol * np.maximum(np.abs(a), np.abs(b)))


def match_rows(B, tol, window, fields=OHLCV, sortkeys=("c", "v")):
    """Matched row pairs of different symbols on the same session: di, a<b (symbol codes), exact, flat, dv (matched $ volume)."""
    e = pd.DataFrame({"tc": B.tc, "di": B.di, "o": B.o, "h": B.h, "l": B.l, "c": B.c, "v": B.v})
    e = e[(e.v > 0) & (e.c > 0)].sort_values(["di", *sortkeys], kind="stable").reset_index(drop=True)
    di, tc = e.di.values, e.tc.values
    arr = {k: e[k].values for k in OHLCV}
    out = []
    for k in range(1, window + 1):
        if len(e) <= k:
            break
        m = (di[:-k] == di[k:]) & (tc[:-k] != tc[k:])
        for f in fields:
            m &= _rel_ok(arr[f][:-k], arr[f][k:], tol)
        i = np.flatnonzero(m)
        if len(i) == 0:
            continue
        j = i + k
        exact = np.ones(len(i), bool)
        for f in fields:
            exact &= arr[f][i] == arr[f][j]
        flat = (arr["o"][i] == arr["h"][i]) & (arr["h"][i] == arr["l"][i]) & (arr["l"][i] == arr["c"][i])
        out.append(pd.DataFrame({"di": di[i], "a": np.minimum(tc[i], tc[j]), "b": np.maximum(tc[i], tc[j]),
                                 "exact": exact, "flat": flat, "dv": arr["c"][i] * arr["v"][i],
                                 "rng": (arr["h"][i] - arr["l"][i]) / arr["c"][i]}))
    if not out:
        return pd.DataFrame({"di": [], "a": [], "b": [], "exact": [], "flat": [], "dv": [], "rng": []})
    return pd.concat(out, ignore_index=True).drop_duplicates(["di", "a", "b"])


# ---------------------------------------------------------------- hints / classes
STOP = set("""common stock shares share ordinary class a b c d inc incorporated corp corporation ltd limited co company holdings holding
plc sa nv ag adr ads american depositary receipts receipt sponsored new the and of lp llc trust series units unit warrants warrant
rights right each representing one par value de cv ab oyj asa group international intl""".split())
SPAC_RE = re.compile(r"acquisition|merger|spac\b|blank check", re.I)
ETF_RE = re.compile(r"\bETF\b|\bETN\b|exchange.traded|\bfund\b|daily|2x|3x|-1x|yieldboost|buffer", re.I)
DERIV_SUFFIX = {"W", "WS", "WT", "U", "R", "RT", "WW", ".U", ".W", ".WS", ".R", ".A", ".B", ".C", "A", "B", "C", "-A", "-B", "-U", "-W", "-WS"}


def core(name):
    if not isinstance(name, str):
        return None
    return frozenset(t for t in re.sub(r"[^a-z0-9 ]", " ", name.lower()).split() if t not in STOP)


def suffix_relation(ta, tb):
    s, l = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return l.startswith(s) and l != s and l[len(s):].upper() in DERIV_SUFFIX


def name_hint(na, nb):
    if not isinstance(na, str) or not isinstance(nb, str):
        return "name_missing"
    h = []
    if bool(ETF_RE.search(na)) != bool(ETF_RE.search(nb)):
        h.append("etf_vs_company_conflict(symbol reused)")
    if SPAC_RE.search(na) or SPAC_RE.search(nb):
        h.append("spac_wording")
    ca, cb = core(na), core(nb)
    if len(ca | cb) and len(ca & cb) / len(ca | cb) >= 0.5:
        h.append("same_issuer_name")
    return "+".join(h) if h else "names_differ"


def longest_run(idx):
    if len(idx) == 0:
        return 0
    idx = np.sort(idx)
    br = np.flatnonzero(np.diff(idx) != 1)
    starts, ends = np.r_[0, br + 1], np.r_[br, len(idx) - 1]
    return int((ends - starts + 1).max())


# ---------------------------------------------------------------- test 1: strict twins
def strict_pairs(B, tol, min_run, window, names):
    mm = match_rows(B, tol, window)
    if len(mm) == 0:
        return mm, pd.DataFrame(), pd.DataFrame()
    g = mm.groupby(["a", "b"])
    pr = g.agg(n_match=("di", "size"), n_exact=("exact", "sum"), first_di=("di", "min"), last_di=("di", "max"),
               n_flat=("flat", "sum"), med_dv=("dv", "median")).reset_index()
    runs = {k: longest_run(sub.di.values) for k, sub in g if len(sub) >= min_run}
    pr["longest_run"] = [runs.get((a, b), 0) for a, b in zip(pr.a, pr.b)]
    last_session = len(B.dates) - 1
    slack = 5
    rows = []
    for r in pr.itertuples():
        base = dict(overlap_days=0, share_of_overlap=np.nan, pre_a=0, pre_b=0, post_a=0, post_b=0, klass="coincidence_short",
                    retired_symbol="", switch_date="")
        sym_a, sym_b = B.cats[r.a], B.cats[r.b]
        if r.n_match >= min_run:
            ba, bb = B.di[B.sl(r.a)], B.di[B.sl(r.b)]
            ov = len(np.intersect1d(ba, bb, assume_unique=True))
            m_i = ba[(ba >= r.first_di)][:20]
            px0 = float(np.median(B.c[B.sl(r.a)][np.isin(ba, m_i)])) if len(m_i) else np.nan
            base.update(px_first20=px0, spac_like=bool(9.5 <= px0 <= 10.6 and r.first_di > 5), overlap_days=ov, share_of_overlap=r.n_match / max(ov, 1), bars_a=len(ba), bars_b=len(bb),
                        pre_a=int((ba < r.first_di).sum()), pre_b=int((bb < r.first_di).sum()),
                        post_a=int((ba > r.last_di).sum()), post_b=int((bb > r.last_di).sum()),
                        a_first=B.dates[ba[0]], a_last=B.dates[ba[-1]], b_first=B.dates[bb[0]], b_last=B.dates[bb[-1]])
            if r.med_dv < 1000 or r.n_flat == r.n_match:
                base["klass"] = "coincidence_thin"
            elif suffix_relation(sym_a, sym_b):
                base["klass"] = "share_class_or_derivative"
            elif base["share_of_overlap"] < 0.05:
                base["klass"] = "coincidence_sparse"      # e.g. a when-issued / spin-off window: 11 of 722 shared days
            elif base["share_of_overlap"] < 0.9:
                base["klass"] = "partial_overlap"
            else:
                ra, rb = base["post_a"] <= slack, base["post_b"] <= slack
                if ra != rb:
                    base["klass"] = "retired_symbol"
                    base["retired_symbol"] = sym_a if ra else sym_b
                    base["switch_date"] = B.dates[min(r.last_di + 1, last_session)]
                elif ra and rb:
                    base["klass"] = "twin_to_window_end" if r.last_di >= last_session - slack else "both_retired"
                else:
                    base["klass"] = "diverged_after_run"
        rows.append(base)
    pr = pd.concat([pr, pd.DataFrame(rows)], axis=1)
    pr["sym_a"], pr["sym_b"] = B.cats[pr.a], B.cats[pr.b]
    pr["name_a"], pr["name_b"] = pr.sym_a.map(names), pr.sym_b.map(names)
    pr["first_match"], pr["last_match"] = B.dates[pr.first_di], B.dates[pr.last_di]
    pr["name_hint"] = [name_hint(x, y) for x, y in zip(pr.name_a, pr.name_b)]
    pr["confirmed"] = ~pr.klass.str.startswith("coincidence")
    fl = mm.merge(pr.loc[pr.confirmed, ["a", "b", "klass"]], on=["a", "b"])
    fl["date"] = B.dates[fl.di.astype(int)]
    return mm, pr, fl


# ---------------------------------------------------------------- test 2: scaled twins
def scaled_twins(B, strict_set, window=8, min_days=20, min_abs_ret=0.03, ratio_tol=0.005):
    ok = np.r_[False, (B.tc[1:] == B.tc[:-1]) & ((B.di[1:] - B.di[:-1]) <= 3)]
    prev = np.r_[np.nan, B.c[:-1]]
    with np.errstate(divide="ignore", invalid="ignore"):
        key = np.round(np.where(ok & (prev > 0), B.c / prev - 1, np.nan) * 1e4)
    sel = (np.abs(key) >= min_abs_ret * 1e4) & (B.v > 0) & (B.c * B.v >= 1e5)
    e = pd.DataFrame({"tc": B.tc[sel], "di": B.di[sel], "key": key[sel]}).sort_values(["di", "key"]).reset_index(drop=True)
    di, kk, tc = e.di.values, e.key.values, e.tc.values
    out = []
    for k in range(1, window + 1):
        i = np.flatnonzero((di[:-k] == di[k:]) & (kk[:-k] == kk[k:]) & (tc[:-k] != tc[k:]))
        out.append(pd.DataFrame({"a": np.minimum(tc[i], tc[i + k]), "b": np.maximum(tc[i], tc[i + k]), "di": di[i]}))
    mm = pd.concat(out, ignore_index=True).drop_duplicates()
    cand = mm.groupby(["a", "b"]).size().reset_index(name="n_ret_match")
    cand = cand[cand.n_ret_match >= min_days]
    rows, flagged = [], []
    for r in cand.itertuples():
        if (r.a, r.b) in strict_set:
            continue
        sa, sb = B.sl(r.a), B.sl(r.b)
        ja = pd.DataFrame({"di": B.di[sa], "ca": B.c[sa], "va": B.v[sa]}).set_index("di")
        jb = pd.DataFrame({"di": B.di[sb], "cb": B.c[sb], "vb": B.v[sb]}).set_index("di")
        j = ja.join(jb, how="inner")
        j = j[(j.va > 0) & (j.vb > 0) & (j.ca > 0) & (j.cb > 0)]
        if len(j) == 0:
            continue
        lr = np.log(j.ca / j.cb)
        mdays = mm[(mm.a == r.a) & (mm.b == r.b)].di.values
        med = float(lr.loc[lr.index.isin(mdays)].median())
        dvl = np.log((j.ca * j.va) / (j.cb * j.vb))
        # same price scale-factor AND same dollar volume (volume inversely scaled, to within share rounding)
        within = ((lr - med).abs() <= ratio_tol) & (dvl.abs() <= 0.05 + 1.0 / np.minimum(j.va, j.vb))
        n_scaled = int(within.sum())
        dvr = float(dvl.median())
        if n_scaled < min_days:
            continue
        kind = "scaled_twin_full" if within.mean() >= 0.95 else "scaled_twin_partial"
        rows.append(dict(a=r.a, b=r.b, sym_a=B.cats[r.a], sym_b=B.cats[r.b], n_ret_match=r.n_ret_match, overlap_days=len(j),
                         n_scaled_days=n_scaled, share_of_overlap=n_scaled / len(j), price_factor_a_over_b=float(np.exp(med)),
                         log_dollar_vol_ratio=dvr, kind=kind, first_scaled=B.dates[within.index[within][0]],
                         last_scaled=B.dates[within.index[within][-1]]))
        flagged.append(pd.DataFrame({"di": within.index[within].values, "a": r.a, "b": r.b}))
    sc = pd.DataFrame(rows)
    fl = pd.concat(flagged, ignore_index=True) if flagged else pd.DataFrame({"di": [], "a": [], "b": []})
    return sc, fl, len(e)


# ---------------------------------------------------------------- test 3: OHLC-only
def probe_ohlc_only(B, tol, min_run, window, skip):
    mm = match_rows(B, tol, window, fields=("o", "h", "l", "c"), sortkeys=("c", "o", "h"))
    mm = mm[mm.rng >= 0.01]          # a bar that moved < 1% intraday matches by chance (SPAC trust prices ~$10.0x)
    if len(mm) == 0:
        return pd.DataFrame()
    g = mm.groupby(["a", "b"]).agg(n_match=("di", "size"), first_di=("di", "min"), last_di=("di", "max"), med_dv=("dv", "median"),
                                   n_flat=("flat", "sum")).reset_index()
    g = g[(g.n_match >= min_run) & (g.med_dv >= 1000) & (g.n_flat < g.n_match)]
    g = g[[(a, b) not in skip for a, b in zip(g.a, g.b)]] if len(g) else g
    if len(g) == 0:
        return pd.DataFrame()
    g["sym_a"], g["sym_b"] = B.cats[g.a], B.cats[g.b]
    g["first_match"], g["last_match"] = B.dates[g.first_di], B.dates[g.last_di]
    return g.sort_values("n_match", ascending=False)


# ---------------------------------------------------------------- suggested de-duplication
def dedupe_map(pr, sc):
    """One row per confirmed twin pair: which symbol to DROP so one series per company remains.  A hint, not an order: the point-in-time
    symbol (Polygon ticker events) and whichever symbol has minute bars on disk outrank it when they disagree."""
    rows = []
    if len(pr):
        for r in pr[pr.confirmed].itertuples():
            if r.klass == "retired_symbol":
                drop = r.retired_symbol; why = "old symbol retired on the switch date; successor carries the same history"
            else:
                drop = r.sym_a if r.bars_a < r.bars_b else r.sym_b; why = "fewer bars dropped (inspect: " + r.klass + ")"
            rows.append(dict(sym_a=r.sym_a, sym_b=r.sym_b, kind=r.klass, drop_hint=drop, matched_days=r.n_match, first=r.first_match,
                             last=r.last_match, switch_date=r.switch_date, why=why))
    if len(sc):
        for r in sc.itertuples():
            rows.append(dict(sym_a=r.sym_a, sym_b=r.sym_b, kind=r.kind, drop_hint="(decide: compare adj/raw against the split table)",
                             matched_days=r.n_scaled_days, first=r.first_scaled, last=r.last_scaled, switch_date="",
                             why=f"close ratio a/b = {r.price_factor_a_over_b:.6g} constant, dollar volume equal"))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- impact
def breakout_counts(B, excess_keys):
    """excess_keys: DataFrame(tc, di).  Returns {name: per-year DataFrame(rows, excess)}."""
    ok = np.r_[False, (B.tc[1:] == B.tc[:-1]) & ((B.di[1:] - B.di[:-1]) <= 5)]
    prev = np.r_[np.nan, B.c[:-1]]
    ok &= prev > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        d = pd.DataFrame({"tc": B.tc, "di": B.di, "gap": np.where(ok, B.o / prev - 1, np.nan), "ret": np.where(ok, B.c / prev - 1, np.nan),
                          "dv": B.c * B.v})
    ex = excess_keys.drop_duplicates(["tc", "di"]).assign(excess=True)
    d = d.merge(ex, on=["tc", "di"], how="left")
    d["excess"] = d.excess.eq(True)
    d["year"] = B.dates[d.di.values.astype(int)]
    d["year"] = pd.Series(d.year).str[:4].values
    res = {}
    for nm, m in (("gap>=10% & $vol>=1M", (d.gap >= .10) & (d.dv >= 1e6)), ("ret>=15% & $vol>=1M", (d.ret >= .15) & (d.dv >= 1e6)),
                  ("ret>=50% & $vol>=1M", (d.ret >= .50) & (d.dv >= 1e6))):
        res[nm] = d[m].groupby("year").agg(rows=("tc", "size"), excess=("excess", "sum"))
    return res


# ---------------------------------------------------------------- cross-export seam
def seam_check(path_a, path_b, cut, lo=None, hi=None):
    """Same symbol on the same date in two exports: do the closes agree?  A stitched A+B backtest has a scale jump at the seam for
    every symbol that does not.  Compares the window where both exports have bars."""
    A, Bx = load(path_a, cut), load(path_b, cut)
    lo = lo or max(A.d.min(), Bx.d.min()); hi = hi or min(A.d.max(), Bx.d.max())
    A, Bx = A[(A.d >= lo) & (A.d <= hi)], Bx[(Bx.d >= lo) & (Bx.d <= hi)]
    m = A[["t", "d", "c", "v"]].astype({"t": "string"}).merge(Bx[["t", "d", "c", "v"]].astype({"t": "string"}), on=["t", "d"], suffixes=("_a", "_b"))
    m = m[(m.c_a > 0) & (m.c_b > 0)]
    m["lr"] = np.log(m.c_a / m.c_b)
    m["agree"] = m.lr.abs() <= 0.01                 # a 1% close difference is feed noise; a seam JUMP is far larger
    m["off01"] = m.lr.abs() > 1e-3
    g = m.groupby("t").agg(n=("lr", "size"), n_agree=("agree", "sum"), n_over_0p1pct=("off01", "sum"), med_lr=("lr", "median"),
                           sd_lr=("lr", "std")).reset_index()
    bad = g[g.n_agree < g.n].copy()
    bad["kind"] = np.where((bad.sd_lr.fillna(0) < 0.005) & (bad.n_agree == 0), "constant_scale_mismatch",
                           np.where(bad.n_agree == 0, "disagree_varying", "partly_disagree"))
    bad["factor_a_over_b"] = np.exp(bad.med_lr)
    summ = dict(window=f"{lo}..{hi}", symbols_a=A.t.nunique(), symbols_b=Bx.t.nunique(), shared_rows=len(m), agree_within_1pct_rows=int(m.agree.sum()), rows_over_0p1pct=int(m.off01.sum()),
                symbols_shared=len(g), symbols_all_agree=int((g.n_agree == g.n).sum()), symbols_with_mismatch=len(bad))
    return summ, bad.sort_values("n", ascending=False)


# ---------------------------------------------------------------- driver
def run(path, label, outdir, cut, assets, tol, min_run, window, quiet=False, probes=True):
    df = load(path, cut)
    names = {}
    if assets and os.path.exists(assets):
        for ln in open(assets):
            p = ln.rstrip("\n").split("\t")
            if len(p) > 1 and p[0] != "symbol":
                names[p[0]] = p[1]
    B = Bars(df)
    del df
    lines = []
    P = lambda s="": lines.append(s)
    P(f"== duplicate-series check: {label}  file={path}  cut={cut}  tol={tol}  min_run={min_run}  window={window}")
    nb, nsym = len(B.tc), len(B.cats)
    P(f"bars={nb:,}  symbols={nsym:,}  sessions={len(B.dates):,}  first={B.dates[0]}  last={B.dates[-1]}")
    mm, pr, fl = strict_pairs(B, tol, min_run, window, names)
    P(f"TEST 1 strict twins: matched row-pairs (any class)={len(mm):,}  exact={int(mm.exact.sum()):,}  pairs with >=2 matched days={len(pr):,}")
    conf = pr[pr.confirmed] if len(pr) else pr
    excess = pd.DataFrame({"tc": [], "di": []})
    if len(pr):
        P(pr.groupby("klass").agg(pairs=("n_match", "size"), matched_days=("n_match", "sum"), exact_days=("n_exact", "sum"),
                                  median_longest_run=("longest_run", "median")).to_string())
        P(f"spac_like confirmed pairs (first 20 matched closes in $9.50-$10.60 and the history starts inside the window)={int(conf.spac_like.sum())}")
        P(f"CONFIRMED strict pairs={len(conf):,}  matched days={int(conf.n_match.sum()):,}  "
          f"of which match >=90% of their overlap={int((conf.share_of_overlap >= .9).sum()):,}")
        excess = fl[["di", "b"]].rename(columns={"b": "tc"}).drop_duplicates()
        P("-- largest confirmed pairs by matched days (top 25)")
        cols = ["sym_a", "sym_b", "klass", "retired_symbol", "n_match", "longest_run", "share_of_overlap", "first_match", "last_match", "spac_like", "name_hint"]
        P(conf.sort_values("n_match", ascending=False).head(25)[cols].to_string(index=False))
    n_strict_excess = len(excess)
    P(f"strict excess (double-counted) rows={n_strict_excess:,} of {nb:,} bars = {n_strict_excess / nb:.4%}")
    sc = pd.DataFrame(); sc_fl = pd.DataFrame({"di": [], "a": [], "b": []}); po = pd.DataFrame()
    if probes:
        sset = set(zip(conf.a, conf.b)) if len(conf) else set()
        sc, sc_fl, nscan = scaled_twins(B, sset, window)
        P(f"TEST 2 scaled twins (price-scale copies): rows scanned={nscan:,}; pairs={len(sc):,}")
        if len(sc):
            P(sc.groupby("kind").agg(pairs=("a", "size"), scaled_days=("n_scaled_days", "sum")).to_string())
            P(sc.sort_values("n_scaled_days", ascending=False).head(30)[["sym_a", "sym_b", "kind", "n_scaled_days", "overlap_days",
              "price_factor_a_over_b", "log_dollar_vol_ratio", "first_scaled", "last_scaled"]].to_string(index=False))
        sc_ex = sc_fl[["di", "b"]].rename(columns={"b": "tc"}) if len(sc_fl) else pd.DataFrame({"di": [], "tc": []})
        P(f"scaled-twin excess rows={len(sc_ex.drop_duplicates()):,}")
        excess = pd.concat([excess, sc_ex], ignore_index=True).drop_duplicates()
        po = probe_ohlc_only(B, tol, min_run, window, sset | set(zip(sc.a, sc.b) if len(sc) else []))
        P(f"TEST 3 ohlc_only (equal O/H/L/C, range >= 1%, volume differs, >= {min_run} days, not already found): pairs={len(po):,}")
        if len(po):
            P(po.head(15)[["sym_a", "sym_b", "n_match", "first_match", "last_match", "med_dv"]].to_string(index=False))
    P(f"TOTAL excess rows (strict + scaled, union)={len(excess):,} = {len(excess) / nb:.4%} of bars")
    # per year
    yr = pd.Series(B.dates[B.di]).str[:4].values
    py = pd.DataFrame({"bars": pd.Series(yr).value_counts().sort_index()})
    if len(excess):
        ey = pd.Series(B.dates[excess.di.values.astype(int)]).str[:4]
        py["excess_rows"] = ey.value_counts()
        if len(fl):
            py["strict_pairs_active"] = pd.Series(B.dates[fl.di.values.astype(int)]).str[:4].groupby(
                [fl.a.values, fl.b.values]).first().groupby(level=[0, 1]).size().reindex(py.index) if False else np.nan
            f2 = fl.assign(y=pd.Series(B.dates[fl.di.values.astype(int)]).str[:4].values)
            py["strict_pairs_active"] = f2.groupby("y").apply(lambda x: len(x[["a", "b"]].drop_duplicates()), include_groups=False)
            py["strict_excess_rows"] = f2.groupby("y")[["di", "b"]].apply(lambda x: len(x.drop_duplicates()), include_groups=False)
        if len(sc_fl):
            s2 = sc_fl.assign(y=pd.Series(B.dates[sc_fl.di.values.astype(int)]).str[:4].values)
            py["scaled_pairs_active"] = s2.groupby("y").apply(lambda x: len(x[["a", "b"]].drop_duplicates()), include_groups=False)
    py = py.fillna(0).astype(int)
    P("-- per year"); P(py.to_string())
    for nm, tb in breakout_counts(B, excess).items():
        tb = tb.assign(share=(tb.excess / tb.rows).round(4))
        P(f"-- breakout-scale rows [{nm}]  total={int(tb.rows.sum()):,}  double-counted={int(tb.excess.sum()):,}  share={tb.excess.sum() / max(tb.rows.sum(), 1):.4%}")
        P(tb.to_string())
    txt = "\n".join(lines)
    if outdir:
        os.makedirs(outdir, exist_ok=True)
        if len(pr):
            pr.drop(columns=["a", "b", "first_di", "last_di"]).sort_values(["confirmed", "n_match"], ascending=False).to_csv(
                f"{outdir}/{label}_pairs.tsv", sep="\t", index=False)
            f = fl.copy(); f["sym_a"], f["sym_b"] = B.cats[f.a.astype(int)], B.cats[f.b.astype(int)]
            f[["date", "sym_a", "sym_b", "klass", "exact", "flat", "dv"]].to_csv(f"{outdir}/{label}_flagged_rows.tsv", sep="\t", index=False)
        if len(sc):
            sc.drop(columns=["a", "b"]).to_csv(f"{outdir}/{label}_scaled_twins.tsv", sep="\t", index=False)
        if len(po):
            po.drop(columns=["a", "b", "first_di", "last_di"]).to_csv(f"{outdir}/{label}_probe_ohlc_only.tsv", sep="\t", index=False)
        dm = dedupe_map(pr, sc)
        if len(dm):
            dm.to_csv(f"{outdir}/{label}_dedupe_map.tsv", sep="\t", index=False)
        py.to_csv(f"{outdir}/{label}_per_year.tsv", sep="\t")
        open(f"{outdir}/{label}_summary.txt", "w").write(txt + "\n")
    if not quiet:
        print(txt)
    return dict(B=B, pairs=pr, flagged=fl, excess=excess, scaled=sc, ohlc_only=po, per_year=py)


# ---------------------------------------------------------------- self-test (positive + negative controls)
def selftest():
    rng = np.random.default_rng(1)
    dts = pd.bdate_range("2020-01-01", periods=120).strftime("%Y-%m-%d")
    n = len(dts)
    def series(px0):
        px = px0 * np.exp(np.cumsum(rng.normal(0, .04, n)))
        return [(px[i] * .99, px[i] * 1.02, px[i] * .98, px[i], float(rng.integers(1e5, 1e6))) for i in range(n)]
    base = {t: series(20 + 7 * i) for i, t in enumerate(["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"])}
    rows = []
    for t, s in base.items():
        rows += [(t, d) + r for d, r in zip(dts, s)]
    rows += [("AAAX", d) + r for d, r in zip(dts, base["AAA"])]                                    # exact twin to window end
    rows += [("BBBX", d) + tuple(x * 1.00005 for x in r) for d, r in zip(dts, base["BBB"])]        # near twin (0.005%)
    rows += [("CCCX", d) + r for d, r in zip(dts[:3], base["CCC"][:3])]                            # 3-day coincidence
    rows += [("NEG", d) + tuple(list(base["DDD"][i][:4]) + [12345.0]) for i, d in enumerate(dts)]  # same prices, other volume
    rows += [("EEEX", d) + tuple(x * 25 for x in r[:4]) + (r[4] / 25,) for d, r in zip(dts, base["EEE"])]  # scaled twin x25
    # old symbol OLDF retired after 60 sessions, successor FFF carries on
    rows += [("OLDF", d) + r for d, r in list(zip(dts, base["FFF"]))[:60]]
    import tempfile
    p = os.path.join(tempfile.mkdtemp(), "dup_selftest.csv.gz")
    pd.DataFrame([r for r in rows if not (r[0] == "FFF")] + [("FFF", d) + r for d, r in zip(dts, base["FFF"])]).to_csv(
        p, header=False, index=False, compression="gzip")
    res = run(p, "selftest", None, "2024-12-31", None, 1e-4, 5, 8, quiet=True)
    pr = res["pairs"].set_index(["sym_a", "sym_b"])
    assert pr.loc[("AAA", "AAAX"), "n_exact"] == n and pr.loc[("AAA", "AAAX"), "klass"] == "twin_to_window_end", "exact twin"
    assert pr.loc[("BBB", "BBBX"), "n_match"] == n and pr.loc[("BBB", "BBBX"), "n_exact"] == 0, "near twin"
    assert pr.loc[("CCC", "CCCX"), "klass"] == "coincidence_short", "short coincidence"
    assert not any("NEG" in k for k in pr.index), "different-volume series wrongly matched"
    assert pr.loc[("FFF", "OLDF"), "klass"] == "retired_symbol" and pr.loc[("FFF", "OLDF"), "retired_symbol"] == "OLDF", "retired symbol"
    assert pr.loc[("FFF", "OLDF"), "switch_date"] == dts[60], "switch date"
    sc = res["scaled"].set_index(["sym_a", "sym_b"])
    assert ("EEE", "EEEX") in sc.index and sc.loc[("EEE", "EEEX"), "kind"] == "scaled_twin_full", "scaled twin missed"
    assert abs(sc.loc[("EEE", "EEEX"), "price_factor_a_over_b"] - 1 / 25) < 1e-3 and abs(sc.loc[("EEE", "EEEX"), "log_dollar_vol_ratio"]) < 1e-6
    assert len(res["excess"]) == n * 3 + 60, f"excess {len(res['excess'])}\n{res['pairs'][['sym_a','sym_b','klass','n_match']]}\n{res['scaled']}"
    try:
        load(p, "2025-06-30"); raise AssertionError("sealed guard failed")
    except SystemExit as e:
        assert "sealed" in str(e)
    print("selftest OK: exact twin, near twin 0.005%, 3-day coincidence, different-volume negative, retired symbol + switch date, "
          "scaled x25 twin, excess count, sealed guard")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", nargs="?")
    ap.add_argument("--label", default="export"); ap.add_argument("--out", default=None)
    ap.add_argument("--cut", default=SEALED_AFTER)
    ap.add_argument("--assets", default="/Users/alvinfung/apollo_data/cb702/qm_streams/alpaca_all_2016_2022/assets.tsv")
    ap.add_argument("--tol", type=float, default=1e-4); ap.add_argument("--min-run", type=int, default=5)
    ap.add_argument("--window", type=int, default=8); ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--no-probes", action="store_true", help="skip the scaled-twin and ohlc-only tests")
    ap.add_argument("--vs", default=None, help="a second export: also run the cross-export seam check on the dates both cover")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    else:
        if not a.export:
            ap.error("export path required")
        run(a.export, a.label, a.out, a.cut, a.assets, a.tol, a.min_run, a.window, probes=not a.no_probes)
        if a.vs:
            summ, bad = seam_check(a.export, a.vs, a.cut)
            print("== SEAM check", summ)
            print(bad.groupby("kind").agg(symbols=("t", "size"), rows=("n", "sum")).to_string())
            print(bad.head(20).to_string(index=False))
            if a.out:
                bad.to_csv(f"{a.out}/{a.label}_vs_seam_mismatch.tsv", sep="\t", index=False)
