"""#702 P4b extension - Alpaca 2016-2022 daily bars: load, de-duplicate, identity guard, rename map ($0: local files only).

Inputs (already on disk, fetched by the main loop): ALP/raw/b*.csv.gz and ALP/split/b*.csv.gz, rows
`ticker,date,open,high,low,close,volume,vwap,trade_count` (no header). Output: a flat, ticker-sorted numpy cache
(`alp_flat.npz`), `symbol_guard.tsv`, `rename_map.tsv`, `alp_build_stats.tsv`.

Alpaca FORWARD-FILLS a dormant symbol: a delisted name keeps printing its last close with volume 0 until the symbol is reused
(DNB: 144.95 for ~340 flat zero-volume sessions, then the 2020 re-IPO at 25.35). Those rows are not trades, so they are DROPPED
here (Polygon has no row for a no-trade day either) and the span becomes a real hole in the session sequence - which is also how
"two companies on one symbol" shows up as a > 30-session hole.

Identity guard. A "break" is a place where one symbol's series changes hands or is corrupted; the guard works PER NIGHT (a
night is ineligible when a break falls inside the 130 bars it needs), not by banning the whole symbol - NIO (pre-IPO junk under the
symbol until 2018) and AA (the 2016-11 Arconic split) are clean after the break and are the stocks we want. Two kinds of break:
  hole   : > 30 SPY sessions with no traded bar inside the symbol's own span. The break date is the first bar AFTER the hole.
  jump   : a > 70 % one-session SPLIT-close move that is NOT a real shock - no volume event (day volume < 3x the mean of the prior
           20 traded sessions, >= 5 prior) or the raw/split factor changes the same day (a corporate action the split series
           did not absorb, e.g. a spin-off). A > 70 % move WITH a volume event is a genuine shock (NIO IPO pop, MDGL on its data)
           and is kept: those are the EP-then-base poles we want. `jump_literal` = the unrefined test (any > 70 % move) so the
           report can say what the literal rule would have dropped. (GME Jan-2021 trips the refined test - its prior 20 sessions
           already carried squeeze volume - and loses a few nights; noted, not tuned.)
Overlap check vs Polygon on 2021-09-27..2022-06-30 (median |Alpaca split close / Polygon close - 1| > 2 %, >= 5 shared days):
  constant_scale : same series, different split factor (kept; the features are ratios)
  polygon_reuse  : Alpaca's series is continuous across the overlap (no break there) so the symbol was held by a different issuer on
                   the POLYGON side (META = a ~$10 ETF in Polygon until 2022-06, Facebook in Alpaca throughout; BNY likewise) - kept
  alpaca_break   : Alpaca itself breaks inside the overlap - the per-night break rule excludes those nights
"""
import csv
import datetime as dt
import glob
import os
import sys

import numpy as np
import pandas as pd

ALP = "/Users/alvinfung/apollo_data/cb702/qm_streams/alpaca_all_2016_2022"
POLY = "/Users/alvinfung/apollo_data/cb702/daily_closes_all.csv.gz"
OVERLAP_LO, OVERLAP_HI = dt.date(2021, 9, 27), dt.date(2022, 6, 30)
GAP_MAX = 0.02
JUMP_MAX = 0.70
HOLE_MAX = 30
VOL_EVENT_X = 3.0
COLS = ["t", "d", "o", "h", "l", "c", "v"]


def _read(kind):
    fs = sorted(glob.glob(f"{ALP}/{kind}/b*.csv.gz"))
    parts = [pd.read_csv(f, header=None, names=COLS, usecols=range(7), dtype={"t": str}, keep_default_na=False) for f in fs]
    df = pd.concat(parts, ignore_index=True)
    df["o_d"] = pd.to_datetime(df["d"]).map(dt.datetime.toordinal).astype(np.int32)
    return df, len(fs)


