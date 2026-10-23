"""#705 Track B — the `pp` walker parameterised by trail average (10 / 20), trail trigger (X1..X4) and partial (P1 / P0).

`esr_lib.py` is read-only (brief): `walk` is COPIED here as `walk_v` and `walk_chain` as `walk_chain_v`; everything else (Frame, stops,
retries, bootstrap, account view, the matched-control helpers of 02_build) is imported or copied verbatim. With (20, X1, P1) `walk_v` must
return every array bit-equal to `esr_lib.walk` (01_parity.py) — that cell IS the `pp` baseline row. The silent-spot readings are in
DEFINITIONS.md, written before any walk ran. HARD SCOPE: the Frame cuts the 2022-24 export at 2024-12-31 (asserted in esr_lib)."""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_entry_stop_retry_1022")
from esr_lib import (Frame, ERAS, HORIZON, PARTIAL_R, PARTIAL_FRAC, STALL_R, STALL_SESSION, RETRY_WINDOW, STATUS,   # noqa: F401
                     stop_levels, retry_entries, race, month_block_ci, account_view, log, TICK_RE)

TRIGGERS = ("X1", "X2", "X3", "X4")
PARTIALS = ("P1", "P0")
AVGS = (10, 20)
X2_ADR_MULT = 0.5
X3_GRACE = 2
TRIG_NAME = {"X1": "X1 close below", "X2": "X2 decisive (≤ avg − 0.5 ADR, or 2 closes under)", "X3": "X3 reclaim forgiven (2 sessions)", "X4": "X4 intraday low under the prior avg"}
PART_NAME = {"P1": "P1 ⅓ at +2R", "P0": "P0 no partial"}


def cell_key(n, trig, part):
    return f"A{n}_{trig}_{part}"


def all_cells():
    """the 16 cells; the pp baseline (20, X1, P1) first so parity is asserted before any new arm is read"""
    base = (20, "X1", "P1")
    rest = [(n, t, p) for n in AVGS for t in TRIGGERS for p in PARTIALS if (n, t, p) != base]
    return [base] + rest


def add_sma(F: Frame, n: int):
    """SMA_n over the wide close frame, built exactly as esr_lib.Frame builds SMA20 (rolling mean of the float32 close pivot, cast to float32)"""
    attr = f"SMA{n}"
    if not hasattr(F, attr):
        setattr(F, attr, pd.DataFrame(F.C).rolling(n, min_periods=n).mean().to_numpy().astype("float32"))
    return getattr(F, attr)


