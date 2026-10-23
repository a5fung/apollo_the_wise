"""#705 entry × stop × retry grid under his carried `pp` exit — the shared pieces, vectorised in lockstep across trades.

Everything here follows docs/analysis/cb_entry_stop_retry_2026-10-22.md §D (frozen before this ran). Daily bars only. The walker is a
lockstep (session-by-session, all trades at once) implementation of the runner's `exitpb_walk` order — gap third, the stop in force
before the session, the +2R leg, the reach / stall cut, the session-3 leg (profit only), the trail (live after a third or from
session 3) filled at the next open, the 120-session mark. HARD SCOPE: the cb702 export is cut at 2024-12-31 at load (asserted);
nothing past the last readable session is ever read (the mark uses the last readable close)."""
from __future__ import annotations
import os, re, time
import numpy as np, pandas as pd

HORIZON = 120
RACE_H = 60
PARTIAL_R, PARTIAL_FRAC, STALL_R, STALL_SESSION, SMA_N = 2.0, 1.0 / 3.0, 1.0, 3, 20
RETRY_WINDOW = 20
PROXY_N = 20                      # the control's "base": the 20 sessions before t
STOPS = ("S1", "S2", "S3", "S4")
STOP_ADR = {"S2": 1.0, "S3": 1.5}
STATUS = {0: "open", 1: "stopped", 2: "time_exit", 3: "trailed", 4: "censored", 5: "degraded"}
TICK_RE = re.compile(r"^[A-Z]{1,5}$")

ERAS = {
    "2017-21": dict(data="/Users/alvinfung/apollo_data/cb702_pre", cut=None, watch_lo="2017-03-01", watch_hi="2021-12-31",
                    trades="out/trades_pre_exitpb.tsv.gz"),
    "2022-24": dict(data="/Users/alvinfung/apollo_data/cb702", cut="2024-12-31", watch_lo="2022-03-28", watch_hi="2024-12-31",
                    trades="out/trades_discovery_exitpb.tsv.gz"),
}

# optional re-run switches, 2017-21 only (#705 v2 re-run; all unset = unchanged): CB_PRE_DIR = the data dir, CB_PRE_OUT = where the generated tables
# (esr_* written here; wrecall_* / bdef_* read here) live (default DATA/out), CB_PRE_LOG = where the logs / numbers / sample files go (default this dir)
HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_entry_stop_retry_1022"
PRE_OUT, LOG_DIR = os.environ.get("CB_PRE_OUT"), os.environ.get("CB_PRE_LOG", HERE)
if os.environ.get("CB_PRE_DIR"):
    ERAS["2017-21"]["data"] = os.environ["CB_PRE_DIR"]


def out_dir(era, data):
    return PRE_OUT if (era == "2017-21" and PRE_OUT) else f"{data}/out"


def log(s, sink: list | None = None):
    print(s, flush=True)
    if sink is not None:
        sink.append(s)