def build(out):
    """-> (dict of arrays, stats); writes OUT/alp_flat.npz (traded rows only) and OUT/alp_build_stats.tsv."""
    sp, nf = _read("split")
    rw, _ = _read("raw")
    stats = {"files_per_kind": nf, "split_rows_read": len(sp), "raw_rows_read": len(rw)}
    stats.update(dup_split=int(sp.duplicated(["t", "o_d"]).sum()), dup_raw=int(rw.duplicated(["t", "o_d"]).sum()))
    sp = sp.drop_duplicates(["t", "o_d"]).sort_values(["t", "o_d"]).reset_index(drop=True)
    rw = rw.drop_duplicates(["t", "o_d"]).sort_values(["t", "o_d"]).reset_index(drop=True)
    stats["symbols_in_split_files"] = int(sp["t"].nunique())
    m = sp.merge(rw[["t", "o_d", "c"]].rename(columns={"c": "c_raw"}), on=["t", "o_d"], how="left")
    stats["split_rows_without_raw"] = int(m["c_raw"].isna().sum())
    stats["raw_rows_without_split"] = int((~rw.set_index(["t", "o_d"]).index.isin(sp.set_index(["t", "o_d"]).index)).sum())
    m["c_raw"] = m["c_raw"].fillna(m["c"])
    bad = ~(np.isfinite(m[["o", "h", "l", "c", "v"]]).all(axis=1) & (m[["o", "h", "l", "c"]] > 0).all(axis=1))
    stats["bad_rows_dropped"] = int(bad.sum())
    m = m[~bad]
    zero = m["v"] <= 0
    stats["zero_volume_rows_dropped"] = int(zero.sum())
    stats["symbols_with_zero_volume_rows"] = int(m.loc[zero, "t"].nunique())
    m = m[~zero].reset_index(drop=True)
    codes, uniques = pd.factorize(m["t"], sort=True)
    bounds = np.concatenate(([0], np.flatnonzero(np.diff(codes)) + 1, [len(codes)]))
    arr = dict(tickers=np.array([str(u) for u in uniques]), start=bounds[:-1].astype(np.int64), stop=bounds[1:].astype(np.int64),
               d=m["o_d"].to_numpy(np.int32), o=m["o"].to_numpy(float), h=m["h"].to_numpy(float), l=m["l"].to_numpy(float),
               c=m["c"].to_numpy(float), v=m["v"].to_numpy(float), c_raw=m["c_raw"].to_numpy(float))
    stats["symbols_with_traded_bars"] = len(arr["tickers"])
    stats["traded_rows_kept"] = len(arr["d"])
    np.savez(os.path.join(out, "alp_flat.npz"), **arr)
    with open(os.path.join(out, "alp_build_stats.tsv"), "w") as f:
        for k, v in stats.items():
            f.write(f"{k}\t{v}\n")
    return arr, stats


def load(out):
    z = np.load(os.path.join(out, "alp_flat.npz"), allow_pickle=False)
    return {k: z[k] for k in z.files}


def sym_index(a):
    return {str(t): k for k, t in enumerate(a["tickers"])}


def sym_bars(a, k):
    s, e = int(a["start"][k]), int(a["stop"][k])
    return {x: a[x][s:e] for x in ("d", "o", "h", "l", "c", "v", "c_raw")}


def poly_closes():
    """Polygon export (split-adjusted closes) -> {ticker: (ord array, close array)} on the overlap window only."""
    df = pd.read_csv(POLY, header=None, usecols=[0, 1, 5], names=["t", "d", "c"], dtype={"t": "category", "d": "string"}, keep_default_na=False)
    df["o_d"] = pd.to_datetime(df["d"]).map(dt.datetime.toordinal)
    lo, hi = OVERLAP_LO.toordinal(), OVERLAP_HI.toordinal()
    df = df[(df.o_d >= lo) & (df.o_d <= hi)]
    out = {}
    for t, g in df.groupby("t", observed=True):
        out[str(t)] = (g["o_d"].to_numpy(np.int32), g["c"].to_numpy(float))
    return out


def _calendar(a):
    ks = int(np.flatnonzero(a["tickers"] == "SPY")[0])
    return a["d"][int(a["start"][ks]):int(a["stop"][ks])]


def guard(a, poly):
    """Identity guard for every Alpaca symbol -> ({symbol: row dict}, {symbol: [(break_ordinal, kind), ...]})."""
    cal = _calendar(a)
    rows, brk = {}, {}
    ov_lo, ov_hi = OVERLAP_LO.toordinal(), OVERLAP_HI.toordinal()
    from numpy.lib.stride_tricks import sliding_window_view as swv
    for k, t in enumerate(a["tickers"]):
        b = sym_bars(a, k)
        d, c, v, cr = b["d"], b["c"], b["v"], b["c_raw"]
        r = dict(symbol=str(t), n=len(d), first=dt.date.fromordinal(int(d[0])).isoformat(), last=dt.date.fromordinal(int(d[-1])).isoformat(),
                 overlap_n=0, overlap_med_gap="", overlap_kind="", max_hole=0, n_holes=0, n_move70=0, n_move70_vol_event=0,
                 n_jump=0, jump_literal=0, n_move70_nosplit=0, max_dv20="", breaks="", flags="")
        flags, blist = [], []
        if len(d) >= 20:                       # best 20-session MEDIAN dollar volume the symbol ever had (liquidity proxy for the alias review)
            r["max_dv20"] = int(np.median(swv(c * v, 20), axis=1).max())
        if len(d) >= 2:
            ci = np.searchsorted(cal, d)
            gaps = np.diff(ci) - 1
            r["max_hole"] = int(gaps.max())
            for j in np.flatnonzero(gaps > HOLE_MAX):
                blist.append((int(d[j + 1]), "hole"))
            r["n_holes"] = int((gaps > HOLE_MAX).sum())
            mv = np.abs(c[1:] / c[:-1] - 1.0)
            big = np.flatnonzero(mv > JUMP_MAX)
            r["n_move70"] = int(len(big))
            r["jump_literal"] = int(len(big) > 0)
            for j in big:
                j1 = int(j) + 1
                pv = v[max(0, j1 - 20):j1]
                vol_event = len(pv) >= 5 and v[j1] >= VOL_EVENT_X * pv.mean()
                fac_change = abs((cr[j1] / c[j1]) / (cr[j1 - 1] / c[j1 - 1]) - 1.0) > 0.01
                if vol_event:
                    r["n_move70_vol_event"] += 1
                if not fac_change:
                    r["n_move70_nosplit"] += 1
                if (not vol_event) or fac_change:
                    blist.append((int(d[j1]), "jump"))
                    r["n_jump"] += 1
        if r["n_holes"]:
            flags.append("hole")
        if r["n_jump"]:
            flags.append("jump")
        if str(t) in poly:
            pd_, pc = poly[str(t)]
            idx = np.searchsorted(d, pd_)
            ok = (idx < len(d)) & (d[np.minimum(idx, len(d) - 1)] == pd_)
            if ok.sum() >= 5:
                lr = np.log(c[idx[ok]] / pc[ok])
                gap = np.abs(np.exp(lr) - 1.0)
                r["overlap_n"] = int(ok.sum())
                r["overlap_med_gap"] = round(float(np.median(gap)), 5)
                if np.median(gap) > GAP_MAX:
                    if float(np.std(lr)) < 0.02:
                        r["overlap_kind"] = "constant_scale"
                    elif any(ov_lo <= bo <= ov_hi for bo, _ in blist):
                        r["overlap_kind"] = "alpaca_break"
                    else:
                        r["overlap_kind"] = "polygon_reuse"
                    flags.append("overlap_" + r["overlap_kind"])
        blist.sort()
        r["breaks"] = ";".join(f"{dt.date.fromordinal(o).isoformat()}:{kind}" for o, kind in blist)
        r["flags"] = "|".join(flags)
        rows[str(t)] = r
        brk[str(t)] = blist
    return rows, brk