def walk_v(F: Frame, e: np.ndarray, tj: np.ndarray, fill: np.ndarray, stop0: np.ndarray, start_j: int, sma_n: int = 20, trigger: str = "X1",
           partial: str = "P1", reached0: np.ndarray | None = None) -> dict:
    """esr_lib.walk with the trail arms. Same returns (status, exit_j, exit_idx, pnl_ps, realized_r, pkind, pj, be_stop, hole, at_cut) plus
    `hit2r` (the +2R level was reached at some session, by a high or an open), `trail_kind` (0 none / 1 close signal / 2 X2 decisive /
    3 X2 two closes / 4 X3 expiry / 5 X4 level) and `watch_started` (X3: a watch ever opened)."""
    assert trigger in TRIGGERS and partial in PARTIALS and sma_n in AVGS
    SMA = F.SMA if sma_n == 20 else add_sma(F, sma_n)
    P1 = partial == "P1"
    N = len(e)
    fill = fill.astype("float64"); stop0 = stop0.astype("float64")
    risk = fill - stop0
    assert (risk > 0).all(), "walk: every trade needs stop < fill"
    target = fill + PARTIAL_R * risk
    cut_lvl = fill + STALL_R * risk
    stop_now = stop0.copy()
    partial_f = np.zeros(N, bool); hit2r = np.zeros(N, bool)
    remaining = np.ones(N); pnl = np.zeros(N); reached = np.zeros(N, bool) if reached0 is None else reached0.astype(bool).copy()
    active = np.ones(N, bool)
    status = np.zeros(N, np.int8); exit_j = np.full(N, -1, np.int32); exit_idx = np.full(N, -1, np.int32)
    pkind = np.zeros(N, np.int8); pj = np.full(N, -1, np.int32); be_stop = np.zeros(N, bool); hole = np.zeros(N, bool)
    at_cut = np.zeros(N, bool); tkind = np.zeros(N, np.int8); watch_started = np.zeros(N, bool)
    under_prev = np.zeros(N, bool)                     # X2: the previous readable session closed under the average
    watch_j = np.full(N, -1, np.int32)                 # X3: the session of the close-under signal, -1 = no watch
    adr_b = F.ADR[e - 1, tj].astype("float64") if trigger == "X2" else None   # the trade's own ADR20 at bday − 1 (close variant: e = bday)
    frac = PARTIAL_FRAC
    for j in range(start_j, HORIZON + 1):
        if not active.any():
            break
        idx = e + j
        past = active & (idx > F.last)
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
            if j == HORIZON:
                sel = a[nan]
                px = F.CF[ia[nan], ta[nan]].astype("float64")
                pnl[sel] += (px - fill[sel]) * remaining[sel]
                status[sel] = 4; exit_j[sel] = j; exit_idx[sel] = ia[nan]; active[sel] = False
            keep = ~nan
            a, ia, ta, o, h, l, c = a[keep], ia[keep], ta[keep], o[keep], h[keep], l[keep], c[keep]
        sn = stop_now[a]; fa = fill[a]; tg = target[a]; cl = cut_lvl[a]
        done2 = partial_f[a] if P1 else hit2r[a]       # the +2R event has been consumed (P1: a third sold; P0: +2R reached)
        # X4: the level in force for this session = the PRIOR session's average, live only if a third sold / +2R reached BEFORE this session or j ≥ 3
        if trigger == "X4":
            live_pre = done2 | (j >= STALL_SESSION)
            lvl = SMA[ia - 1, ta].astype("float64")
            x4 = live_pre & np.isfinite(lvl) & (lvl > sn)
            eff = np.where(x4, lvl, sn)
        else:
            x4 = np.zeros(len(a), bool); eff = sn
        # (0) a gap open at/above the target with the +2R event unconsumed -> the third at the open (P1) / +2R reached (P0)
        gap = (~done2) & (o >= tg)
        # (1) the stop in force before this session (or the X4 level above it)
        st = (o <= eff) | (l <= eff)
        if st.any():
            s = a[st]
            g = gap[st]
            if g.any():
                sg = s[g]
                if P1:
                    pnl[sg] += (o[st][g] - fill[sg]) * frac; remaining[sg] -= frac; partial_f[sg] = True; pkind[sg] = 1; pj[sg] = j
                hit2r[sg] = True
            px = np.where(o[st] <= eff[st], o[st], eff[st])
            pnl[s] += (px - fill[s]) * remaining[s]
            be_stop[s] = sn[st] > stop0[s] + 1e-12
            status[s] = np.where(x4[st], 3, 1).astype(np.int8); tkind[s[x4[st]]] = 5
            exit_j[s] = j; exit_idx[s] = ia[st]; active[s] = False
        live = ~st
        a2, o2, h2, c2, fa2, tg2, cl2, d2, gap2 = a[live], o[live], h[live], c[live], fa[live], tg[live], cl[live], done2[live], gap[live]
        # (1b) the +2R leg
        hit = gap2 | ((~d2) & (h2 >= tg2))
        if hit.any():
            s = a2[hit]
            if P1:
                px = np.where(gap2[hit], o2[hit], tg2[hit])
                pnl[s] += (px - fill[s]) * frac; remaining[s] -= frac; partial_f[s] = True
                pkind[s] = np.where(gap2[hit], 1, 2); pj[s] = j
            hit2r[s] = True
            stop_now[s] = np.maximum(stop_now[s], fill[s])    # breakeven, resting from the NEXT session
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
                a2, o2, h2, c2, fa2 = a2[keep], o2[keep], h2[keep], c2[keep], fa2[keep]
        # (2) the session leg at session 3's close, only in profit, only with no third yet (P1 only)
        if P1 and j == STALL_SESSION and a2.size:
            leg = (~partial_f[a2]) & (c2 > fa2)
            if leg.any():
                s = a2[leg]
                pnl[s] += (c2[leg] - fill[s]) * frac; remaining[s] -= frac; partial_f[s] = True; pkind[s] = 3; pj[s] = j
                stop_now[s] = np.maximum(stop_now[s], fill[s])
        # (3) the trail on the close (X1 / X2 / X3): live once a third has sold (P1) / +2R reached (P0) or from session 3; sells at the NEXT open
        if a2.size and trigger != "X4":
            tl = (partial_f[a2] if P1 else hit2r[a2]) | (j >= STALL_SESSION)
            sma = SMA[idx[a2], tj[a2]].astype("float64")
            fin = np.isfinite(sma)
            under = fin & (c2 < sma)
            if trigger == "X1":
                sig = tl & under; kind = np.where(sig, 1, 0)
            elif trigger == "X2":
                dec = fin & (c2 <= sma * (1.0 - X2_ADR_MULT * adr_b[a2]))
                two = under & under_prev[a2]
                sig = tl & (dec | two); kind = np.where(dec, 2, np.where(two, 3, 0))
                under_prev[a2] = under                     # tracked on every readable session, live or not
            else:  # X3
                w = watch_j[a2]
                reclaim = (w >= 0) & fin & (c2 >= sma)
                expire = (w >= 0) & (~reclaim) & (j == w + X3_GRACE)
                start = tl & (w < 0) & under
                watch_j[a2[reclaim]] = -1
                watch_j[a2[start]] = j; watch_started[a2[start]] = True
                sig = expire; kind = np.where(sig, 4, 0)
            if sig.any():
                s = a2[sig]; ii = idx[s]; tt = tj[s]
                tkind[s] = kind[sig]
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
                    pnl[ss] += (c2[sig][~okn] - fill[ss]) * remaining[ss]
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
                be_stop=be_stop, hole=hole, at_cut=at_cut, hit2r=hit2r, trail_kind=tkind, watch_started=watch_started)