class Frame:
    """wide float32 arrays on SPY's calendar; ADR20 / SMA20 / the 20-session prior high and low; a forward-filled close for marks."""

    def __init__(self, data: str, cut: str | None, sink=None):
        t0 = time.time()
        df = pd.read_csv(f"{data}/daily_closes_all.csv.gz", header=None, names=["ticker", "date", "o", "h", "l", "c", "v"],
                         dtype={"ticker": str, "date": str, "o": "float32", "h": "float32", "l": "float32", "c": "float32", "v": "float64"},
                         keep_default_na=False)
        n0 = len(df)
        if cut:
            df = df[df.date <= cut]
            assert df.date.max() <= cut, df.date.max()
        cal = pd.Index(df[df.ticker == "SPY"].date.sort_values().values)
        df = df[df.date.isin(cal)]
        tickers = pd.Index(sorted(df.ticker.unique()))
        log(f"  export: {n0:,} rows, kept {len(df):,} (cut {cut}); {cal[0]}..{cal[-1]} = {len(cal)} sessions; {len(tickers):,} tickers; {time.time()-t0:.0f}s", sink)
        W = {}
        for col in ("o", "h", "l", "c", "v"):
            W[col] = df.pivot(index="date", columns="ticker", values=col).reindex(index=cal, columns=tickers).astype("float32")
        del df
        self.cal, self.tickers = cal, tickers
        self.cidx = {d: i for i, d in enumerate(cal)}
        self.tpos = {t: k for k, t in enumerate(tickers)}
        self.last = len(cal) - 1
        self.O, self.H, self.L, self.C, self.V = (W[c].to_numpy() for c in ("o", "h", "l", "c", "v"))
        Cw = W["c"]
        self.ADR = ((W["h"] - W["l"]) / Cw).rolling(20, min_periods=20).mean().to_numpy().astype("float32")
        self.SMA = Cw.rolling(SMA_N, min_periods=SMA_N).mean().to_numpy().astype("float32")
        self.PHI = W["h"].shift(1).rolling(PROXY_N, min_periods=PROXY_N).max().to_numpy().astype("float32")   # highest high over [t-20, t-1]
        self.PLO = W["l"].shift(1).rolling(PROXY_N, min_periods=PROXY_N).min().to_numpy().astype("float32")   # lowest low over [t-20, t-1]
        self.CF = Cw.ffill().to_numpy().astype("float32")                                                      # the last readable close at or before a session
        self.DV = (Cw * W["v"]).rolling(20, min_periods=20).median().to_numpy()
        self.HIST = (Cw.notna().astype("float32").rolling(130, min_periods=130).sum() == 130).to_numpy()
        self.RET63 = (Cw / Cw.shift(63) - 1.0).to_numpy()
        log(f"  wide {self.C.shape}; frame built {time.time()-t0:.0f}s", sink)

    def bar(self, A, idx, tj):
        """A[idx, tj] with NaN where idx is past the last session"""
        out = np.full(len(idx), np.nan, dtype="float32")
        ok = idx <= self.last
        out[ok] = A[idx[ok], tj[ok]]
        return out


def stop_levels(F: Frame, kind: str, fill, bday, tj, base_lo):
    """the stop for a trade entered off breakout day `bday` (index) at `fill`: S1 the breakout day's low; S2/S3 fill − k × ADR20(bday − 1) × fill;
    S4 the base low (passed in; the control's proxy)."""
    if kind == "S1":
        return F.L[bday, tj]
    if kind in STOP_ADR:
        adr = F.ADR[bday - 1, tj]
        return (fill * (1.0 - STOP_ADR[kind] * adr)).astype("float32")
    if kind == "S4":
        return np.asarray(base_lo, dtype="float32")
    raise ValueError(kind)


