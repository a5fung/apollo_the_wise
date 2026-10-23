"""#705 entry/stop/retry — step 2: the grid, per era, under the FROZEN §D of docs/analysis/cb_entry_stop_retry_2026-10-22.md.

Per era (2017-21 = cb702_pre, 2022-24 = cb702) walks, for every stop S1..S4 × entry variant close/nopen, the up-to-three-trade chain
(T2; T1 and T0 are read off it) on: P-win (the covered measurable-breakout doublers), P-all (every R1 real breakout; R2 = its
expansion subset) and P-ctl (the matched control re-walked under the same rules). Writes under DATA/out/:
  esr_win_<era>.tsv.gz        one row per (stop, variant, base, attempt) on the doublers
  esr_r1_<era>.tsv.gz         the same on the R1 breakouts
  esr_ctl_<era>.parquet       one row per (stop, variant, control base) — the chain summaries for T0/T1/T2 and the first-trade race
  esr_ctlsample_<era>.tsv.gz  per-trade rows of the account-view control (one control row per entry, drawn from its cell, seed 702)
and under the probe dir: 02_numbers_<era>.json (every reported number) and 02_build_<era>.log (checks).
HARD SCOPE: the export is cut at 2024-12-31 at load (asserted); nothing under DATA is modified or deleted; the runner is never imported."""
from __future__ import annotations
import json, os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_entry_stop_retry_1022")
from esr_lib import (Frame, ERAS, STOPS, HORIZON, walk_chain, month_block_ci, account_view, log, TICK_RE, out_dir, PRE_OUT, LOG_DIR)

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_entry_stop_retry_1022"
VARIANTS = ("close", "nopen")
SEED = 702
SMOKE = os.environ.get("ESR_SMOKE")          # a one-cell run on a control subsample, outputs suffixed _smoke
SFX = "_smoke" if SMOKE else ""
if SMOKE:
    STOPS = ("S1", "S4"); VARIANTS = ("close",)


def q(x, qs=(0.25, 0.5, 0.75)):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return [float(np.quantile(x, v)) for v in qs] if len(x) else [np.nan] * len(qs)


def summarize(ch: pd.DataFrame, T: int, n_bases: int) -> pd.DataFrame:
    """per-base chain summary for retries ≤ T (attempts 0..T): n trades, chain R, first-trade R / status / race, any ≥5R / ≥10R,
    truncation, retries that followed a breakeven stop. Bases whose first trade was impossible (status -1) carry NaN."""
    d = ch[(ch.attempt <= T) & (ch.status >= 0)]
    out = pd.DataFrame(index=pd.RangeIndex(n_bases))
    g = d.groupby("base")
    out["n_tr"] = g.size().reindex(out.index).fillna(0).astype(int)
    out["r_sum"] = g.realized_r.sum().reindex(out.index)
    out["adr_sum"] = g.pnl_adr.sum().reindex(out.index)
    out["r_max"] = g.realized_r.max().reindex(out.index)
    out["last_exit"] = g.exit_idx.max().reindex(out.index)
    out["trunc"] = (d.status == 5).groupby(d.base).any().reindex(out.index).fillna(False).astype(int)
    f0 = ch[(ch.attempt == 0)].set_index("base")
    for c in ("realized_r", "pnl_adr", "width_adr", "status", "e", "exit_idx", "fill", "stop0", "exit_j", "pkind", "race_complete", "race2_hit", "race5_hit", "race10_hit",
              "race2_stop", "race5_stop", "race10_stop", "race2_r", "race5_r", "race10_r", "valid"):
        if c in f0:
            out[f"f_{c}"] = f0[c].reindex(out.index)
    out.loc[out.f_valid != 1, ["r_sum", "adr_sum", "r_max", "n_tr", "f_width_adr", "f_pnl_adr", "f_realized_r"]] = np.nan
    for code, name in ((1, "stopped"), (2, "cut"), (3, "trailed"), (4, "censored"), (5, "degraded")):
        out[f"f_{name}"] = (out.f_status == code).astype(float).where(out.f_valid == 1)
    out["f_third"] = (out.f_pkind > 0).astype(float).where(out.f_valid == 1)
    out["f_tiny"] = (out.f_width_adr < 0.25).astype(float).where(out.f_valid == 1)
    out["any5"] = (out.r_max >= 5).astype(float).where(out.r_max.notna())
    out["any10"] = (out.r_max >= 10).astype(float).where(out.r_max.notna())
    out["win"] = (out.f_realized_r > 0).astype(float).where(out.f_realized_r.notna())
    out["retries"] = (out.n_tr - 1).clip(lower=0)
    # retries that followed a breakeven stop (the previous attempt's stop had been raised)
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
    """per entry: the control's mean in its (t, decile, quintile) cell; fallback (t, decile), then t. Returns a frame + fallback counts."""
    k3, k2, k1 = ctl_keys_tuple
    out = {}
    fb = {}
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