def walk_chain_v(F: Frame, bday: np.ndarray, tj: np.ndarray, base_hi: np.ndarray, base_lo: np.ndarray, kind: str, variant: str,
                 sma_n: int, trigger: str, partial: str, max_retries: int = 2, with_race: bool = False) -> pd.DataFrame:
    """esr_lib.walk_chain with walk_v in place of walk (the retry rule, the fills, the stops are untouched)"""
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
            w = walk_v(F, e[valid], t[valid], fill[valid], stop0[valid], start_j, sma_n, trigger, partial)
            if with_race and attempt == 0:
                w.update(race(F, e[valid], t[valid], fill[valid], stop0[valid], start_j))
            cols = {}
            for kcol, v in w.items():
                full = np.full(len(b), np.nan)
                full[valid] = v.astype(float)
                cols[kcol] = full
            rec = pd.concat([rec, pd.DataFrame(cols)], axis=1)
            rec["pnl_adr"] = rec.pnl_ps / (rec.adr_b * rec.fill.astype("float64"))
        rec.loc[~valid, "status"] = -1
        rows.append(rec)
        if attempt == max_retries:
            break
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
    for c in ("status", "exit_j", "exit_idx", "pkind", "pj", "trail_kind"):
        if c in out:
            out[c] = out[c].fillna(-1).astype(np.int32)
    out["kind"] = kind; out["variant"] = variant; out["sma_n"] = sma_n; out["trigger"] = trigger; out["partial"] = partial
    return out


# ── copied verbatim from _702_entry_stop_retry_1022/02_build.py (so the matched means are the same arithmetic) ──────────────────────────
def summarize(ch: pd.DataFrame, T: int, n_bases: int) -> pd.DataFrame:
    d = ch[(ch.attempt <= T) & (ch.status >= 0)]
    out = pd.DataFrame(index=pd.RangeIndex(n_bases))
    g = d.groupby("base")
    out["n_tr"] = g.size().reindex(out.index).fillna(0).astype(int)
    out["r_sum"] = g.realized_r.sum().reindex(out.index)
    out["adr_sum"] = g.pnl_adr.sum().reindex(out.index)
    out["r_max"] = g.realized_r.max().reindex(out.index)
    out["r_min"] = g.realized_r.min().reindex(out.index)
    out["last_exit"] = g.exit_idx.max().reindex(out.index)
    out["held"] = (d.exit_idx - d.e).groupby(d.base).sum().reindex(out.index)
    out["trunc"] = (d.status == 5).groupby(d.base).any().reindex(out.index).fillna(False).astype(int)
    f0 = ch[(ch.attempt == 0)].set_index("base")
    for c in ("realized_r", "pnl_adr", "width_adr", "status", "e", "exit_idx", "fill", "stop0", "exit_j", "pkind", "trail_kind", "race_complete", "race2_hit", "race5_hit", "race10_hit",
              "race2_stop", "race5_stop", "race10_stop", "race2_r", "race5_r", "race10_r", "valid"):
        if c in f0:
            out[f"f_{c}"] = f0[c].reindex(out.index)
    out.loc[out.f_valid != 1, ["r_sum", "adr_sum", "r_max", "r_min", "held", "n_tr", "f_width_adr", "f_pnl_adr", "f_realized_r"]] = np.nan
    for code, name in ((1, "stopped"), (2, "cut"), (3, "trailed"), (4, "censored"), (5, "degraded")):
        out[f"f_{name}"] = (out.f_status == code).astype(float).where(out.f_valid == 1)
    out["f_third"] = (out.f_pkind > 0).astype(float).where(out.f_valid == 1)
    out["f_tiny"] = (out.f_width_adr < 0.25).astype(float).where(out.f_valid == 1)
    out["any5"] = (out.r_max >= 5).astype(float).where(out.r_max.notna())
    out["any10"] = (out.r_max >= 10).astype(float).where(out.r_max.notna())
    out["win"] = (out.f_realized_r > 0).astype(float).where(out.f_realized_r.notna())
    out["retries"] = (out.n_tr - 1).clip(lower=0)
    if T >= 1:
        prev = ch[(ch.attempt <= T - 1) & (ch.status == 1)][["base", "attempt", "be_stop"]]
        nxt = ch[(ch.attempt >= 1) & (ch.attempt <= T) & (ch.status >= 0)][["base", "attempt"]].copy()
        nxt["attempt"] -= 1
        m = nxt.merge(prev, on=["base", "attempt"], how="left")
        out["retry_after_be"] = m.groupby("base").be_stop.sum().reindex(out.index).fillna(0)
    else:
        out["retry_after_be"] = 0.0
    return out