def walk(F: Frame, e: np.ndarray, tj: np.ndarray, fill: np.ndarray, stop0: np.ndarray, start_j: int, reached0: np.ndarray | None = None) -> dict:
    """Lockstep `pp` walk. e = session-0 index per trade; start_j = 1 (entry at the close of session 0) or 0 (entry at session 0's open).
    Returns per-trade arrays: status code, exit_j (sessions from e), exit_idx, pnl per share, realized R (vs stop0), partial kind
    (0 none / 1 gap-open +2R / 2 +2R at target / 3 session-3 close), partial_j, stopped_at_be (the stop that fired was the breakeven stop),
    hole (a NaN session inside the walk)."""
    N = len(e)
    fill = fill.astype("float64"); stop0 = stop0.astype("float64")
    risk = fill - stop0
    assert (risk > 0).all(), "walk: every trade needs stop < fill"
    target = fill + PARTIAL_R * risk
    cut_lvl = fill + STALL_R * risk
    stop_now = stop0.copy()
    partial = np.zeros(N, bool); remaining = np.ones(N); pnl = np.zeros(N); reached = np.zeros(N, bool) if reached0 is None else reached0.astype(bool).copy()
    active = np.ones(N, bool)
    status = np.zeros(N, np.int8); exit_j = np.full(N, -1, np.int32); exit_idx = np.full(N, -1, np.int32)
    pkind = np.zeros(N, np.int8); pj = np.full(N, -1, np.int32); be_stop = np.zeros(N, bool); hole = np.zeros(N, bool)
    at_cut = np.zeros(N, bool)
    frac = PARTIAL_FRAC
    for j in range(start_j, HORIZON + 1):
        if not active.any():
            break
        idx = e + j
        past = active & (idx > F.last)                       # bars ran out: mark at the last readable close (degraded)
        if past.any():
            px = F.CF[F.last, tj[past]].astype("float64")
            pnl[past] += (px - fill[past]) * remaining[past]
            status[past] = 5; exit_j[past] = j - 1; exit_idx[past] = F.last; active[past] = False
        a = np.where(active)[0]
        if a.size == 0:
            break
        ia, ta = idx[a], tj[a]
        o = F.O[ia, ta].astype("float64"); h = F.H[ia, ta].astype("float64"); l = F.L[ia, ta].astype("float64"); c = F.C[ia, ta].astype("float64")
        nan = ~np.isfinite(c)
        if nan.any():
            hole[a[nan]] = True
            if j == HORIZON:                                 # mark at the last readable close
                sel = a[nan]
                px = F.CF[ia[nan], ta[nan]].astype("float64")
                pnl[sel] += (px - fill[sel]) * remaining[sel]
                status[sel] = 4; exit_j[sel] = j; exit_idx[sel] = ia[nan]; active[sel] = False
            keep = ~nan
            a, ia, ta, o, h, l, c = a[keep], ia[keep], ta[keep], o[keep], h[keep], l[keep], c[keep]
        sn = stop_now[a]; fa = fill[a]; tg = target[a]; cl = cut_lvl[a]; pa = partial[a]
        # (0) a gap open at/above the target with no third yet -> the third at the open
        gap = (~pa) & (o >= tg)
        # (1) the stop in force before this session
        st = (o <= sn) | (l <= sn)
        if st.any():
            s = a[st]
            g = gap[st]
            if g.any():
                sg = s[g]
                pnl[sg] += (o[st][g] - fill[sg]) * frac; remaining[sg] -= frac; partial[sg] = True; pkind[sg] = 1; pj[sg] = j
            px = np.where(o[st] <= sn[st], o[st], sn[st])
            pnl[s] += (px - fill[s]) * remaining[s]
            be_stop[s] = sn[st] > stop0[s] + 1e-12                 # the stop that fired was the raised (breakeven) stop, not the original
            status[s] = 1; exit_j[s] = j; exit_idx[s] = ia[st]; active[s] = False
        live = ~st
        a2, o2, h2, c2, fa2, tg2, cl2, pa2, gap2 = a[live], o[live], h[live], c[live], fa[live], tg[live], cl[live], pa[live], gap[live]
        # (1b) the +2R leg
        hit = gap2 | ((~pa2) & (h2 >= tg2))
        if hit.any():
            s = a2[hit]
            px = np.where(gap2[hit], o2[hit], tg2[hit])
            pnl[s] += (px - fill[s]) * frac; remaining[s] -= frac; partial[s] = True
            pkind[s] = np.where(gap2[hit], 1, 2); pj[s] = j
            stop_now[s] = np.maximum(stop_now[s], fill[s])    # resting from the NEXT session (this session's stop test already ran)
        # (1c) the reach test (sessions start_j..3), then the cut at session 3's close
        if j <= STALL_SESSION:
            r = h2 >= cl2
            reached[a2[r]] = True
            if j == STALL_SESSION:
                cutm = ~reached[a2]
                if cutm.any():
                    s = a2[cutm]
                    pnl[s] += (c2[cutm] - fill[s]) * remaining[s]
                    status[s] = 2; exit_j[s] = j; exit_idx[s] = ia[live][cutm]; active[s] = False; at_cut[s] = True
                keep = ~cutm
                a2, o2, h2, c2, fa2, pa2 = a2[keep], o2[keep], h2[keep], c2[keep], fa2[keep], pa2[keep]
        # (2) the session leg at session 3's close, only in profit, only with no third yet
        if j == STALL_SESSION and a2.size:
            pa2 = partial[a2]
            leg = (~pa2) & (c2 > fa2)
            if leg.any():
                s = a2[leg]
                pnl[s] += (c2[leg] - fill[s]) * frac; remaining[s] -= frac; partial[s] = True; pkind[s] = 3; pj[s] = j
                stop_now[s] = np.maximum(stop_now[s], fill[s])
        # (3) the trail: live once a third has sold or from session 3; a close under the SMA20 sells the rest at the NEXT open
        if a2.size:
            tl = partial[a2] | (j >= STALL_SESSION)
            if tl.any():
                s = a2[tl]; ii = idx[s]; tt = tj[s]
                sma = F.SMA[ii, tt].astype("float64")
                sig = np.isfinite(sma) & (c2[tl] < sma)
                if sig.any():
                    s = s[sig]; ii = ii[sig]; tt = tt[sig]
                    nxt = ii + 1
                    has = nxt <= F.last
                    opx = np.full(len(s), np.nan)
                    opx[has] = F.O[nxt[has], tt[has]]
                    okn = np.isfinite(opx)
                    if okn.any():
                        ss = s[okn]
                        pnl[ss] += (opx[okn] - fill[ss]) * remaining[ss]
                        status[ss] = 4 if j == HORIZON else 3; exit_j[ss] = j + 1; exit_idx[ss] = nxt[okn]; active[ss] = False
                    if (~okn).any():                          # no next open readable: mark at the signal close (degraded)
                        ss = s[~okn]
                        pnl[ss] += (c2[tl][sig][~okn] - fill[ss]) * remaining[ss]
                        status[ss] = 5; exit_j[ss] = j; exit_idx[ss] = ii[~okn]; active[ss] = False
        # (4) the horizon
        if j == HORIZON:
            s = np.where(active)[0]
            if s.size:
                px = F.C[idx[s], tj[s]].astype("float64")
                bad = ~np.isfinite(px)
                if bad.any():
                    px[bad] = F.CF[idx[s][bad], tj[s][bad]]
                pnl[s] += (px - fill[s]) * remaining[s]
                status[s] = 4; exit_j[s] = j; exit_idx[s] = idx[s]; active[s] = False
    assert not active.any()
    return dict(status=status, exit_j=exit_j, exit_idx=exit_idx, pnl_ps=pnl, realized_r=pnl / risk, pkind=pkind, pj=pj,
                be_stop=be_stop, hole=hole, at_cut=at_cut)


