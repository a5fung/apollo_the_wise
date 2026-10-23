#!/usr/bin/env python3
"""#702 R decomposition, step 2: the stock's path INDEPENDENT of our stop (ADR units), our trade's path, and a matched control.

Per era (2017-21 = cb702_pre, 2022-24 = cb702) this writes, under DATA/out/:
  r_decomp_fills_<era>.tsv.gz    one row per published C0 / tl / ORH5 / pp MATURE fill (13,363 / 8,984) + the path columns
  r_decomp_control_<era>.tsv.gz  one row per (E, universe ticker) control candidate (price >= $5 adjusted, 20-session median
                                 dollar volume >= $10M, 130 consecutive sessions, ticker ^[A-Z]{1,5}$, all at D = the session
                                 before E; tickers with a C0 fill on that E or a watch row at D are excluded)
  and the small file scripts/probes/_702_r_decomposition_1022/02_build_checks.txt (the consistency checks).

HARD SCOPE: the cb702 export is cut at 2024-12-31 at load (asserted). No bar after that date is read for any fill; a window
that does not fit before the cut is flagged incomplete (complete_20 / complete_60 = 0) and the report excludes it.
Windows: the forward window is (E, E+k] in SPY sessions - it starts the session AFTER E. Day 0 (E) is NOT in the MFE / MAE;
a separate flag records whether E's own daily high already stood T ADR above the fill (the daily bar cannot tell before/after the fill).
ADR20 = mean of (high - low) / close over the 20 sessions ending at D (the module's `adr20_pct_from_bars`), as a fraction.
Nothing under DATA is modified or deleted; the runner is not imported.
"""
from __future__ import annotations
import re, sys, time
import numpy as np, pandas as pd

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_r_decomposition_1022"
ERAS = {
    "2017-21": dict(data="/Users/alvinfung/apollo_data/cb702_pre", trades="out/trades_pre_exitpb.tsv.gz",
                    watch="out/watch_tl_com.tsv.gz", cut=None),
    "2022-24": dict(data="/Users/alvinfung/apollo_data/cb702", trades="out/trades_discovery_exitpb.tsv.gz",
                    watch="out/watch.tsv.gz", cut="2024-12-31"),
}
MIN_PRICE, MIN_DV, HIST = 5.0, 10_000_000.0, 130
TICK_RE = re.compile(r"^[A-Z]{1,5}$")
THRESH = (5.0, 10.0)
HORIZONS = (5, 20, 60)
checks: list[str] = []


def log(s):
    print(s, flush=True); checks.append(s)


def load_export(path: str, cut: str | None) -> pd.DataFrame:
    t0 = time.time()
    df = pd.read_csv(path, header=None, names=["ticker", "date", "o", "h", "l", "c", "v"],
                     dtype={"ticker": str, "date": str, "o": "float32", "h": "float32", "l": "float32", "c": "float32", "v": "float64"}, keep_default_na=False)
    n0 = len(df)
    if cut:
        df = df[df.date <= cut]
        assert df.date.max() <= cut, df.date.max()
    log(f"  export {path}: {n0:,} rows, kept {len(df):,} (cut {cut}); dates {df.date.min()}..{df.date.max()}; {df.ticker.nunique():,} tickers; {time.time()-t0:.0f}s")
    return df


def wide(df: pd.DataFrame, col: str, cal: pd.Index, tickers: pd.Index) -> pd.DataFrame:
    w = df.pivot(index="date", columns="ticker", values=col).reindex(index=cal, columns=tickers)
    return w.astype("float32")


def fwd_roll(x: pd.DataFrame, k: int, fn: str) -> pd.DataFrame:
    """max/min/count over the k rows AFTER each row (the window (t, t+k]); NaN rows (holes) skipped; min_periods=1."""
    r = x.iloc[::-1].shift(1).rolling(k, min_periods=1)
    out = getattr(r, fn)()
    return out.iloc[::-1]