def build(era):
    cfg = ERAS[era]; data = cfg["data"]; sink = []
    log(f"== {era}", sink)
    F = Frame(data, cfg["cut"], sink)
    last = F.last
    # ── P-win: the covered measurable-breakout doublers ───────────────────────────────────────────
    ep = pd.read_csv(f"{out_dir(era, data)}/wrecall_episodes_{era}_x200.tsv.gz", sep="\t")
    ca = pd.read_csv(f"{out_dir(era, data)}/wrecall_catch_{era}_x200.tsv.gz", sep="\t", usecols=["ticker", "t", "covered", "triggered", "still_in_s50", "kept_half_episode", "kept_share_episode"])
    ep = ep[(ep.class_p == "measurable_breakout") & (ep.excluded == 0)].merge(ca, on=["ticker", "t"], how="left")
    assert ep.covered.notna().all()
    win = ep[ep.covered == 1].reset_index(drop=True).copy()
    for c in ("t", "b_p", "s50", "p"):
        win[c] = win[c].astype(int)
    assert (win.b_date.to_numpy() == F.cal.to_numpy()[win.b_p.to_numpy()]).all(), "episode indices are not this calendar's"
    win["tj"] = win.ticker.map(F.tpos).astype(int)
    assert np.allclose(F.C[win.t, win.tj], win.close_t, rtol=1e-5)
    win["complete120"] = ((win.b_p + HORIZON) <= last).astype(int)
    log(f"  P-win: {len(win)} covered measurable-breakout doublers; b+120 past the last session {int((win.complete120==0).sum())}; "
        f"ext_truncated {int(win.ext_truncated.sum())}; the published catch: triggered {int(win.triggered.sum())}, still in at s50 {int(win.still_in_s50.fillna(0).sum())}, kept half {int(win.kept_half_episode.fillna(0).sum())}", sink)
    # ── P-all: the R1 real breakouts ───────────────────────────────────────────────────────────────
    r1 = pd.read_csv(f"{out_dir(era, data)}/bdef_r1_{era}.tsv.gz", sep="\t", low_memory=False)
    r1 = r1.reset_index(drop=True).copy()
    r1["tj"] = r1.ticker.map(F.tpos).astype(int)
    assert (r1.entry_date.to_numpy() == F.cal.to_numpy()[r1.t.to_numpy()]).all()
    assert np.allclose(F.C[r1.t, r1.tj], r1.c_t, rtol=1e-5) and np.allclose(F.ADR[r1.t - 1, r1.tj], r1.adr_t1, rtol=1e-4)
    assert (r1.c_t.to_numpy("float32") > r1.pivot_full.to_numpy("float32")).all(), "an R1 close not above its base high"
    r1["complete120"] = ((r1.t + HORIZON) <= last).astype(int)
    r1 = pd.concat([r1, pd.DataFrame({"proxy_lo": F.PLO[r1.t, r1.tj], "proxy_hi": F.PHI[r1.t, r1.tj]})], axis=1)
    log(f"  P-all: R1 {len(r1)} rows over {r1.t.nunique()} days ({r1.entry_date.min()}..{r1.entry_date.max()}); R2 {int(r1.r2_exp.sum())}; "
        f"complete (t+120 <= last) {int(r1.complete120.sum())} / R2 {int(r1[r1.complete120==1].r2_exp.sum())}; base_len median {r1.base_len.median():.0f}", sink)
    # ── P-ctl: the matched control rows on the R1 entry days ───────────────────────────────────────
    ctl = pd.read_csv(f"{out_dir(era, data)}/bdef_control_{era}.tsv.gz", sep="\t", usecols=["t", "ticker", "adr20", "ret63", "dv"])
    ctl = ctl[ctl.t.isin(set(r1.entry_date))].reset_index(drop=True)
    ctl["ci"] = ctl.t.map(F.cidx).astype(int); ctl["tj"] = ctl.ticker.map(F.tpos).astype(int)
    ctl["proxy_hi"] = F.PHI[ctl.ci, ctl.tj]; ctl["proxy_lo"] = F.PLO[ctl.ci, ctl.tj]
    okc = np.isfinite(ctl.proxy_hi) & np.isfinite(ctl.proxy_lo) & np.isfinite(F.C[ctl.ci, ctl.tj])
    log(f"  P-ctl: {len(ctl):,} control rows on the R1 days; without a readable 20-session proxy {int((~okc).sum())} (dropped)", sink)
    ctl = ctl[okc].reset_index(drop=True)
    if SMOKE:
        ctl = ctl.sample(40000, random_state=1).sort_values("ci").reset_index(drop=True); log(f"  SMOKE: control subsampled to {len(ctl)}", sink)
    ctl["complete120"] = ((ctl.ci + HORIZON) <= last).astype(int)
    assert np.allclose(F.ADR[ctl.ci - 1, ctl.tj], ctl.adr20, rtol=1e-4, equal_nan=True)
    # cells for R1 and for R2, cut on the entry set; the account-view sample (one control row per entry)
    rng = np.random.default_rng(SEED)
    cells = {}
    for es in ("R1", "R2"):
        ent = r1 if es == "R1" else r1[r1.r2_exp == 1]
        adr_cuts = np.quantile(ent.adr_t1, np.arange(1, 10) / 10); ret_cuts = np.quantile(ent.ret63_t1.dropna(), np.arange(1, 5) / 5)
        ek = cell_keys(ent.assign(adr=ent.adr_t1, ret63=ent.ret63_t1), adr_cuts, ret_cuts)
        ck = cell_keys(ctl.assign(t=ctl.ci, adr=ctl.adr20), adr_cuts, ret_cuts)
        # the sample: per entry one control row from its cell (fallbacks as the means)
        pos3 = pd.Series(np.arange(len(ctl))).groupby(ck[0]).apply(lambda s: s.to_numpy())
        pos2 = pd.Series(np.arange(len(ctl))).groupby(ck[1]).apply(lambda s: s.to_numpy())
        pos1 = pd.Series(np.arange(len(ctl))).groupby(ck[2]).apply(lambda s: s.to_numpy())
        samp = np.full(len(ent), -1, np.int64)
        for i, (a, b, c) in enumerate(zip(ek[0], ek[1], ek[2])):
            for keyd, kk in ((pos3, a), (pos2, b), (pos1, c)):
                if kk in keyd.index:
                    arr = keyd.loc[kk]; samp[i] = arr[rng.integers(0, len(arr))]; break
        cells[es] = dict(ent_index=ent.index.to_numpy(), ek=ek, ck=ck, adr_cuts=adr_cuts.tolist(), ret_cuts=ret_cuts.tolist(), sample=samp)
        log(f"  cells {es}: n entries {len(ent)}; ADR deciles {np.round(adr_cuts, 4).tolist()}; ret63 quintiles {np.round(ret_cuts, 3).tolist()}; sample drawn {int((samp>=0).sum())}", sink)
    sample_ids = np.unique(np.concatenate([cells["R1"]["sample"], cells["R2"]["sample"]]))
    sample_ids = sample_ids[sample_ids >= 0]

    numbers = dict(era=era, sessions=len(F.cal), cal_first=F.cal[0], cal_last=F.cal[-1], last_idx=int(last),
                   win=dict(n=int(len(win)), complete120=int(win.complete120.sum()), ext_truncated=int(win.ext_truncated.sum()),
                            pub_triggered=int(win.triggered.sum()), pub_still_in_s50=int(win.still_in_s50.fillna(0).sum()), pub_kept_half=int(win.kept_half_episode.fillna(0).sum()),
                            adr_bprev_med=float(win.adr20_bprev.median()), gain_med=float(win.gain.median()), L_med=float(win.L_p.median())),
                   r1=dict(n=int(len(r1)), n_r2=int(r1.r2_exp.sum()), complete=int(r1.complete120.sum()), complete_r2=int(r1[r1.complete120 == 1].r2_exp.sum()),
                           days=int(r1.t.nunique()), first=r1.entry_date.min(), last=r1.entry_date.max(), base_len_q=q(r1.base_len), adr_q=q(r1.adr_t1), ret63_q=q(r1.ret63_t1),
                           complete_first=r1[r1.complete120 == 1].entry_date.min(), complete_last=r1[r1.complete120 == 1].entry_date.max(),
                           weeks_all=float((r1.t.max() - r1.t.min() + 1) / 5), weeks_complete=float((r1[r1.complete120 == 1].t.max() - r1[r1.complete120 == 1].t.min() + 1) / 5)),
                   ctl=dict(n=int(len(ctl)), complete=int(ctl.complete120.sum()), adr_q=q(ctl.adr20), ret63_q=q(ctl.ret63), cells={k: dict(adr_cuts=v["adr_cuts"], ret_cuts=v["ret_cuts"]) for k, v in cells.items()}),
                   grid={})
    win_rows, r1_rows, ctl_parts, samp_rows = [], [], [], []
    MEAS = ["r_sum", "adr_sum", "f_realized_r", "f_pnl_adr", "f_width_adr", "win", "any5", "any10", "n_tr", "f_race2_hit", "f_race5_hit", "f_race10_hit", "f_race2_stop", "f_race5_stop", "f_race10_stop",
            "f_race2_r", "f_race5_r", "f_race10_r", "retries", "retry_after_be", "trunc", "f_stopped", "f_cut", "f_trailed", "f_censored", "f_degraded", "f_third", "f_tiny"]
    for kind in STOPS:
        for variant in VARIANTS:
            t0 = time.time(); key = f"{kind}_{variant}"; G = {}
            # P-win
            chw = walk_chain(F, win.b_p.to_numpy(), win.tj.to_numpy(), win.base_high_p.to_numpy("float32"), win.base_low_p.to_numpy("float32"), kind, variant, 2, with_race=False)
            chw["ticker"] = win.ticker.to_numpy()[chw.base]
            win_rows.append(chw)
            G["win"] = {}
            f0 = chw[chw.attempt == 0]
            wadr = ((f0.fill - f0.stop0) / (F.ADR[f0.bday - 1, win.tj.to_numpy()[f0.base]] * f0.fill)).to_numpy()
            G["win"]["width_adr_q"] = q(wadr); G["win"]["n_skipped_first"] = int((f0.status == -1).sum())
            for T in (0, 1, 2):
                s = summarize(chw, T, len(win))
                d = chw[(chw.attempt <= T) & (chw.status >= 0)]
                s50 = win.s50.to_numpy(); gain_ps = (win.close_p - win.close_t).to_numpy()
                inat = ((d.e.to_numpy() <= s50[d.base]) & (d.exit_idx.to_numpy() >= s50[d.base]))
                still = pd.Series(inat).groupby(d.base.to_numpy()).any().reindex(range(len(win))).fillna(False).to_numpy()
                kept = d.groupby("base").pnl_ps.sum().reindex(range(len(win))).to_numpy() / gain_ps
                valid = s.f_valid.to_numpy() == 1
                fs = s.f_status.to_numpy(); fx = s.f_exit_idx.to_numpy()
                G["win"][f"T{T}"] = dict(first_status_mix={str(k): int(v) for k, v in pd.Series(fs[valid]).value_counts().to_dict().items()},
                                        adr_sum_mean=float(s.adr_sum[valid].mean()), n=int(valid.sum()), still_in_s50=int(still[valid].sum()), kept_half=int((kept[valid] >= 0.5).sum()), kept_quarter=int((kept[valid] >= 0.25).sum()),
                                        kept_share_q=q(kept[valid]), kept_share_mean=float(np.nanmean(kept[valid])),
                                        first_stopped_before_s50=int(((fs == 1) & (fx < s50))[valid].sum()), first_cut=int((fs == 2)[valid].sum()),
                                        first_stopped_any=int((fs == 1)[valid].sum()),
                                        retries_mean=float(s.retries[valid].mean()), used1=int((s.retries[valid] == 1).sum()), used2=int((s.retries[valid] == 2).sum()),
                                        retry_after_be=int(s.retry_after_be[valid].sum()), trunc=int(s.trunc[valid].sum()),
                                        chain_r_mean=float(s.r_sum[valid].mean()), chain_r_q=q(s.r_sum[valid]), any5=int(s.any5[valid].sum()), any10=int(s.any10[valid].sum()),
                                        still_in_s50_needing_retry=int((still & (s.retries.to_numpy() >= 1))[valid].sum()),
                                        kept_half_needing_retry=int(((kept >= 0.5) & (s.retries.to_numpy() >= 1))[valid].sum()),
                                        kept_quarter_needing_retry=int(((kept >= 0.25) & (s.retries.to_numpy() >= 1))[valid].sum()))
            # P-all
            chr_ = walk_chain(F, r1.t.to_numpy(), r1.tj.to_numpy(), r1.pivot_full.to_numpy("float32"), r1.base_low.to_numpy("float32"), kind, variant, 2, with_race=True)
            chr_["ticker"] = r1.ticker.to_numpy()[chr_.base]
            r1_rows.append(chr_)
            # the overlap: retry entries that are themselves another R1 row's breakout day (same ticker, same day)
            rk = set(zip(r1.ticker, r1.t))
            rt = chr_[(chr_.attempt >= 1) & (chr_.status >= 0)]
            G["r1_retry_is_another_r1"] = int(sum((tk, int(b)) in rk for tk, b in zip(rt.ticker, rt.bday)))
            G["r1_retry_trades"] = int(len(rt))
            # P-ctl
            chc = walk_chain(F, ctl.ci.to_numpy(), ctl.tj.to_numpy(), ctl.proxy_hi.to_numpy("float32"), ctl.proxy_lo.to_numpy("float32"), kind, variant, 2, with_race=True)
            sm = chc[chc.base.isin(sample_ids)].copy(); sm["kind"] = kind; sm["variant"] = variant; sm["ticker"] = ctl.ticker.to_numpy()[sm.base]
            samp_rows.append(sm)
            sums_r1 = {T: summarize(chr_, T, len(r1)) for T in (0, 1, 2)}
            sums_c = {T: summarize(chc, T, len(ctl)) for T in (0, 1, 2)}
            for T in (0, 1, 2):
                sc = sums_c[T].copy(); sc["kind"] = kind; sc["variant"] = variant; sc["T"] = T; sc["base"] = np.arange(len(ctl)); sc["ci"] = ctl.ci.to_numpy(); sc["complete120"] = ctl.complete120.to_numpy()
                ctl_parts.append(sc[["kind", "variant", "T", "base", "ci", "complete120"] + MEAS + ["f_status", "f_fill", "f_stop0", "f_valid"]])
            del chc
            # widths (first trades, entries and control), proxy width on the entries
            f0 = chr_[chr_.attempt == 0]
            G["r1_width_adr_q"] = q(((f0.fill - f0.stop0) / (r1.adr_t1.to_numpy()[f0.base] * f0.fill)).to_numpy())
            G["r1_width_adr_q_r2"] = q(((f0.fill - f0.stop0) / (r1.adr_t1.to_numpy()[f0.base] * f0.fill)).to_numpy()[r1.r2_exp.to_numpy()[f0.base] == 1])
            if kind == "S4":
                G["r1_proxy_width_adr_q"] = q(((f0.fill - r1.proxy_lo.to_numpy()[f0.base]) / (r1.adr_t1.to_numpy()[f0.base] * f0.fill)).to_numpy())
            s0c = sums_c[0]
            G["ctl_width_adr_q"] = q(((s0c.f_fill - s0c.f_stop0) / (ctl.adr20.to_numpy() * s0c.f_fill)).to_numpy())
            G["r1_skipped_first"] = int((f0.status == -1).sum()); G["ctl_skipped_first"] = int((s0c.f_valid != 1).sum())
            # the comparison, per entry set × T × completeness
            for es in ("R1", "R2"):
                C = cells[es]; eidx = C["ent_index"]
                ent = r1.loc[eidx]
                for T in (0, 1, 2):
                    se = sums_r1[T].loc[eidx].reset_index(drop=True); sc = sums_c[T]
                    mm_all, fb_all = matched_means(C["ek"], C["ck"], sc, MEAS)
                    cw = (sc.f_width_adr >= 0.25).to_numpy()
                    mm_w, fb_w = matched_means(C["ek"], tuple(k[cw] for k in C["ck"]), sc[cw], MEAS)
                    for comp in ("complete", "all", "complete_w025"):
                        keep = (ent.complete120.to_numpy() == 1) if comp.startswith("complete") else np.ones(len(ent), bool)
                        keep &= se.f_valid.to_numpy() == 1
                        if comp == "complete_w025":
                            keep &= se.f_width_adr.to_numpy() >= 0.25
                            mm, fb = mm_w, fb_w
                        else:
                            mm, fb = mm_all, fb_all
                        E = se[keep].reset_index(drop=True); M = mm[keep].reset_index(drop=True); months = ent.entry_date.to_numpy()[keep].astype("U7")
                        ent_k = ent[keep]
                        weeks = (ent_k.t.max() - ent_k.t.min() + 1) / 5 if len(ent_k) else np.nan
                        n = len(E)
                        def summ(S):
                            o = dict(n=n, trades=float(np.nansum(S.n_tr)), trades_per_week=float(np.nansum(S.n_tr) / weeks) if weeks else np.nan,
                                     r_per_trade=float(np.nansum(S.r_sum) / np.nansum(S.n_tr)) if np.nansum(S.n_tr) else np.nan,
                                     adr_per_trade=float(np.nansum(S.adr_sum) / np.nansum(S.n_tr)) if np.nansum(S.n_tr) else np.nan,
                                     adr_per_base=float(np.nanmean(S.adr_sum)), first_adr=float(np.nanmean(S.f_pnl_adr)), width_adr_mean=float(np.nanmean(S.f_width_adr)),
                                     tiny_share=float(np.nanmean(S.f_tiny)), stopped=float(np.nanmean(S.f_stopped)), cut=float(np.nanmean(S.f_cut)), trailed=float(np.nanmean(S.f_trailed)),
                                     censored=float(np.nanmean(S.f_censored)), degraded=float(np.nanmean(S.f_degraded)), third=float(np.nanmean(S.f_third)),
                                     r_per_base=float(np.nanmean(S.r_sum)), first_r=float(np.nanmean(S.f_realized_r)), win=float(np.nanmean(S.win)),
                                     any5_per100=float(100 * np.nanmean(S.any5)), any10_per100=float(100 * np.nanmean(S.any10)),
                                     retries_mean=float(np.nanmean(S.retries)), retry_after_be=float(np.nansum(S.retry_after_be)), trunc=float(np.nansum(S.trunc)))
                            for k in (2, 5, 10):
                                o[f"race{k}_hit"] = float(np.nanmean(S[f"f_race{k}_hit"])); o[f"race{k}_stop"] = float(np.nanmean(S[f"f_race{k}_stop"])); o[f"race{k}_r"] = float(np.nanmean(S[f"f_race{k}_r"]))
                            return o
                        ent_s = summ(E); ctl_s = summ(M)
                        # per-trade tail on the entries (≥5R / ≥10R per 100 TRADES) and the median chain R
                        dtr = chr_[(chr_.attempt <= T) & (chr_.status >= 0) & np.isin(chr_.base, eidx[keep])]
                        ent_s.update(ge5_per100_trades=float(100 * (dtr.realized_r >= 5).mean()), ge10_per100_trades=float(100 * (dtr.realized_r >= 10).mean()),
                                     r_per_trade_median=float(dtr.realized_r.median()), win_per_trade=float((dtr.realized_r > 0).mean()), r_per_base_median=float(np.nanmedian(E.r_sum)),
                                     race_complete=int(np.nansum(E.f_race_complete)), all_status_mix={str(k): int(v) for k, v in dtr.status.value_counts().to_dict().items()},
                                     all_pkind_mix={str(k): int(v) for k, v in dtr.pkind.value_counts().to_dict().items()}, width_q=q(E.f_width_adr, (0.05, 0.1, 0.25, 0.5, 0.75)),
                                     r_top5_share=float(dtr.realized_r.nlargest(5).sum() / dtr.realized_r.sum()) if dtr.realized_r.sum() else np.nan)
                        ctl_s.update(width_q=q(sc.f_width_adr, (0.05, 0.1, 0.25, 0.5, 0.75)))
                        diffs = {}
                        for col, name in (("r_sum", "r_per_base"), ("adr_sum", "adr_per_base"), ("f_realized_r", "first_r"), ("f_pnl_adr", "first_adr"), ("win", "win"), ("any5", "any5"), ("any10", "any10"),
                                          ("f_race2_hit", "race2_hit"), ("f_race5_hit", "race5_hit"), ("f_race10_hit", "race10_hit"), ("f_race2_r", "race2_r"), ("f_race5_r", "race5_r"), ("f_race10_r", "race10_r")):
                            dv = E[col].to_numpy(float) - M[col].to_numpy(float)
                            scale = 100.0 if name in ("win", "any5", "any10", "race2_hit", "race5_hit", "race10_hit") else 1.0
                            m_, lo, hi, nn = month_block_ci(dv * scale, months)
                            diffs[name] = dict(diff=m_, lo=lo, hi=hi, n=nn)
                        # account view: the entries' chain trades; the sampled control's chain trades
                        acc = account_view(dtr.realized_r.to_numpy(), dtr.exit_idx.to_numpy(), dtr.e.to_numpy())
                        sids = C["sample"][keep]
                        sm_k = sm[(sm.attempt <= T) & (sm.status >= 0) & sm.base.isin(sids)]
                        # a sampled control base may be drawn by several entries: weight by multiplicity
                        mult = pd.Series(sids).value_counts()
                        wts = sm_k.base.map(mult).fillna(0).to_numpy()
                        rr = np.repeat(sm_k.realized_r.to_numpy(), wts.astype(int)); xx = np.repeat(sm_k.exit_idx.to_numpy(), wts.astype(int)); ee = np.repeat(sm_k.e.to_numpy(), wts.astype(int))
                        acc_c = account_view(rr, xx, ee)
                        G[f"{es}_T{T}_{comp}"] = dict(entries=ent_s, control=ctl_s, diff=diffs, fallback=fb, account=acc, account_control=acc_c, weeks=float(weeks) if weeks else np.nan)
            numbers["grid"][key] = G
            log(f"  {key}: done in {time.time()-t0:.0f}s; R1 T0 complete: r/trade {G['R1_T0_complete']['entries']['r_per_trade']:+.3f} vs ctl {G['R1_T0_complete']['control']['r_per_trade']:+.3f}, "
                f"trades/wk {G['R1_T0_complete']['entries']['trades_per_week']:.1f}; T2 r/base {G['R1_T2_complete']['entries']['r_per_base']:+.3f} vs {G['R1_T2_complete']['control']['r_per_base']:+.3f}; "
                f"P-win T0 still-in-s50 {G['win']['T0']['still_in_s50']}/{G['win']['T0']['n']} kept-half {G['win']['T0']['kept_half']}; T2 {G['win']['T2']['still_in_s50']} / {G['win']['T2']['kept_half']}; "
                f"width ADR median {G['r1_width_adr_q'][1]:.2f} (ctl {G['ctl_width_adr_q'][1]:.2f})", sink)
    # ── write ──────────────────────────────────────────────────────────────────────────────────────
    W = pd.concat(win_rows, ignore_index=True)
    for c in ("t", "s50", "p", "close_t", "close_p", "gain", "adr20_bprev", "L_p", "base_high_p", "base_low_p", "complete120"):
        W[c] = win[c].to_numpy()[W.base]
    W.to_csv(f"{out_dir(era, data)}/esr_win_{era}{SFX}.tsv.gz", sep="\t", index=False, float_format="%.7g")
    R = pd.concat(r1_rows, ignore_index=True)
    for c in ("t", "entry_date", "r2_exp", "adr_t1", "ret63_t1", "pivot_full", "base_low", "base_len", "complete120", "proxy_lo"):
        R[c] = r1[c].to_numpy()[R.base]
    R.to_csv(f"{out_dir(era, data)}/esr_r1_{era}{SFX}.tsv.gz", sep="\t", index=False, float_format="%.7g")
    CT = pd.concat(ctl_parts, ignore_index=True)
    for c in MEAS + ["f_fill", "f_stop0"]:
        CT[c] = CT[c].astype("float32")
    CT["ticker"] = ctl.ticker.to_numpy()[CT.base]
    CT.to_parquet(f"{out_dir(era, data)}/esr_ctl_{era}{SFX}.parquet", index=False)
    SM = pd.concat(samp_rows, ignore_index=True)
    SM.to_csv(f"{out_dir(era, data)}/esr_ctlsample_{era}{SFX}.tsv.gz", sep="\t", index=False, float_format="%.7g")
    pd.DataFrame({es: cells[es]["sample"] for es in ("R1",)} | {"ent_index_R1": cells["R1"]["ent_index"]}).to_csv(f"{LOG_DIR}/02_sample_R1_{era}{SFX}.tsv", sep="\t", index=False)
    pd.DataFrame({"R2": cells["R2"]["sample"], "ent_index_R2": cells["R2"]["ent_index"]}).to_csv(f"{LOG_DIR}/02_sample_R2_{era}{SFX}.tsv", sep="\t", index=False)
    log(f"  wrote esr_win ({len(W)} rows), esr_r1 ({len(R)}), esr_ctl ({len(CT):,}), esr_ctlsample ({len(SM)})", sink)
    with open(f"{LOG_DIR}/02_numbers_{era}{SFX}.json", "w") as fh:
        json.dump(numbers, fh, indent=1, default=lambda o: float(o) if isinstance(o, (np.floating, np.integer)) else str(o))
    with open(f"{LOG_DIR}/02_build_{era}{SFX}.log", "w") as fh:
        fh.write("\n".join(sink) + "\n")


if __name__ == "__main__":
    eras = sys.argv[1:] or list(ERAS)
    assert (not (PRE_OUT or LOG_DIR != HERE)) or eras == ["2017-21"], "CB_PRE_OUT / CB_PRE_LOG re-run the 2017-21 era only"
    for era in eras:
        build(era)