def race(F: Frame, e: np.ndarray, tj: np.ndarray, fill: np.ndarray, stop0: np.ndarray, start_j: int, ks=(2, 5, 10)) -> dict:
    """the 01_race convention from the entry: sessions start_j..start_j+59, first low <= stop vs first high >= fill + kR, a tie -> the stop,
    neither -> marked at the last session's close in R. Needs the whole window readable (complete flag)."""
    N = len(e)
    fill = fill.astype("float64"); stop0 = stop0.astype("float64"); risk = fill - stop0
    first_stop = np.full(N, 999, np.int32)
    first_hit = {k: np.full(N, 999, np.int32) for k in ks}
    endj = start_j + RACE_H - 1
    complete = (e + endj) <= F.last
    for j in range(start_j, endj + 1):
        idx = e + j
        l = F.bar(F.L, idx, tj).astype("float64"); h = F.bar(F.H, idx, tj).astype("float64")
        m = (l <= stop0) & (first_stop == 999) & np.isfinite(l)
        first_stop[m] = j
        for k in ks:
            m = (h >= fill + k * risk) & (first_hit[k] == 999) & np.isfinite(h)
            first_hit[k][m] = j
    cend = F.bar(F.C, e + endj, tj).astype("float64")
    out = {"race_complete": complete.astype(np.int8), "race_first_stop": first_stop}
    for k in ks:
        fh = first_hit[k]
        hit = (fh < first_stop) & (fh != 999)
        stp = (first_stop <= fh) & (first_stop != 999)
        neither = (~hit) & (~stp)
        rr = np.where(hit, float(k), np.where(stp, -1.0, (cend - fill) / risk))
        out[f"race{k}_hit"] = hit.astype(np.int8); out[f"race{k}_stop"] = stp.astype(np.int8); out[f"race{k}_neither"] = neither.astype(np.int8)
        out[f"race{k}_r"] = rr
    return out


