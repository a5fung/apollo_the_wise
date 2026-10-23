#!/usr/bin/env python3
"""#705 breakout definition, step 2: the per-entry tables and the matched control, per era, under the FROZEN definitions of
docs/analysis/cb_breakout_definition_2026-10-22.md §D (written before this ran).

Per era (2017-21 = cb702_pre, 2022-24 = cb702) writes under DATA/out/:
  bdef_fills_<era>.tsv.gz    one row per published C0 / tl / ORH5 / pp MATURE fill with a readable E bar (yesterday's r_decomp_fills
                             rows) + the base high at D (pivot_full), the fill's distance below it, s_c (first close above it, 0..60
                             from E), the R3 expansion flags on E, and the close-based forward measures (ADR20 at D)
  bdef_r1_<era>.tsv.gz       one row per (ticker, R1 day): the first close above the base high in sessions 0..59 from E, deduped;
                             R2 flags; forward measures from that close (ADR20 at t-1), from the next open, and from the next close
  bdef_kvar_<era>.tsv.gz     one row per K-variant ORH5 first-break fill (entry tables; C0 = 1, retrigger = 0), measures from E's close
  bdef_control_<era>.tsv.gz  one row per (entry day t, universe ticker) over the UNION of entry days; features at t-1; the same three
                             measure variants
HARD SCOPE: the cb702 export is cut at 2024-12-31 at load (asserted); any window past the last readable session is flagged incomplete.
Nothing under DATA is modified or deleted; the runner is never imported. Same code path measures entries and control (one function)."""
from __future__ import annotations
import os, re, sys, time
import numpy as np, pandas as pd

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_breakout_definition_1022"
ERAS = {
    "2017-21": dict(data="/Users/alvinfung/apollo_data/cb702_pre", fills="out/r_decomp_fills_2017-21.tsv.gz", watch="out/watch_tl_com.tsv.gz",
                    entries="out/entries_pre_tl_com.tsv.gz", splits=None, cut=None),
    "2022-24": dict(data="/Users/alvinfung/apollo_data/cb702", fills="out/r_decomp_fills_2022-24.tsv.gz", watch="out/watch.tsv.gz",
                    entries="out/entries_discovery.tsv.gz", splits="cb702_splits.psv", cut="2024-12-31"),
}
# optional re-run switches, 2017-21 only (#705 v2 re-run; all unset = unchanged): CB_PRE_DIR = the data dir (inputs, incl. DATA/out/r_decomp_* and
# the watch / entries tables), CB_PRE_OUT = where the bdef_* tables are written (default DATA/out), CB_PRE_LOG = where the checks file goes (default HERE)
PRE_OUT, LOG_DIR = os.environ.get("CB_PRE_OUT"), os.environ.get("CB_PRE_LOG", HERE)
if os.environ.get("CB_PRE_DIR"):
    ERAS["2017-21"]["data"] = os.environ["CB_PRE_DIR"]


def out_dir(era, data):
    return PRE_OUT if (era == "2017-21" and PRE_OUT) else f"{data}/out"


MIN_PRICE, MIN_DV, HIST = 5.0, 10_000_000.0, 130
TICK_RE = re.compile(r"^[A-Z]{1,5}$")
HOR = (1, 5, 20, 60)
R1_SCAN = 60          # sessions 0..59 from E (= D+1 .. D+60)
RANGE_X, CLOSE_LOC, VOL_X, VOL_N = 1.0, 0.70, 1.5, 50
checks: list[str] = []


def log(s):
    print(s, flush=True); checks.append(s)


def load_export(path, cut):
    t0 = time.time()
    df = pd.read_csv(path, header=None, names=["ticker", "date", "o", "h", "l", "c", "v"],
                     dtype={"ticker": str, "date": str, "o": "float32", "h": "float32", "l": "float32", "c": "float32", "v": "float64"}, keep_default_na=False)
    n0 = len(df)
    if cut:
        df = df[df.date <= cut]
        assert df.date.max() <= cut, df.date.max()
    log(f"  export {path}: {n0:,} rows, kept {len(df):,} (cut {cut}); dates {df.date.min()}..{df.date.max()}; {df.ticker.nunique():,} tickers; {time.time()-t0:.0f}s")
    return df


