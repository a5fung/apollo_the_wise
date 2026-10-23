#!/usr/bin/env python3
"""#705 big-winner recall, step 1: the big-winner EPISODES and their detector-independent breakout class, per era, under the
FROZEN definitions of docs/analysis/cb_big_winner_recall_2026-10-22.md §D (written before this ran).

Per era (2017-21 = cb702_pre, 2022-24 = cb702) and per factor (2.0 = the +100% set, 1.5 = the +50% set) writes
  DATA/out/wrecall_episodes_<era>_x<200|150>.tsv.gz   one row per episode: trough / peak / gain / s25 / s50 / universe & artifact
                                                      flags / EP-gap start / the measurable-breakout class under the primary rule and
                                                      every sensitivity variant / expansion-day flags on the breakout day
  HERE/01_episodes_<era>.txt                          the run log (counts of every exclusion)
HARD SCOPE: the cb702 export is cut at 2024-12-31 at load (asserted). Nothing under DATA is modified or deleted; the runner is never
imported; no network."""
from __future__ import annotations
import os, re, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence.consolidation_breakout import is_test_symbol as cb_is_test   # noqa: E402  (the frozen module; one helper)

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_winner_recall_1022"
ERAS = {
    "2017-21": dict(data="/Users/alvinfung/apollo_data/cb702_pre", cut=None, era_start="2017-03-01", era_end="2021-12-31",
                    guard="symbol_guard.tsv", splits=None, raw_close="daily_raw_close.csv.gz"),
    "2022-24": dict(data="/Users/alvinfung/apollo_data/cb702", cut="2024-12-31", era_start="2022-03-28", era_end="2024-12-31",
                    guard=None, splits="cb702_splits.psv", raw_close=None),
}
# optional re-run switches, 2017-21 only (#705 v2 re-run; all unset = unchanged): CB_PRE_DIR = the data dir, CB_PRE_OUT = where the tables are
# written (default DATA/out), CB_PRE_LOG = where the run log goes (default HERE)
PRE_OUT, LOG_DIR = os.environ.get("CB_PRE_OUT"), os.environ.get("CB_PRE_LOG", HERE)
if os.environ.get("CB_PRE_DIR"):
    ERAS["2017-21"]["data"] = os.environ["CB_PRE_DIR"]


def out_dir(era, data):
    return PRE_OUT if (era == "2017-21" and PRE_OUT) else f"{data}/out"


MIN_PRICE, MIN_DV, HIST = 5.0, 10_000_000.0, 130
TICK_RE = re.compile(r"^[A-Z]{1,5}$")
QWIN = 63                 # the qualifying window (t, t+63]
EXT_WIN, EXT_CAP = 20, 126
GAP_X, GAP_VOL_X, GAP_WIN = 1.10, 3.0, 5
ART_JUMP, ART_VOL_X = 1.5, 2.0
L_MIN, L_MAX = 10, 60
SPAN_PRIMARY, SIDEWAYS_ADR = 5.0, 2.0
RANGE_X, CLOSE_LOC, VOL_X, VOL_N = 1.0, 0.70, 1.5, 50
# the classifier variants: (name, span cap, adr unit, sideways rule on)
VARIANTS = [("p", 5.0, "adr60", True, "longest"), ("s4", 4.0, "adr60", True, "longest"), ("s7", 7.0, "adr60", True, "longest"), ("a20", 5.0, "adr20", True, "longest"),
            ("nosw", 5.0, "adr60", False, "longest"),
            # ADDED AFTER THE FIRST BUILD (post hoc, labelled so in the doc): the SHORTEST qualifying window — the tight pocket right
            # before the break — because the frozen longest-window rule reads a recovery out of a deep base as "late_base"
            ("shortL", 5.0, "adr60", True, "shortest")]
log_lines: list[str] = []


def log(s):
    print(s, flush=True); log_lines.append(s)


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