def retry_entries(F: Frame, x_idx: np.ndarray, tj: np.ndarray, level: np.ndarray):
    """after a stop-out at session index x: the first session in [x+1, x+20] whose close > level (float32 strict). Returns the index or -1."""
    N = len(x_idx)
    found = np.full(N, -1, np.int64)
    lvl = level.astype("float32")
    for k in range(1, RETRY_WINDOW + 1):
        idx = x_idx + k
        c = F.bar(F.C, idx, tj)
        m = (found < 0) & np.isfinite(c) & (c > lvl)
        found[m] = idx[m]
    return found


def walk_chain(F: Frame, bday: np.ndarray, tj: np.ndarray, base_hi: np.ndarray, base_lo: np.ndarray, kind: str, variant: str,
               max_retries: int = 2, with_race: bool = True) -> pd.DataFrame:
    """the chain for every base: trade 0 off breakout day `bday`, then up to `max_retries` re-entries after a STOP exit.
    variant 'close': fill = close of the breakout day, session 0 = that day, walk from session 1; 'nopen': fill = the next open,
    session 0 = that next day, walked from session 0. One row per trade; `attempt` 0/1/2; `base` = the row number of the base.
    Rows whose entry is impossible (R <= 0, no next bar) are returned with status -1 ('skipped') and no walk."""
    assert variant in ("close", "nopen")
    N = len(bday)
    rows = []
    cur_b = bday.astype(np.int64); alive = np.ones(N, bool); base_id = np.arange(N)
    for attempt in range(max_retries + 1):
        b = cur_b[alive]; t = tj[alive]; bid = base_id[alive]; lo = base_lo[alive]
        if variant == "close":
            e = b; fill = F.C[b, t]; start_j = 1
        else:
            e = b + 1
            okb = e <= F.last
            fill = np.full(len(b), np.nan, "float32"); fill[okb] = F.O[e[okb], t[okb]]
            start_j = 0
        stop0 = stop_levels(F, kind, fill, b, t, lo)
        valid = np.isfinite(fill) & np.isfinite(stop0) & (fill > stop0)
        adr_b = F.ADR[b - 1, t].astype("float64")
        width_adr = (fill.astype("float64") - stop0.astype("float64")) / (adr_b * fill.astype("float64"))
        rec = pd.DataFrame({"base": bid, "attempt": attempt, "bday": b, "e": e, "fill": fill, "stop0": stop0, "valid": valid.astype(np.int8), "adr_b": adr_b, "width_adr": width_adr})
        if valid.any():
            w = walk(F, e[valid], t[valid], fill[valid], stop0[valid], start_j)
            if with_race and attempt == 0:
                w.update(race(F, e[valid], t[valid], fill[valid], stop0[valid], start_j))
            cols = {}
            for kcol, v in w.items():
                full = np.full(len(b), np.nan)
                full[valid] = v.astype(float)
                cols[kcol] = full
            rec = pd.concat([rec, pd.DataFrame(cols)], axis=1)
            rec["pnl_adr"] = rec.pnl_ps / (rec.adr_b * rec.fill.astype("float64"))      # size-free P&L: ADR20(b-1) x fill units
        rec.loc[~valid, "status"] = -1
        rows.append(rec)
        if attempt == max_retries:
            break
        # the next attempt: only after a STOP exit, at the first close above the base high within 20 sessions of the stop
        stopped = valid & (rec.status.to_numpy() == 1)
        nxt = np.full(len(b), -1, np.int64)
        if stopped.any():
            nxt[stopped] = retry_entries(F, rec.exit_idx.to_numpy()[stopped].astype(np.int64), t[stopped], base_hi[alive][stopped])
        new_alive = np.zeros(N, bool)
        new_alive[np.where(alive)[0][nxt >= 0]] = True
        cur_b[np.where(alive)[0][nxt >= 0]] = nxt[nxt >= 0]
        alive = new_alive
        if not alive.any():
            break
    out = pd.concat(rows, ignore_index=True)
    for c in ("status", "exit_j", "exit_idx", "pkind", "pj"):
        if c in out:
            out[c] = out[c].fillna(-1).astype(np.int32)
    out["kind"] = kind; out["variant"] = variant
    return out