def write_guard(rows, out):
    cols = ["symbol", "n", "first", "last", "overlap_n", "overlap_med_gap", "overlap_kind", "max_hole", "n_holes", "n_move70",
            "n_move70_vol_event", "n_jump", "jump_literal", "n_move70_nosplit", "max_dv20", "breaks", "flags"]
    with open(os.path.join(out, "symbol_guard.tsv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in rows.values():
            w.writerow(r)


def rename_map(a, poly, anchor=dt.date(2022, 3, 31), tol=0.002):
    """Polygon tickers with NO Alpaca series (renamed since: SQ -> XYZ) -> the Alpaca symbol carrying the same closes.
    Match on the anchor-day close, then require a median close gap < tol on every shared overlap day. Pure data matching:
    nothing is hand-listed."""
    idx = sym_index(a)
    a_ord = anchor.toordinal()
    names, closes = [], []
    for t, k in idx.items():
        b = sym_bars(a, k)
        j = np.searchsorted(b["d"], a_ord)
        if j < len(b["d"]) and b["d"][j] == a_ord:
            names.append(t)
            closes.append(float(b["c"][j]))
    closes = np.array(closes)
    order = np.argsort(closes)
    names, closes = [names[i] for i in order], closes[order]
    out = {}
    for t, (pd_, pc) in poly.items():
        if t in idx or len(pd_) < 100:
            continue
        j = np.searchsorted(pd_, a_ord)
        if j >= len(pd_) or pd_[j] != a_ord:
            continue
        c0 = float(pc[j])
        lo = np.searchsorted(closes, c0 * (1 - tol))
        hi = np.searchsorted(closes, c0 * (1 + tol), side="right")
        hits = []
        for q in range(lo, hi):
            S = names[q]
            b = sym_bars(a, idx[S])
            ii = np.searchsorted(b["d"], pd_)
            ok = (ii < len(b["d"])) & (b["d"][np.minimum(ii, len(b["d"]) - 1)] == pd_)
            if ok.sum() >= 100 and float(np.median(np.abs(b["c"][ii[ok]] / pc[ok] - 1.0))) < tol:
                hits.append((S, int(ok.sum())))
        if len(hits) == 1:
            out[t] = hits[0]
    return out


def write_rename(m, out):
    with open(os.path.join(out, "rename_map.tsv"), "w") as f:
        f.write("polygon_ticker\talpaca_symbol\tshared_days\n")
        for t, (s, n) in sorted(m.items()):
            f.write(f"{t}\t{s}\t{n}\n")


if __name__ == "__main__":
    out = sys.argv[1]
    a, st = build(out)
    print(st)
    poly = poly_closes()
    g, brk = guard(a, poly)
    write_guard(g, out)
    import collections
    print(collections.Counter(f for r in g.values() for f in (r["flags"].split("|") if r["flags"] else ["none"])))
    print("symbols with a break:", sum(1 for r in g.values() if r["breaks"]), "| literal >70% move symbols:", sum(r["jump_literal"] for r in g.values()))
    rm = rename_map(a, poly)
    write_rename(rm, out)
    print("renames", len(rm))