def raw_close_wide(data, cfg, Cw, cal, tickers, log):
    """RAW close per (session, ticker) — the setup's price floor is on the RAW close (`universe_ok`), not the adjusted one.
    2017-21: the export's own daily_raw_close.csv.gz; 2022-24: adjusted x the product of the ratios of splits executing AFTER the
    session (`cb.raw_factor_for`'s rule) from cb702_splits.psv, splits executing after the export's last session dropped."""
    if cfg.get("raw_close"):
        r = pd.read_csv(f"{data}/{cfg['raw_close']}", header=None, names=["ticker", "date", "raw"], dtype={"ticker": str, "date": str, "raw": "float32"}, keep_default_na=False)
        R = r.pivot(index="date", columns="ticker", values="raw").reindex(index=cal, columns=tickers).astype("float32").to_numpy()
        log(f"  raw close from {cfg['raw_close']}: {np.isfinite(R).sum():,} cells")
        return R
    sp = pd.read_csv(f"{data}/{cfg['splits']}", sep="|", header=None, names=["ticker", "date", "a", "b"], dtype=str).drop_duplicates()
    sp = sp[sp.date <= cal[-1]]
    F = np.ones(Cw.shape, dtype="float64")
    tpos = {tk: k for k, tk in enumerate(tickers)}
    n_sp = 0
    for tk, g in sp.groupby("ticker"):
        if tk not in tpos:
            continue
        j = tpos[tk]
        for d, a, b in zip(g.date, g.a, g.b):
            ratio = float(b) / float(a) if float(a) > 0 else 1.0        # the runner's load_splits: f[3] / f[2] (NVDA|2024-06-10|1|10 -> 10)
            if ratio <= 0:
                continue
            F[cal < d, j] *= ratio; n_sp += 1
    log(f"  raw close = adjusted x split factor from {cfg['splits']}: {n_sp} splits applied on {sp.ticker.nunique()} tickers")
    return (Cw.to_numpy().astype("float64") * F).astype("float32")


def load_sectypes(data):
    """the runner's `resolve_sectype`: small_pulls.psv `sectype|TICKER|TYPE|exch` first, then cb702_sic.psv's type, else unknown (admitted)"""
    mi = {}
    for line in open(f"{data}/small_pulls.psv"):
        f = line.rstrip("\n").split("|")
        if f[0] == "sectype" and len(f) >= 3:
            mi[f[1]] = f[2]
    sic = pd.read_csv(f"{data}/cb702_sic.psv", sep="|", header=None, dtype=str, keep_default_na=False)
    sic_t = dict(zip(sic[0], sic[5]))
    return lambda tk: mi.get(tk) or sic_t.get(tk) or ""


def fwd_max(C: np.ndarray, w: int) -> np.ndarray:
    """fwd[t] = max C over (t, t+w] (NaN-skipping); NaN where no bar."""
    s = pd.Series(C[::-1])
    r = s.rolling(w, min_periods=1).max().to_numpy()[::-1]     # max over [t, t+w-1]
    out = np.full(len(C), np.nan)
    out[:-1] = r[1:]
    return out