def cell_keys(df: pd.DataFrame, adr_cuts, ret_cuts, tcol="t", adrcol="adr", retcol="ret63"):
    dec = np.searchsorted(adr_cuts, df[adrcol].to_numpy(), side="right")
    quin = np.searchsorted(ret_cuts, df[retcol].to_numpy(), side="right")
    return df[tcol].to_numpy().astype(np.int64) * 100 + dec * 10 + quin, df[tcol].to_numpy().astype(np.int64) * 100 + dec * 10 + 9, df[tcol].to_numpy().astype(np.int64) * 100 + 99


def matched_means(ent_keys, ctl_keys_tuple, ctl_vals: pd.DataFrame, cols):
    k3, k2, k1 = ctl_keys_tuple
    cv = ctl_vals[cols].astype(float)
    g3 = cv.groupby(k3).mean(); g2 = cv.groupby(k2).mean(); g1 = cv.groupby(k1).mean()
    e3, e2, e1 = ent_keys
    m3 = g3.reindex(e3); m2 = g2.reindex(e2); m1 = g1.reindex(e1)
    res = m3.to_numpy()
    miss3 = np.isnan(res[:, 0])
    res[miss3] = m2.to_numpy()[miss3]
    miss2 = np.isnan(res[:, 0])
    res[miss2] = m1.to_numpy()[miss2]
    fb = dict(cell=int((~miss3).sum()), to_decile=int((miss3 & ~miss2).sum()), to_day=int(miss2.sum()))
    return pd.DataFrame(res, columns=cols), fb