def wide(df, col, cal, tickers):
    return df.pivot(index="date", columns="ticker", values=col).reindex(index=cal, columns=tickers).astype("float32")


class Frame:
    """the wide arrays + the one measure function shared by entries and control"""

    def __init__(self, O, H, L, C, V, cal):
        self.O, self.H, self.L, self.C, self.V = (x.to_numpy() for x in (O, H, L, C, V))
        self.cal = cal; self.last = len(cal) - 1
        self.ADR = ((H - L) / C).rolling(20, min_periods=20).mean().to_numpy()
        self.DV = (C * V).rolling(20, min_periods=20).median().to_numpy()
        self.HIST = (C.notna().astype("float32").rolling(HIST, min_periods=HIST).sum() == HIST).to_numpy()
        self.RET63 = (C / C.shift(63) - 1.0).to_numpy()
        self.VOL50 = V.rolling(VOL_N, min_periods=VOL_N).mean().to_numpy()

    def measure(self, e: int, js: np.ndarray, adr: np.ndarray, variant: str, prefix: str) -> dict:
        """Forward measures for the entries (date index e, ticker columns js, ADR unit per row).
        variant 'close': base = C[e], window (e, e+60], ret_k = C[e+k];  'nopen': base = O[e+1], same window/returns;
        'nclose': base = C[e+1], window (e+1, e+61], ret_k = C[e+1+k]. All in ADR units: (price - base) / (adr * base)."""
        if variant == "close":
            b, base = e, self.C[e, js]
        elif variant == "nopen":
            b, base = e, (self.O[e + 1, js] if e + 1 <= self.last else np.full(len(js), np.nan, dtype="float32"))
        else:
            b, base = e + 1, (self.C[e + 1, js] if e + 1 <= self.last else np.full(len(js), np.nan, dtype="float32"))
        out = {f"{prefix}base": base}
        den = adr * base
        for k in HOR:
            out[f"{prefix}c{k}"] = int(b + k <= self.last)
            out[f"{prefix}ret{k}"] = (self.C[b + k, js] - base) / den if b + k <= self.last else np.full(len(js), np.nan)
        w0, w1 = b + 1, min(b + 60, self.last)
        if w1 >= w0:
            hi = self.H[w0:w1 + 1, js]
            cm = np.fmax.accumulate(hi, axis=0)
            out[f"{prefix}mfe60"] = (cm[-1] - base) / den
            for T in (5, 10):
                lvl = base * (1 + T * adr)
                reach = cm >= lvl[None, :]
                anyr = reach.any(axis=0)
                first = np.where(anyr, reach.argmax(axis=0) + 1, -1)
                out[f"{prefix}first{T}"] = first
            lo = np.fmin.accumulate(self.L[w0:w1 + 1, js], axis=0)
            out[f"{prefix}mae60"] = (lo[-1] - base) / den
        else:
            out[f"{prefix}mfe60"] = np.full(len(js), np.nan); out[f"{prefix}mae60"] = np.full(len(js), np.nan)
            out[f"{prefix}first5"] = np.full(len(js), -1); out[f"{prefix}first10"] = np.full(len(js), -1)
        out[f"{prefix}c60"] = int(b + 60 <= self.last)
        return out

    def measure_rows(self, t: np.ndarray, j: np.ndarray, adr: np.ndarray, variant: str, prefix: str) -> pd.DataFrame:
        """the same, for an entry table: rows grouped by their date index"""
        res = [None] * len(t)
        parts = []
        order = np.arange(len(t))
        df = pd.DataFrame({"t": t, "j": j, "adr": adr, "row": order})
        for e, g in df.groupby("t"):
            m = self.measure(int(e), g.j.to_numpy(), g.adr.to_numpy(float), variant, prefix)
            m["row"] = g.row.to_numpy()
            parts.append(pd.DataFrame(m))
        return pd.concat(parts).set_index("row").sort_index()

    def expansion_flags(self, t: np.ndarray, j: np.ndarray, adr_ref: np.ndarray, prefix: str) -> pd.DataFrame:
        """the three expansion tests on day t (ADR reference given per row = ADR20 the day before / at D)"""
        h, l, c, v = self.H[t, j], self.L[t, j], self.C[t, j], self.V[t, j]
        vol50 = self.VOL50[t - 1, j]
        rng_adr = (h - l) / c / adr_ref
        hl = h > l
        loc = np.where(hl, (c - l) / np.where(hl, h - l, 1.0), np.nan)
        volx = v / vol50
        return pd.DataFrame({f"{prefix}range_adr": rng_adr, f"{prefix}close_loc": loc, f"{prefix}vol_x": volx,
                             f"{prefix}range_ok": (rng_adr >= RANGE_X).astype(int), f"{prefix}loc_ok": (hl & (loc >= CLOSE_LOC)).astype(int),
                             f"{prefix}vol_ok": (np.isfinite(volx) & (volx >= VOL_X)).astype(int), f"{prefix}vol50_known": np.isfinite(vol50).astype(int),
                             f"{prefix}exp": (((rng_adr >= RANGE_X) & hl & (loc >= CLOSE_LOC) & np.isfinite(volx) & (volx >= VOL_X))).astype(int)})