def base_for(H, L, C, b, adr_unit, span_cap, sideways, pick="longest"):
    """the LONGEST L in [L_MIN, L_MAX] whose window [b-L, b-1] is contained (and sideways); (L, base_high, base_low) or None"""
    u = adr_unit * C[b - 1]
    if not np.isfinite(u) or u <= 0 or b < L_MIN:
        return None
    a0 = max(b - L_MAX, 0)
    hh, ll, cc = H[a0:b][::-1], L[a0:b][::-1], C[a0:b][::-1]          # index k = window length k+1 (sessions b-1 .. b-1-k)
    fin = np.isfinite(hh) & np.isfinite(ll) & np.isfinite(cc)
    finall = np.cumprod(fin.astype(np.int8)).astype(bool)             # all finite within the window
    hmax = np.fmax.accumulate(np.where(fin, hh, -np.inf))
    lmin = np.fmin.accumulate(np.where(fin, ll, np.inf))
    Ls = np.arange(1, len(hh) + 1)
    ok = finall & (Ls >= L_MIN) & ((hmax - lmin) <= span_cap * u)
    if sideways:
        last5 = cc[:5].mean()                                          # the last 5 sessions of every window (b-5 .. b-1)
        # first 5 of a window of length Lw = sessions b-Lw .. b-Lw+4 = reversed index Lw-1 .. Lw-5
        cs = np.concatenate([[0.0], np.cumsum(np.where(fin, cc, 0.0))])
        first5 = np.full(len(hh), np.nan)
        idx = np.arange(5, len(hh) + 1)                                # Lw >= 5
        first5[idx - 1] = (cs[idx] - cs[idx - 5]) / 5.0
        ok &= np.isfinite(first5) & (np.abs(first5 - last5) <= SIDEWAYS_ADR * u)
    if not ok.any():
        return None
    k = int(np.where(ok)[0][-1]) if pick == "longest" else int(np.where(ok)[0][0])   # the LONGEST (or shortest) qualifying window
    return k + 1, float(hmax[k]), float(lmin[k])


def classify(H, L, C, ADRU, t, p, s25, span_cap, sideways, pick="longest"):
    """scan b in (t, p]: the first base breakout; returns dict(class, b, L, base_high, base_low, any_base_before_s25)"""
    first_bo = None; any_base_pre = 0; any_base = 0
    for b in range(t + 1, p + 1):
        bs = base_for(H, L, C, b, ADRU[b - 1], span_cap, sideways, pick)
        if bs is None:
            continue
        any_base = 1
        if b <= s25:
            any_base_pre = 1
        if np.float32(C[b]) > np.float32(bs[1]):
            first_bo = (b, bs)
            break
    if first_bo is not None:
        b, (Lw, bh, bl) = first_bo
        cls = "measurable_breakout" if b <= s25 else "late_base"
        return dict(cls=cls, b=b, L=Lw, base_high=bh, base_low=bl, any_base_pre_s25=any_base_pre)
    if any_base:
        return dict(cls="other", b=-1, L=-1, base_high=np.nan, base_low=np.nan, any_base_pre_s25=any_base_pre)
    return dict(cls="no_consolidation", b=-1, L=-1, base_high=np.nan, base_low=np.nan, any_base_pre_s25=0)