# ── the populations, loaded exactly as 02_build.py of the 10-22 read loads them (copied; the asserts are the same) ────────────────────
def load_pops(era: str, F: Frame, sink=None, seed: int = 702):
    cfg = ERAS[era]; data = cfg["data"]; last = F.last
    ep = pd.read_csv(f"{data}/out/wrecall_episodes_{era}_x200.tsv.gz", sep="\t")
    ca = pd.read_csv(f"{data}/out/wrecall_catch_{era}_x200.tsv.gz", sep="\t", usecols=["ticker", "t", "covered", "triggered", "still_in_s50", "kept_half_episode", "kept_share_episode"])
    ep = ep[(ep.class_p == "measurable_breakout") & (ep.excluded == 0)].merge(ca, on=["ticker", "t"], how="left")
    assert ep.covered.notna().all()
    win = ep[ep.covered == 1].reset_index(drop=True).copy()
    for c in ("t", "b_p", "s50", "p"):
        win[c] = win[c].astype(int)
    assert (win.b_date.to_numpy() == F.cal.to_numpy()[win.b_p.to_numpy()]).all(), "episode indices are not this calendar's"
    win["tj"] = win.ticker.map(F.tpos).astype(int)
    assert np.allclose(F.C[win.t, win.tj], win.close_t, rtol=1e-5)
    win["complete120"] = ((win.b_p + HORIZON) <= last).astype(int)
    log(f"  P-win: {len(win)} covered measurable-breakout doublers; b+120 past the last session {int((win.complete120==0).sum())}", sink)
    r1 = pd.read_csv(f"{data}/out/bdef_r1_{era}.tsv.gz", sep="\t", low_memory=False).reset_index(drop=True).copy()
    r1["tj"] = r1.ticker.map(F.tpos).astype(int)
    assert (r1.entry_date.to_numpy() == F.cal.to_numpy()[r1.t.to_numpy()]).all()
    assert np.allclose(F.C[r1.t, r1.tj], r1.c_t, rtol=1e-5) and np.allclose(F.ADR[r1.t - 1, r1.tj], r1.adr_t1, rtol=1e-4)
    assert (r1.c_t.to_numpy("float32") > r1.pivot_full.to_numpy("float32")).all(), "an R1 close not above its base high"
    r1["complete120"] = ((r1.t + HORIZON) <= last).astype(int)
    r1 = pd.concat([r1, pd.DataFrame({"proxy_lo": F.PLO[r1.t, r1.tj], "proxy_hi": F.PHI[r1.t, r1.tj]})], axis=1)
    log(f"  P-all: R1 {len(r1)} rows over {r1.t.nunique()} days ({r1.entry_date.min()}..{r1.entry_date.max()}); R2 {int(r1.r2_exp.sum())}; complete {int(r1.complete120.sum())} / R2 {int(r1[r1.complete120==1].r2_exp.sum())}", sink)
    ctl = pd.read_csv(f"{data}/out/bdef_control_{era}.tsv.gz", sep="\t", usecols=["t", "ticker", "adr20", "ret63", "dv"])
    ctl = ctl[ctl.t.isin(set(r1.entry_date))].reset_index(drop=True)
    ctl["ci"] = ctl.t.map(F.cidx).astype(int); ctl["tj"] = ctl.ticker.map(F.tpos).astype(int)
    ctl["proxy_hi"] = F.PHI[ctl.ci, ctl.tj]; ctl["proxy_lo"] = F.PLO[ctl.ci, ctl.tj]
    okc = np.isfinite(ctl.proxy_hi) & np.isfinite(ctl.proxy_lo) & np.isfinite(F.C[ctl.ci, ctl.tj])
    log(f"  P-ctl: {len(ctl):,} control rows on the R1 days; without a readable 20-session proxy {int((~okc).sum())} (dropped)", sink)
    ctl = ctl[okc].reset_index(drop=True)
    ctl["complete120"] = ((ctl.ci + HORIZON) <= last).astype(int)
    assert np.allclose(F.ADR[ctl.ci - 1, ctl.tj], ctl.adr20, rtol=1e-4, equal_nan=True)
    rng = np.random.default_rng(seed)
    cells = {}
    for es in ("R1", "R2"):
        ent = r1 if es == "R1" else r1[r1.r2_exp == 1]
        adr_cuts = np.quantile(ent.adr_t1, np.arange(1, 10) / 10); ret_cuts = np.quantile(ent.ret63_t1.dropna(), np.arange(1, 5) / 5)
        ek = cell_keys(ent.assign(adr=ent.adr_t1, ret63=ent.ret63_t1), adr_cuts, ret_cuts)
        ck = cell_keys(ctl.assign(t=ctl.ci, adr=ctl.adr20), adr_cuts, ret_cuts)
        pos3 = pd.Series(np.arange(len(ctl))).groupby(ck[0]).apply(lambda s: s.to_numpy())
        pos2 = pd.Series(np.arange(len(ctl))).groupby(ck[1]).apply(lambda s: s.to_numpy())
        pos1 = pd.Series(np.arange(len(ctl))).groupby(ck[2]).apply(lambda s: s.to_numpy())
        samp = np.full(len(ent), -1, np.int64)
        for i, (a, b, c) in enumerate(zip(ek[0], ek[1], ek[2])):
            for keyd, kk in ((pos3, a), (pos2, b), (pos1, c)):
                if kk in keyd.index:
                    arr = keyd.loc[kk]; samp[i] = arr[rng.integers(0, len(arr))]; break
        cells[es] = dict(ent_index=ent.index.to_numpy(), ek=ek, ck=ck, adr_cuts=adr_cuts.tolist(), ret_cuts=ret_cuts.tolist(), sample=samp)
        log(f"  cells {es}: n entries {len(ent)}; sample drawn {int((samp>=0).sum())}", sink)
    return win, r1, ctl, cells