def build(era, cfg):
    log(f"== {era}")
    data = cfg["data"]
    ex = load_export(f"{data}/daily_closes_all.csv.gz", cfg["cut"])
    cal = pd.Index(ex[ex.ticker == "SPY"].date.sort_values().values)
    ex = ex[ex.date.isin(cal)]
    tickers = pd.Index(sorted(ex.ticker.unique()))
    t0 = time.time()
    O, H, L, C, V = (wide(ex, c, cal, tickers) for c in ("o", "h", "l", "c", "v"))
    del ex
    F = Frame(O, H, L, C, V, cal)
    log(f"  calendar {len(cal)} sessions ({cal[0]}..{cal[-1]}); wide {F.C.shape}; {time.time()-t0:.0f}s")
    cidx = {d: i for i, d in enumerate(cal)}
    tpos = {tk: k for k, tk in enumerate(tickers)}
    last = F.last

    w = pd.read_csv(f"{data}/{cfg['watch']}", sep="\t", usecols=["ticker", "watch_date", "pivot_full", "pivot_tl", "pivot_k5", "pivot_k10", "adr20", "close", "pole_high", "base_low", "base_len"])
    watch_D = w.groupby("watch_date").ticker.apply(set).to_dict()

    # ── the fills (Question A, R3, and the K = tl row) ──────────────────────────────────────
    f = pd.read_csv(f"{data}/{cfg['fills']}", sep="\t", low_memory=False)
    f = f.merge(w.rename(columns={"adr20": "adr20_w", "close": "close_D"}), left_on=["ticker", "D"], right_on=["ticker", "watch_date"], how="left")
    assert f.pivot_full.notna().all()
    rel = (f.adr20_w - f.adr20).abs() / f.adr20
    log(f"  fills {len(f)}: watch adr20 vs table adr20 (6-digit text) max rel diff {rel.max():.1e} -> using the watch row's full-precision adr20")
    f["adr20"] = f.adr20_w.astype(float); f.drop(columns=["adr20_w", "watch_date"], inplace=True)
    f["tj"] = f.ticker.map(tpos).astype(int); f["ci"] = f.ci.astype(int)
    ci, tj = f.ci.to_numpy(), f.tj.to_numpy()
    assert np.allclose(F.C[ci, tj], f.c_E, rtol=1e-5), "E close mismatch vs yesterday"
    f["dist_adr"] = (f.pivot_full - f.fill) / (f.adr20 * f.fill)
    f["dist_tl_adr"] = (f.pivot_full - f.pivot_tl) / (f.adr20 * f.fill)
    # s_c: first session 0..60 from E whose CLOSE > pivot_full
    sc = np.full(len(f), -1, dtype=int)
    pf = f.pivot_full.to_numpy(np.float32)   # the bar frame is float32; a float64 pivot would read an exact tie as "above" (strict > needs the same precision)
    for i in range(len(f)):
        seg = F.C[ci[i]: min(ci[i] + 61, last + 1), tj[i]]
        hit = np.where(seg > pf[i])[0]
        if hit.size:
            sc[i] = int(hit[0])
    f["s_c"] = sc
    f["sc_complete"] = ((ci + 60) <= last).astype(int)
    f["r1_scan_complete"] = ((ci + R1_SCAN - 1) <= last).astype(int)
    # R3 flags on E (ADR20 at D, volume vs the 50 sessions ending D)
    f = pd.concat([f.reset_index(drop=True), F.expansion_flags(ci, tj, f.adr20.to_numpy(float), "e_")], axis=1)
    # close-based measures from E's close with ADR20_D (the control's base) — must reproduce yesterday's columns
    mc = F.measure_rows(ci, tj, f.adr20.to_numpy(float), "close", "cl_")
    f = pd.concat([f, mc.reset_index(drop=True)], axis=1)
    for k in (5, 20, 60):
        ok = f[f"cl_c{k}"] == 1
        d = (f.loc[ok, f"cl_ret{k}"] - f.loc[ok, f"ret{k}_adr_close"]).abs()
        log(f"  CHECK ret{k} from E close vs yesterday's ret{k}_adr_close: max abs diff {d.max():.2e} on {int(ok.sum())} rows")
    ok = f.cl_c60 == 1
    log(f"  CHECK mfe60 from E close vs yesterday's mfe60_adr_close: max abs diff {(f.loc[ok,'cl_mfe60'] - f.loc[ok,'mfe60_adr_close']).abs().max():.2e}; "
        f"complete_60 agree: {int((f.cl_c60 == f.complete_60).sum())} of {len(f)}")
    # s* from the FILL (yesterday's first_5adr) is kept for Question A; s* from the close is cl_first5
    assert not f.columns.duplicated().any(), "duplicate columns in the fills table"
    f.to_csv(f"{out_dir(era, data)}/bdef_fills_{era}.tsv.gz", sep="\t", index=False, float_format="%.7g")
    log(f"  wrote bdef_fills_{era}: {len(f)} rows; s_c found {int((sc >= 0).sum())}, none within 60 (complete) {int(((sc < 0) & (f.sc_complete == 1)).sum())}, "
        f"unknown (window cut) {int(((sc < 0) & (f.sc_complete == 0)).sum())}; s_c = 0 (E itself) {int((sc == 0).sum())}")
    log(f"  R3 on E: range ok {int(f.e_range_ok.sum())}, close-location ok {int(f.e_loc_ok.sum())}, volume ok {int(f.e_vol_ok.sum())} (vol50 known {int(f.e_vol50_known.sum())}); all three {int(f.e_exp.sum())}")

    # ── R1: the first close above the base high within sessions 0..59 from E ─────────────────
    r = f[(f.s_c >= 0) & (f.s_c < R1_SCAN)].drop(columns=[c for c in f.columns if c.startswith("cl_")]).copy()   # the fills' E-close measures
    r["t"] = r.ci + r.s_c                                                                                        # must NOT ride into the R1 table
    n0 = len(r)
    r = r.sort_values(["ticker", "t", "D"]).drop_duplicates(["ticker", "t"], keep="first")
    log(f"  R1: {n0} fills reach a close above the base high within sessions 0..{R1_SCAN-1}; one row per (ticker, day): {len(r)} (removed {n0 - len(r)})")
    t, j = r.t.to_numpy(), r.tj.to_numpy()
    r["adr_t1"] = F.ADR[t - 1, j]
    r["ret63_t1"] = F.RET63[t - 1, j]
    r["dv_t1"] = F.DV[t - 1, j]
    r["c_t"] = F.C[t, j]; r["o_t"] = F.O[t, j]; r["h_t"] = F.H[t, j]; r["l_t"] = F.L[t, j]
    r["o_next"] = np.where(t + 1 <= last, F.O[np.minimum(t + 1, last), j], np.nan)
    r["gap_next_adr"] = (r.o_next - r.c_t) / (r.adr_t1 * r.c_t)
    r["entry_date"] = cal[t]
    r["close_over_base_adr"] = (r.c_t - r.pivot_full) / (r.adr_t1 * r.c_t)
    r = pd.concat([r.reset_index(drop=True), F.expansion_flags(t, j, r.adr_t1.to_numpy(float), "r2_")], axis=1)
    if cfg["splits"]:
        sp = pd.read_csv(f"{data}/{cfg['splits']}", sep="|", header=None, names=["ticker", "date", "a", "b"], dtype=str)
        sp = sp[sp.ticker.isin(set(r.ticker))]
        spd = sp.groupby("ticker").date.apply(sorted).to_dict()
        flag = np.zeros(len(r), dtype=int)
        for i, (tk, ti) in enumerate(zip(r.ticker, t)):
            lo = cal[max(ti - VOL_N, 0)]; hi = cal[ti]
            if any(lo < d <= hi for d in spd.get(tk, [])):
                flag[i] = 1
        r["split_in_vol_window"] = flag
        log(f"  R1 rows with a split inside the 50-session volume window: {int(flag.sum())}")
    else:
        r["split_in_vol_window"] = -1
        log(f"  no splits file for this era: split_in_vol_window = -1 (unknown)")
    for variant, pre in (("close", "cl_"), ("nopen", "no_"), ("nclose", "nc_")):
        m = F.measure_rows(t, j, r.adr_t1.to_numpy(float), variant, pre)
        r = pd.concat([r, m.reset_index(drop=True)], axis=1)
    keep = [c for c in r.columns if not c.startswith(("mfe", "mae", "ret5_", "ret20_", "ret60_", "first_", "day0_", "complete_", "e_"))]
    assert not r[keep].columns.duplicated().any(), "duplicate columns in the R1 table"
    r[keep].to_csv(f"{out_dir(era, data)}/bdef_r1_{era}.tsv.gz", sep="\t", index=False, float_format="%.7g")
    log(f"  wrote bdef_r1_{era}: {len(r)} rows; R2 (all three) {int(r.r2_exp.sum())}; range ok {int(r.r2_range_ok.sum())}, loc ok {int(r.r2_loc_ok.sum())}, vol ok {int(r.r2_vol_ok.sum())}; "
        f"s_c = 0 share {100*(r.s_c==0).mean():.1f}%; median s_c {r.s_c.median():.0f}")

    # ── K variants from the entry tables ───────────────────────────────────────────────────────
    e = pd.read_csv(f"{data}/{cfg['entries']}", sep="\t", low_memory=False)
    kv = e[(e.variant == "orh5") & (e.status == "filled") & (e.C0 == 1) & (e.retrigger == 0)][["ticker", "D", "E", "K", "fill", "stop", "retrigger_chain"]].copy()
    kv = kv.merge(w[["ticker", "watch_date", "pivot_full", "adr20"]], left_on=["ticker", "D"], right_on=["ticker", "watch_date"], how="left").drop(columns="watch_date")
    assert kv.pivot_full.notna().all() and kv.adr20.notna().all()
    kv["ci"] = kv.E.map(cidx)
    n_out = int(kv.ci.isna().sum())
    kv = kv[kv.ci.notna()].copy(); kv["ci"] = kv.ci.astype(int)
    kv["tj"] = kv.ticker.map(tpos).astype(int)
    n0 = len(kv)
    kv = kv.sort_values(["K", "ticker", "E", "D"]).drop_duplicates(["K", "ticker", "E"])
    log(f"  K variants: {n0 + n_out} rows, {n_out} with E after the cut (dropped), dedup removed {n0 - len(kv)}; per K {kv.groupby('K').size().to_dict()}")
    kv["dist_adr"] = (kv.pivot_full - kv.fill) / (kv.adr20 * kv.fill)
    kv["c_E"] = F.C[kv.ci.to_numpy(), kv.tj.to_numpy()]
    kv["ret63_D"] = F.RET63[kv.ci.to_numpy() - 1, kv.tj.to_numpy()]
    kv["dv_D"] = F.DV[kv.ci.to_numpy() - 1, kv.tj.to_numpy()]
    inbar = (kv.fill >= F.L[kv.ci, kv.tj] * 0.99) & (kv.fill <= F.H[kv.ci, kv.tj] * 1.01)
    log(f"  CHECK K-variant fills inside E's daily bar (+-1%): {int(inbar.sum())} of {len(kv)}")
    m = F.measure_rows(kv.ci.to_numpy(), kv.tj.to_numpy(), kv.adr20.to_numpy(float), "close", "cl_")
    kv = pd.concat([kv.reset_index(drop=True), m.reset_index(drop=True)], axis=1)
    assert not kv.columns.duplicated().any(), "duplicate columns in the K table"
    kv.to_csv(f"{out_dir(era, data)}/bdef_kvar_{era}.tsv.gz", sep="\t", index=False, float_format="%.7g")
    log(f"  wrote bdef_kvar_{era}: {len(kv)} rows")

    # ── the control: the union of entry days ───────────────────────────────────────────────────
    entry_days = {}
    for name, df_, col in (("fills", f, "ci"), ("r1", r, "t"), ("kvar", kv, "ci")):
        for ti, tk in zip(df_[col].to_numpy(), df_.ticker):
            entry_days.setdefault(int(ti), set()).add(tk)
    days = sorted(entry_days)
    log(f"  control: {len(days)} entry days (fills {f.ci.nunique()}, R1 {r.t.nunique()}, K {kv.ci.nunique()})")
    tick_ok = np.array([bool(TICK_RE.match(tk)) for tk in tickers])
    rows = []; n_excl = 0
    t0 = time.time()
    for ti in days:
        d = ti - 1
        ok = tick_ok & (F.C[d] >= MIN_PRICE) & (F.DV[d] >= MIN_DV) & F.HIST[d] & np.isfinite(F.ADR[d]) & (F.ADR[d] > 0) & np.isfinite(F.C[ti])
        excl = entry_days[ti] | watch_D.get(cal[d], set())
        js = np.where(ok)[0]
        keep_j = np.array([tickers[x] not in excl for x in js], dtype=bool)
        n_excl += int((~keep_j).sum()); js = js[keep_j]
        a = F.ADR[d, js].astype(float)
        row = {"t": cal[ti], "ticker": tickers[js], "adr20": a, "ret63": F.RET63[d, js], "dv": F.DV[d, js]}
        for variant, pre in (("close", "cl_"), ("nopen", "no_"), ("nclose", "nc_")):
            row.update(F.measure(ti, js, a, variant, pre))
        rows.append(pd.DataFrame(row))
    ctl = pd.concat(rows, ignore_index=True)
    ctl.to_csv(f"{out_dir(era, data)}/bdef_control_{era}.tsv.gz", sep="\t", index=False, float_format="%.6g")
    log(f"  wrote bdef_control_{era}: {len(ctl):,} rows over {len(days)} days (mean {len(ctl)/len(days):.0f}); excluded as an entry / watch ticker {n_excl:,}; {time.time()-t0:.0f}s")
    # cross-check the control against yesterday's on the shared E dates (same rows, same numbers)
    yc = pd.read_csv(f"{data}/out/r_decomp_control_{era}.tsv.gz", sep="\t", usecols=["E", "ticker", "adr20", "ret20_adr_close", "mfe60_adr_close", "complete_60"])
    sub = ctl[ctl.t.isin(set(yc.E))][["t", "ticker", "adr20", "cl_ret20", "cl_mfe60", "cl_c60"]]
    jn = yc.merge(sub, left_on=["E", "ticker"], right_on=["t", "ticker"], how="outer", indicator=True)
    both = jn[jn._merge == "both"]
    log(f"  CHECK vs yesterday's control on its E dates: rows yesterday {len(yc):,}, mine on those dates {len(sub):,}, in both {len(both):,} "
        f"(only yesterday {int((jn._merge=='left_only').sum())}: tickers now excluded as an R1/K entry; only mine {int((jn._merge=='right_only').sum())}); "
        f"ret20 max abs diff {(both.ret20_adr_close - both.cl_ret20).abs().max():.1e}; mfe60 max abs diff {(both.mfe60_adr_close - both.cl_mfe60).abs().max():.1e}")


if __name__ == "__main__":
    eras = sys.argv[1:] or list(ERAS)
    assert (not (PRE_OUT or LOG_DIR != HERE)) or eras == ["2017-21"], "CB_PRE_OUT / CB_PRE_LOG re-run the 2017-21 era only"
    for era in eras:
        build(era, ERAS[era])
    with open(f"{LOG_DIR}/02_build_checks{'_' + '_'.join(eras) if len(eras) < len(ERAS) else ''}.txt", "w") as fh:
        fh.write("\n".join(checks) + "\n")