def month_block_ci(diff: np.ndarray, months: np.ndarray, n_boot: int = 2000, seed: int = 702):
    """month-block bootstrap of a mean: resample months with replacement, each resample's mean = sum of drawn blocks / their count"""
    diff = np.asarray(diff, float); ok = np.isfinite(diff)
    diff, months = diff[ok], np.asarray(months)[ok]
    if len(diff) == 0:
        return (np.nan, np.nan, np.nan, 0)
    um, inv = np.unique(months, return_inverse=True)
    sums = np.bincount(inv, weights=diff, minlength=len(um)); cnts = np.bincount(inv, minlength=len(um)).astype(float)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(um), size=(n_boot, len(um)))
    means = sums[draws].sum(axis=1) / cnts[draws].sum(axis=1)
    return (float(diff.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)), int(len(diff)))


def account_view(r: np.ndarray, exit_idx: np.ndarray, entry_idx: np.ndarray, risk_frac: float = 0.005):
    """fixed 0.5% of equity risked per trade, additive (not compounded), no position cap, sequenced by exit session.
    total = risk × ΣR; worst drawdown = the deepest peak-to-trough of the running sum × risk; positions open at once (median/max)."""
    r = np.asarray(r, float); ok = np.isfinite(r)
    r, exit_idx, entry_idx = r[ok], np.asarray(exit_idx)[ok], np.asarray(entry_idx)[ok]
    if len(r) == 0:
        return dict(total_pct=np.nan, max_dd_pct=np.nan, total_r=np.nan, max_dd_r=np.nan, open_median=np.nan, open_max=np.nan, n=0)
    order = np.lexsort((entry_idx, exit_idx))
    cum = np.cumsum(r[order]); peak = np.maximum.accumulate(np.maximum(cum, 0.0))
    dd = (peak - cum).max()
    # positions open at once: +1 at the entry session, -1 after the exit session
    lo, hi = int(min(entry_idx.min(), exit_idx.min())), int(max(entry_idx.max(), exit_idx.max())) + 2
    ev = np.zeros(hi - lo + 1)
    np.add.at(ev, entry_idx - lo, 1); np.add.at(ev, exit_idx - lo + 1, -1)
    openc = np.cumsum(ev)[: hi - lo]
    openc = openc[openc > 0] if (openc > 0).any() else openc
    return dict(total_pct=100 * risk_frac * cum[-1], max_dd_pct=100 * risk_frac * dd, total_r=float(cum[-1]), max_dd_r=float(dd),
                open_median=float(np.median(openc)), open_max=float(openc.max()), n=int(len(r)))