def build(era: str, cfg: dict):
    log(f"== {era}")
    data = cfg["data"]
    ex = load_export(f"{data}/daily_closes_all.csv.gz", cfg["cut"])
    spy = ex[ex.ticker == "SPY"].date.sort_values()
    cal = pd.Index(spy.values)
    off = (~ex.date.isin(cal)).sum()
    log(f"  calendar = SPY sessions: {len(cal)} ({cal[0]}..{cal[-1]}); off-calendar bars dropped {off:,}")
    ex = ex[ex.date.isin(cal)]
    tickers = pd.Index(sorted(ex.ticker.unique()))
    t0 = time.time()
    H, L, C, V = (wide(ex, c, cal, tickers) for c in ("h", "l", "c", "v"))
    del ex
    log(f"  wide frames {H.shape}; {time.time()-t0:.0f}s")
    cidx = {d: i for i, d in enumerate(cal)}
    last = len(cal) - 1

    # universe / matching features at each session (used at D)
    DV = (C * V).rolling(20, min_periods=20).median()
    ADR = ((H - L) / C).rolling(20, min_periods=20).mean()
    HIST130 = C.notna().astype("float32").rolling(HIST, min_periods=HIST).sum() == HIST
    RET63 = C / C.shift(63) - 1.0
    # forward paths, from the session AFTER t
    FMAX = {k: fwd_roll(H, k, "max") for k in (20, 60)}
    FMIN = {k: fwd_roll(L, k, "min") for k in (20, 60)}
    FCNT60 = fwd_roll(H, 60, "count")
    FCLOSE = {k: C.shift(-k) for k in HORIZONS}
    log(f"  rolling features done; {time.time()-t0:.0f}s")

    # ── the fills ──────────────────────────────────────────────────────────────────────────────
    t = pd.read_csv(f"{data}/{cfg['trades']}", sep="\t", low_memory=False)
    pop = t[(t.arm == "pp") & (t.entry == "orh5") & (t.K == "tl") & (t.C0 == 1)].copy()
    fills_all_E = pop.groupby("E").ticker.apply(set).to_dict()      # every C0 fill (mature or not) -> excluded from the control
    m = pop[pop.mature == 1].copy()
    log(f"  population: {len(pop)} fills, {len(m)} mature (published {13363 if era=='2017-21' else 8984})")
    m["ci"] = m.E.map(cidx)
    n_out = int(m.ci.isna().sum())
    log(f"  fills whose E lies AFTER the export cut (no bar of theirs is read; they keep their published realized_r but carry no path): {n_out} "
        f"(E dates {sorted(m.loc[m.ci.isna(), 'E'].unique())})")
    m = m[m.ci.notna()].copy()
    m["ci"] = m.ci.astype(int)
    m["di"] = m.D.map(cidx).astype(int)
    log(f"  E is the session after D for {(m.ci - m.di == 1).sum()} of {len(m)} fills (others: {sorted((m.ci - m.di).unique())})")
    tk_pos = {tk: j for j, tk in enumerate(tickers)}
    missing = [tk for tk in m.ticker.unique() if tk not in tk_pos]
    assert not missing, f"fill tickers absent from the export: {missing[:10]}"
    m["tj"] = m.ticker.map(tk_pos).astype(int)
    Hn, Ln, Cn = H.to_numpy(), L.to_numpy(), C.to_numpy()
    ci, tj = m.ci.to_numpy(), m.tj.to_numpy()
    m["h_E"], m["l_E"], m["c_E"] = Hn[ci, tj], Ln[ci, tj], Cn[ci, tj]
    m["c_D"] = Cn[ci - 1, tj]
    m["adr_calc"] = ADR.to_numpy()[ci - 1, tj]
    m["ret63_D"] = RET63.to_numpy()[ci - 1, tj]
    m["dv_D"] = DV.to_numpy()[ci - 1, tj]
    fill, stop, adr = m.fill.to_numpy(float), m.stop.to_numpy(float), m.adr20.to_numpy(float)
    # consistency: the fill sits inside E's daily bar (the export and the minute fills share one price frame)
    inbar = (fill >= m.l_E.to_numpy() * 0.99) & (fill <= m.h_E.to_numpy() * 1.01)
    log(f"  CHECK fill inside E's daily bar (+-1%): {inbar.sum()} of {len(m)} ({100*inbar.mean():.2f}%); exceptions: "
        f"{m.loc[~inbar, ['ticker','E','fill','l_E','h_E']].head(8).to_dict('records')}")
    rel = np.abs(m.adr_calc.to_numpy() - adr) / adr
    log(f"  CHECK my ADR20 at D vs the table's adr20: median rel diff {np.nanmedian(rel):.2e}, p99 {np.nanpercentile(rel, 99):.2e}, "
        f"within 1%: {(rel < 0.01).sum()} of {len(m)}; NaN {np.isnan(rel).sum()}")
    pa = m.realized_r.to_numpy(float) * m.width_adr.to_numpy(float)
    log(f"  CHECK pnl_adr == realized_r x width_adr: max abs diff {np.nanmax(np.abs(pa - m.pnl_adr.to_numpy(float))):.2e}")
    log(f"  CHECK width_adr == (fill-stop)/(adr20*fill): max abs diff {np.max(np.abs((fill-stop)/(adr*fill) - m.width_adr.to_numpy(float))):.2e}")
    m["fill_in_bar"] = inbar.astype(int)

    # the stock's path, in ADR units, from the fill and from E's close; window (E, E+k]
    for k in (20, 60):
        fm, fn = FMAX[k].to_numpy()[ci, tj], FMIN[k].to_numpy()[ci, tj]
        m[f"complete_{k}"] = ((ci + k) <= last).astype(int)
        m[f"mfe{k}_adr_fill"] = (fm - fill) / (adr * fill)
        m[f"mae{k}_adr_fill"] = (fn - fill) / (adr * fill)
        m[f"mfe{k}_adr_close"] = (fm - m.c_E) / (adr * m.c_E)
        m[f"mae{k}_adr_close"] = (fn - m.c_E) / (adr * m.c_E)
    m["fwd_bars_60"] = FCNT60.to_numpy()[ci, tj]
    m["complete_5"] = ((ci + 5) <= last).astype(int)
    for k in HORIZONS:
        fc = FCLOSE[k].to_numpy()[ci, tj]
        m[f"ret{k}_adr_close"] = (fc - m.c_E) / (adr * m.c_E)
        m[f"ret{k}_pct_close"] = fc / m.c_E - 1.0
    # first session (1..60) the stock's HIGH reached fill x (1 + T x ADR); day-0 flag beside (not counted)
    for T in THRESH:
        lvl = fill * (1 + T * adr)
        first = np.full(len(m), -1, dtype=int)
        for i in range(len(m)):
            hi = min(ci[i] + 60, last)
            seg = Hn[ci[i] + 1: hi + 1, tj[i]]
            hit = np.where(seg >= lvl[i])[0]
            if hit.size:
                first[i] = int(hit[0]) + 1
        m[f"first_{int(T)}adr"] = first
        m[f"day0_high_ge_{int(T)}adr"] = (m.h_E.to_numpy() >= lvl).astype(int)
    # the stop in the stock's path: first session (1..60) whose LOW <= the row's ORIGINAL stop (independent of our walk's bookkeeping)
    first_stop = np.full(len(m), -1, dtype=int)
    for i in range(len(m)):
        hi = min(ci[i] + 60, last)
        seg = Ln[ci[i] + 1: hi + 1, tj[i]]
        hit = np.where(seg <= stop[i])[0]
        if hit.size:
            first_stop[i] = int(hit[0]) + 1
    m["first_low_le_stop"] = first_stop
    keep = ["ticker", "D", "E", "year", "fill_month", "retrigger_chain", "C1", "adr20", "adr_calc", "fill", "stop", "width_pct", "width_adr",
            "status", "realized_r", "pnl_adr", "sessions_held", "fill_day_stop", "partial_kind", "partial_session", "partial_px", "stop_to",
            "exit_kind", "exit_px", "exit_session", "stopped_after_third_le_fill", "fwd_bars", "fwd_hole", "ci", "h_E", "l_E", "c_E", "c_D",
            "ret63_D", "dv_D", "fill_in_bar", "fwd_bars_60"] + [c for c in m.columns if c.startswith(("complete_", "mfe", "mae", "ret5_", "ret20_", "ret60_", "first_", "day0_high"))]
    out_f = f"{data}/out/r_decomp_fills_{era}.tsv.gz"
    m[keep].to_csv(out_f, sep="\t", index=False, float_format="%.6g")
    log(f"  wrote {out_f}: {len(m)} rows; complete_20 {int(m.complete_20.sum())}, complete_60 {int(m.complete_60.sum())}")

    # ── the control: every universe stock at D, measured from E's close ─────────────────────────
    w = pd.read_csv(f"{data}/{cfg['watch']}", sep="\t", usecols=["ticker", "watch_date"])
    watch_D = w.groupby("watch_date").ticker.apply(set).to_dict()
    Es = sorted(m.E.unique())
    adr_d = ADR.to_numpy(); dv_d = DV.to_numpy(); hist = HIST130.to_numpy(); ret63 = RET63.to_numpy()
    fmax = {k: FMAX[k].to_numpy() for k in (20, 60)}; fmin = {k: FMIN[k].to_numpy() for k in (20, 60)}
    fcl = {k: FCLOSE[k].to_numpy() for k in HORIZONS}
    tick_ok = np.array([bool(TICK_RE.match(tk)) for tk in tickers])
    rows = []
    n_excl = 0
    for E in Es:
        e = cidx[E]; d = e - 1
        D = cal[d]
        ok = tick_ok & (Cn[d] >= MIN_PRICE) & (dv_d[d] >= MIN_DV) & hist[d] & np.isfinite(adr_d[d]) & (adr_d[d] > 0) & np.isfinite(Cn[e])
        excl = set(fills_all_E.get(E, set())) | set(watch_D.get(D, set()))
        js = np.where(ok)[0]
        if excl:
            keep_j = np.array([tickers[j] not in excl for j in js], dtype=bool)
            n_excl += int((~keep_j).sum()); js = js[keep_j]
        ce = Cn[e, js]; a = adr_d[d, js]
        r = pd.DataFrame({"E": E, "D": D, "ticker": tickers[js], "adr20": a, "ret63_D": ret63[d, js], "c_E": ce, "dv_D": dv_d[d, js]})
        for k in (20, 60):
            r[f"complete_{k}"] = int((e + k) <= last)
            r[f"mfe{k}_adr_close"] = (fmax[k][e, js] - ce) / (a * ce)
            r[f"mae{k}_adr_close"] = (fmin[k][e, js] - ce) / (a * ce)
        r["complete_5"] = int((e + 5) <= last)
        for k in HORIZONS:
            r[f"ret{k}_adr_close"] = (fcl[k][e, js] - ce) / (a * ce)
            r[f"ret{k}_pct_close"] = fcl[k][e, js] / ce - 1.0
        rows.append(r)
    ctl = pd.concat(rows, ignore_index=True)
    out_c = f"{data}/out/r_decomp_control_{era}.tsv.gz"
    ctl.to_csv(out_c, sep="\t", index=False, float_format="%.6g")
    log(f"  wrote {out_c}: {len(ctl):,} control rows over {len(Es)} E dates (mean {len(ctl)/len(Es):.0f} per E); excluded as a fill/watch ticker: {n_excl:,}")
    # the breakout population passes its own universe filter at D in my export-based reading? (a check on the control's filter)
    bu = (m.c_D >= MIN_PRICE) & (m.dv_D >= MIN_DV)
    log(f"  CHECK breakouts passing my price/dollar-volume filter at D (adjusted close): {int(bu.sum())} of {len(m)}")


if __name__ == "__main__":
    eras = sys.argv[1:] or list(ERAS)
    for era in eras:
        build(era, ERAS[era])
    with open(f"{HERE}/02_build_checks{'_' + '_'.join(eras) if len(eras) < len(ERAS) else ''}.txt", "w") as fh:
        fh.write("\n".join(checks) + "\n")