def build(era, cfg):
    data = cfg["data"]
    ex = load_export(f"{data}/daily_closes_all.csv.gz", cfg["cut"])
    cal = pd.Index(ex[ex.ticker == "SPY"].date.sort_values().values)
    ex = ex[ex.date.isin(cal)]
    tickers = pd.Index(sorted(ex.ticker.unique()))
    O, Hw, Lw_, Cw, Vw = (wide(ex, c, cal, tickers) for c in ("o", "h", "l", "c", "v"))
    del ex
    n = len(cal); last = n - 1
    log(f"  calendar {n} sessions ({cal[0]}..{cal[-1]}); wide {Cw.shape}")
    ADR20 = ((Hw - Lw_) / Cw).rolling(20, min_periods=20).mean().to_numpy()
    ADR60 = ((Hw - Lw_) / Cw).rolling(60, min_periods=60).mean().to_numpy()
    DV = (Cw * Vw).rolling(20, min_periods=20).median().to_numpy()
    HISTok = (Cw.notna().astype("float32").rolling(HIST, min_periods=HIST).sum() == HIST).to_numpy()
    V20 = Vw.rolling(20, min_periods=20).mean().to_numpy()
    V50 = Vw.rolling(VOL_N, min_periods=VOL_N).mean().to_numpy()
    O, H, L, C, V = (x.to_numpy() for x in (O, Hw, Lw_, Cw, Vw))
    ei0, ei1 = int(np.searchsorted(cal, cfg["era_start"])), int(np.searchsorted(cal, cfg["era_end"], side="right")) - 1
    log(f"  era trough window {cal[ei0]}..{cal[ei1]} (idx {ei0}..{ei1})")
    tick_ok = np.array([bool(TICK_RE.match(tk)) for tk in tickers])
    # identity breaks (2017-21) / splits (2022-24)
    breaks = {}
    if cfg["guard"]:
        g = pd.read_csv(f"{data}/{cfg['guard']}", sep="\t", dtype=str, keep_default_na=False)
        for tk, br in zip(g.symbol, g.breaks):
            if br:
                breaks[tk] = sorted({x.split(":")[0] for x in br.split(";") if x})
        log(f"  symbol_guard: {len(breaks)} tickers with an identity break")
    splits = {}
    if cfg["splits"]:
        sp = pd.read_csv(f"{data}/{cfg['splits']}", sep="|", header=None, names=["ticker", "date", "a", "b"], dtype=str)
        for tk, d in zip(sp.ticker, sp.date):
            splits.setdefault(tk, []).append(d)
        log(f"  splits file: {len(splits)} tickers")
    sectype_of = load_sectypes(data)
    RAW = raw_close_wide(data, cfg, Cw, cal, tickers, log)
    type_ok = np.array([(sectype_of(tk) in ("", "CS", "ADRC")) and not cb_is_test(tk) for tk in tickers])
    log(f"  tickers: {len(tickers)}; ticker regex ok {int(tick_ok.sum())}; security type CS/ADRC/unknown and not a test symbol {int((tick_ok & type_ok).sum())}")

    for factor, tag in ((2.0, "x200"), (1.5, "x150")):
        t0 = time.time()
        rows = []; cnt = dict(cand_tickers=0, qualifying_sessions=0, episodes=0, window_cut=0, artifact_jump=0, identity_break=0,
                              split_flag=0, extended=0, ext_truncated=0, trough_moved=0, lower_close_univ_fail=0, lower_close_pre10=0,
                              sectype_unknown=0)
        for j, tk in enumerate(tickers):
            if not (tick_ok[j] and type_ok[j]):
                continue
            c = C[:, j]
            if np.isfinite(c).sum() < HIST:
                continue
            fm = fwd_max(c, QWIN)
            univ = (RAW[:, j] >= MIN_PRICE) & (DV[:, j] >= MIN_DV) & HISTok[:, j]        # RAW close floor (the setup's), adjusted-$ volume
            qual = univ & np.isfinite(fm) & (fm >= factor * c)
            qual[: ei0] = False; qual[ei1 + 1:] = False
            if not qual.any():
                continue
            cnt["cand_tickers"] += 1; cnt["qualifying_sessions"] += int(qual.sum())
            start = ei0
            while True:
                q = np.where(qual[start:])[0]
                if q.size == 0:
                    break
                t = start + int(q[0])
                if t + QWIN > last:
                    cnt["window_cut"] += 1
                    break                                        # every later candidate is cut too
                seg = c[t + 1: t + QWIN + 1]
                p = t + 1 + int(np.nanargmax(seg))
                moved = 0
                for _ in range(10):                              # anchor the trough on the lowest close before the peak
                    m = t + int(np.nanargmin(c[t: p + 1]))
                    if m == t:
                        break
                    if qual[m]:
                        t = m; moved = 1
                        seg = c[t + 1: t + QWIN + 1]
                        p = t + 1 + int(np.nanargmax(seg))
                    else:
                        cnt["lower_close_univ_fail"] += 1
                        break
                cnt["trough_moved"] += moved
                # peak extension: a higher close within the next 20 sessions, cap t+126
                ext = 0; trunc = 0
                while True:
                    hi = min(p + EXT_WIN, t + EXT_CAP, last)
                    if hi <= p:
                        trunc = int(min(p + EXT_WIN, t + EXT_CAP) > last); break
                    seg2 = c[p + 1: hi + 1]
                    if np.isfinite(seg2).any() and np.nanmax(seg2) > c[p]:
                        p = p + 1 + int(np.nanargmax(seg2)); ext = 1
                    else:
                        trunc = int(min(p + EXT_WIN, t + EXT_CAP) > last); break
                cnt["extended"] += ext; cnt["ext_truncated"] += trunc
                gain = float(c[p] / c[t] - 1.0)
                run = c[t + 1: p + 1]
                s25 = t + 1 + int(np.argmax(run >= c[t] * (1 + 0.25 * gain)))
                s50 = t + 1 + int(np.argmax(run >= c[t] * (1 + 0.50 * gain)))
                # artifact: a >= +50% one-session close jump on < 2x the prior 20-session mean volume inside [t-60, p]
                a0 = max(t - 60, 1)
                cr = c[a0: p + 1] / c[a0 - 1: p]
                vr = V[a0: p + 1, j] / V20[a0 - 1: p, j]
                art = int(np.any(np.isfinite(cr) & (cr >= ART_JUMP) & np.isfinite(vr) & (vr < ART_VOL_X)))
                brk = int(any(cal[a0] <= d <= cal[p] for d in breaks.get(tk, [])))
                spl = int(any(cal[a0] <= d <= cal[p] for d in splits.get(tk, [])))
                cnt["artifact_jump"] += art; cnt["identity_break"] += brk; cnt["split_flag"] += spl
                st = sectype_of(tk)
                if st == "":
                    cnt["sectype_unknown"] += 1
                # EP-gap start in (t, t+5]
                gap_day = -1; gap_pct = np.nan; gap_volx = np.nan
                for g in range(t + 1, min(t + GAP_WIN, last) + 1):
                    if np.isfinite(O[g, j]) and np.isfinite(c[g - 1]) and np.isfinite(V50[g - 1, j]) and V50[g - 1, j] > 0:
                        gp = O[g, j] / c[g - 1]; vx = V[g, j] / V50[g - 1, j]
                        if gp >= GAP_X and vx >= GAP_VOL_X:
                            gap_day, gap_pct, gap_volx = g, float(gp - 1), float(vx); break
                lower_pre10 = int(np.nanmin(c[max(t - 10, 0): t]) < c[t]) if t > 0 and np.isfinite(c[max(t - 10, 0): t]).any() else 0
                cnt["lower_close_pre10"] += lower_pre10
                row = dict(ticker=tk, era=era, factor=factor, t=t, trough_date=cal[t], p=p, peak_date=cal[p], sessions_t_to_p=p - t,
                           close_t=float(c[t]), close_p=float(c[p]), gain=gain, s25=s25, s25_date=cal[s25], s50=s50, s50_date=cal[s50],
                           adr20_t=float(ADR20[t, j]), adr60_t=float(ADR60[t, j]), dv_t=float(DV[t, j]), ret63_t=float(c[t] / c[t - 63] - 1) if t >= 63 and np.isfinite(c[t - 63]) else np.nan,
                           trough_moved=moved, extended=ext, ext_truncated=trunc, artifact_jump=art, identity_break=brk, split_flag=spl,
                           sectype=st, raw_close_t=float(RAW[t, j]), lower_close_pre10=lower_pre10, gap_day=gap_day, gap_date=cal[gap_day] if gap_day >= 0 else "",
                           gap_pct=gap_pct, gap_volx=gap_volx, gap_day_minus_t=(gap_day - t) if gap_day >= 0 else -1)
                for name, cap, unit, sw, pick in VARIANTS:
                    ADRU = ADR60[:, j] if unit == "adr60" else ADR20[:, j]
                    r = classify(H[:, j], L[:, j], c, ADRU, t, p, s25, cap, sw, pick)
                    b = r["b"]
                    cls = r["cls"]
                    if gap_day >= 0 and (b < 0 or b >= gap_day):
                        cls = "ep_gap"
                    row[f"class_{name}"] = cls; row[f"b_{name}"] = b; row[f"L_{name}"] = r["L"]
                    row[f"base_high_{name}"] = r["base_high"]; row[f"base_low_{name}"] = r["base_low"]; row[f"any_base_pre_s25_{name}"] = r["any_base_pre_s25"]
                    row[f"bo_and_gap_{name}"] = int(gap_day >= 0 and b >= 0)
                    if name == "p" and b >= 0:
                        a = b - r["L"]
                        row["b_date"] = cal[b]; row["b_minus_t"] = b - t; row["base_start_date"] = cal[a]
                        row["base_contains_trough"] = int(a <= t <= b - 1)
                        row["gain_made_at_b_prev"] = float((c[b - 1] - c[t]) / (c[p] - c[t]))
                        row["gain_made_at_b_close"] = float((c[b] - c[t]) / (c[p] - c[t]))
                        row["span_adr60"] = float((r["base_high"] - r["base_low"]) / (ADR60[b - 1, j] * c[b - 1]))
                        row["span_adr20"] = float((r["base_high"] - r["base_low"]) / (ADR20[b - 1, j] * c[b - 1]))
                        row["base_depth_pct"] = float(1 - r["base_low"] / r["base_high"])
                        row["adr20_bprev"] = float(ADR20[b - 1, j]); row["adr60_bprev"] = float(ADR60[b - 1, j])
                        hb, lb, cb, vb = H[b, j], L[b, j], c[b], V[b, j]
                        rng = (hb - lb) / cb / ADR20[b - 1, j]
                        loc = (cb - lb) / (hb - lb) if hb > lb else np.nan
                        vx = vb / V50[b - 1, j] if np.isfinite(V50[b - 1, j]) and V50[b - 1, j] > 0 else np.nan
                        row["bo_range_adr"] = float(rng); row["bo_close_loc"] = float(loc) if np.isfinite(loc) else np.nan; row["bo_vol_x"] = float(vx) if np.isfinite(vx) else np.nan
                        row["bo_expansion"] = int(np.isfinite(rng) and rng >= RANGE_X and np.isfinite(loc) and loc >= CLOSE_LOC and np.isfinite(vx) and vx >= VOL_X)
                        row["bo_close_over_high_adr"] = float((cb - r["base_high"]) / (ADR20[b - 1, j] * cb))
                        row["bo_gap_open_pct"] = float(O[b, j] / c[b - 1] - 1)
                rows.append(row); cnt["episodes"] += 1
                start = p + 1
        df = pd.DataFrame(rows)
        for col in ("b_date", "base_start_date"):
            if col in df: df[col] = df[col].fillna("")
        df["excluded"] = ((df.artifact_jump == 1) | (df.identity_break == 1)).astype(int)
        out = f"{out_dir(era, data)}/wrecall_episodes_{era}_{tag}.tsv.gz"
        df.to_csv(out, sep="\t", index=False, float_format="%.7g")
        kept = df[df.excluded == 0]
        log(f"  [{tag}] {cnt}; wrote {out}: {len(df)} episodes, excluded {int(df.excluded.sum())}, kept {len(kept)}; "
            f"classes (primary, kept): {kept.class_p.value_counts().to_dict()}; {time.time()-t0:.0f}s")


if __name__ == "__main__":
    eras = sys.argv[1:] or list(ERAS)
    assert (not (PRE_OUT or LOG_DIR != HERE)) or eras == ["2017-21"], "CB_PRE_OUT / CB_PRE_LOG re-run the 2017-21 era only"
    for era in eras:
        log(f"== {era}")
        build(era, ERAS[era])
        with open(f"{LOG_DIR}/01_episodes_{era}.txt", "w") as fh:
            fh.write("\n".join(log_lines) + "\n")
        log_lines.clear()
