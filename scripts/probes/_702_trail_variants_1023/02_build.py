"""#705 Track B — step 2: the 16-cell trail grid per era, on S2 close with up to two retries (T0 / T1 beside), under BRIEF.md + DEFINITIONS.md.

Per era (2017-21 = cb702_pre, 2022-24 = cb702): for each (average 10/20 × trigger X1..X4 × partial P1/P0) the chain on P-win (the covered
measurable-breakout doublers), P-all (every R1 real breakout; R2 = its expansion subset) and P-ctl (the matched control re-walked under the
same rules). The pp baseline (20, X1, P1) runs FIRST and must reproduce every number of the 10-22 read's `02_numbers_<era>.json['grid']
['S2_close']` (parity (c)) or the build stops before any new arm is read. Writes under DATA/out/: trail_win_<era>.tsv.gz (one row per cell ×
base × attempt on the doublers), trail_r1_<era>.tsv.gz (the same on R1), trail_ctlsample_<era>.tsv.gz (the seed-702 account-view control's
trades per cell), trail_ctlmatch_<era>.parquet (the matched control means per entry × cell × entry set × retry depth); under the probe dir:
02_numbers_<era>.json (every reported number) and 02_build_<era>.log. HARD SCOPE: the export is cut at 2024-12-31 at load (asserted in
esr_lib); nothing under DATA is modified or deleted; the runner is never imported; no network; no subagent."""
from __future__ import annotations
import json, sys, time
import numpy as np, pandas as pd
HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_trail_variants_1023"
PREV = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_entry_stop_retry_1022"
sys.path.insert(0, HERE)
from trail_lib import (Frame, ERAS, HORIZON, walk_chain_v, add_sma, load_pops, summarize, matched_means, month_block_ci, account_view, log,
                       all_cells, cell_key)

STOP, VARIANT = "S2", "close"
BASE = (20, "X1", "P1")
MEAS0 = ["r_sum", "adr_sum", "f_realized_r", "f_pnl_adr", "f_width_adr", "win", "any5", "any10", "n_tr", "retries", "retry_after_be", "trunc",
         "f_stopped", "f_cut", "f_trailed", "f_censored", "f_degraded", "f_third", "f_tiny", "held"]
RACE_MEAS = ["f_race2_hit", "f_race5_hit", "f_race10_hit", "f_race2_stop", "f_race5_stop", "f_race10_stop", "f_race2_r", "f_race5_r", "f_race10_r"]
DIFF0 = [("r_sum", "r_per_base"), ("adr_sum", "adr_per_base"), ("f_realized_r", "first_r"), ("f_pnl_adr", "first_adr"), ("win", "win"), ("any5", "any5"), ("any10", "any10")]
DIFF_RACE = [("f_race2_hit", "race2_hit"), ("f_race5_hit", "race5_hit"), ("f_race10_hit", "race10_hit"), ("f_race2_r", "race2_r"), ("f_race5_r", "race5_r"), ("f_race10_r", "race10_r")]
PCT_SCALE = ("win", "any5", "any10", "race2_hit", "race5_hit", "race10_hit")


def q(x, qs=(0.25, 0.5, 0.75)):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return [float(np.quantile(x, v)) for v in qs] if len(x) else [np.nan] * len(qs)


def tq(x):
    """per-trade distribution: n, worst, p1, p5, p10, p25, median, p75, p95, best, mean"""
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if len(x) == 0:
        return dict(n=0, worst=np.nan, p1=np.nan, p5=np.nan, p10=np.nan, p25=np.nan, median=np.nan, p75=np.nan, p95=np.nan, best=np.nan, mean=np.nan)
    p = np.percentile(x, [1, 5, 10, 25, 50, 75, 95])
    return dict(n=int(len(x)), worst=float(x.min()), p1=float(p[0]), p5=float(p[1]), p10=float(p[2]), p25=float(p[3]), median=float(p[4]), p75=float(p[5]), p95=float(p[6]), best=float(x.max()), mean=float(x.mean()))


def compare(G, ref, path="", acc=None):
    """numeric leaves of ref that exist in G: max |G − ref|; ref keys missing in G are listed (new measures in G are ignored)"""
    if acc is None:
        acc = dict(n=0, maxd=0.0, worst="", missing=[])
    if isinstance(ref, dict):
        for k, v in ref.items():
            if not isinstance(G, dict) or k not in G:
                acc["missing"].append(path + "/" + str(k)); continue
            compare(G[k], v, path + "/" + str(k), acc)
    elif isinstance(ref, list):
        if not isinstance(G, list) or len(G) != len(ref):
            acc["missing"].append(path + " (list)"); return acc
        for i, (g, r) in enumerate(zip(G, ref)):
            compare(g, r, f"{path}[{i}]", acc)
    elif isinstance(ref, (int, float)) and not isinstance(ref, bool):
        g = float(G) if isinstance(G, (int, float, np.floating, np.integer)) else np.nan
        r = float(ref)
        if np.isnan(r) and np.isnan(g):
            d = 0.0
        else:
            d = abs(g - r)
        acc["n"] += 1
        if not (d <= acc["maxd"]):
            acc["maxd"] = d; acc["worst"] = path
    elif isinstance(ref, str):
        acc["n"] += 1
        if str(G) != ref:
            acc["maxd"] = np.inf; acc["worst"] = path
    return acc


def build(era):
    cfg = ERAS[era]; data = cfg["data"]; sink = []
    log(f"== {era}", sink)
    F = Frame(data, cfg["cut"], sink); add_sma(F, 10)
    last = F.last
    win, r1, ctl, cells = load_pops(era, F, sink)
    # the saved seed-702 control draw of the 10-22 read must be the one re-derived here (same control rows, same order)
    for es in ("R1", "R2"):
        saved = pd.read_csv(f"{PREV}/02_sample_{es}_{era}.tsv", sep="\t")
        assert np.array_equal(saved[es].to_numpy(), cells[es]["sample"]) and np.array_equal(saved[f"ent_index_{es}"].to_numpy(), cells[es]["ent_index"]), f"the saved {es} control draw differs"
    assert len(ctl) == (2096517 if era == "2017-21" else 1469399), len(ctl)
    log(f"  the saved seed-702 control draws (R1 {len(cells['R1']['sample'])}, R2 {len(cells['R2']['sample'])}) re-derived equal; control n {len(ctl):,}", sink)
    sample_ids = np.unique(np.concatenate([cells["R1"]["sample"], cells["R2"]["sample"]])); sample_ids = sample_ids[sample_ids >= 0]
    ref = json.load(open(f"{PREV}/02_numbers_{era}.json"))["grid"]["S2_close"]
    numbers = dict(era=era, sessions=len(F.cal), cal_first=F.cal[0], cal_last=F.cal[-1], last_idx=int(last), stop=STOP, variant=VARIANT,
                   win=dict(n=int(len(win)), complete120=int(win.complete120.sum()), ext_truncated=int(win.ext_truncated.sum()), pub_triggered=int(win.triggered.sum()),
                            pub_still_in_s50=int(win.still_in_s50.fillna(0).sum()), pub_kept_half=int(win.kept_half_episode.fillna(0).sum()), gain_med=float(win.gain.median()),
                            adr_bprev_med=float(win.adr20_bprev.median()), L_med=float(win.L_p.median()), s50_minus_b_q=q((win.s50 - win.b_p).to_numpy()), p_minus_b_q=q((win.p - win.b_p).to_numpy())),
                   r1=dict(n=int(len(r1)), n_r2=int(r1.r2_exp.sum()), complete=int(r1.complete120.sum()), complete_r2=int(r1[r1.complete120 == 1].r2_exp.sum()), days=int(r1.t.nunique()),
                           first=r1.entry_date.min(), last=r1.entry_date.max(), complete_first=r1[r1.complete120 == 1].entry_date.min(), complete_last=r1[r1.complete120 == 1].entry_date.max(),
                           weeks_complete=float((r1[r1.complete120 == 1].t.max() - r1[r1.complete120 == 1].t.min() + 1) / 5)),
                   ctl=dict(n=int(len(ctl)), complete=int(ctl.complete120.sum())), cells=[cell_key(*c) for c in all_cells()], grid={})
    win_rows, r1_rows, samp_rows, match_rows = [], [], [], []
    s50 = win.s50.to_numpy(); gain_ps = (win.close_p - win.close_t).to_numpy(); nwin = len(win)
    ctl_complete = ctl.complete120.to_numpy()
    for (n_avg, trig, part) in all_cells():
        t0 = time.time(); key = cell_key(n_avg, trig, part); is_base = (n_avg, trig, part) == BASE; G = dict(sma_n=n_avg, trigger=trig, partial=part)
        # ── P-win ────────────────────────────────────────────────────────────────────────────────
        chw = walk_chain_v(F, win.b_p.to_numpy(), win.tj.to_numpy(), win.base_high_p.to_numpy("float32"), win.base_low_p.to_numpy("float32"), STOP, VARIANT, n_avg, trig, part, 2, with_race=False)
        chw["ticker"] = win.ticker.to_numpy()[chw.base]; chw["cell"] = key
        win_rows.append(chw)
        G["win"] = {}
        f0w = chw[chw.attempt == 0]
        G["win"]["width_adr_q"] = q(((f0w.fill - f0w.stop0) / (F.ADR[f0w.bday - 1, win.tj.to_numpy()[f0w.base]] * f0w.fill)).to_numpy()); G["win"]["n_skipped_first"] = int((f0w.status == -1).sum())
        for T in (0, 1, 2):
            s = summarize(chw, T, nwin)
            d = chw[(chw.attempt <= T) & (chw.status >= 0)]
            inat = ((d.e.to_numpy() <= s50[d.base]) & (d.exit_idx.to_numpy() >= s50[d.base]))
            still = pd.Series(inat).groupby(d.base.to_numpy()).any().reindex(range(nwin)).fillna(False).to_numpy()
            kept = d.groupby("base").pnl_ps.sum().reindex(range(nwin)).to_numpy() / gain_ps
            valid = s.f_valid.to_numpy() == 1
            fs = s.f_status.to_numpy(); fx = s.f_exit_idx.to_numpy()
            held_tr = (d.exit_idx - d.e).to_numpy()
            G["win"][f"T{T}"] = dict(n=int(valid.sum()), still_in_s50=int(still[valid].sum()), kept_half=int((kept[valid] >= 0.5).sum()), kept_quarter=int((kept[valid] >= 0.25).sum()),
                                    kept_share_q=q(kept[valid]), kept_share_mean=float(np.nanmean(kept[valid])),
                                    held_chain_q=q(s.held[valid]), held_first_q=q(s.f_exit_idx[valid] - s.f_e[valid]), held_trade_q=q(held_tr),
                                    first_status_mix={str(k): int(v) for k, v in pd.Series(fs[valid]).value_counts().to_dict().items()},
                                    first_trail_kind_mix={str(k): int(v) for k, v in pd.Series(s.f_trail_kind[valid]).value_counts().to_dict().items()},
                                    all_status_mix={str(k): int(v) for k, v in d.status.value_counts().to_dict().items()},
                                    all_trail_kind_mix={str(k): int(v) for k, v in d.trail_kind.value_counts().to_dict().items()},
                                    first_stopped_before_s50=int(((fs == 1) & (fx < s50))[valid].sum()), first_cut=int((fs == 2)[valid].sum()), first_stopped_any=int((fs == 1)[valid].sum()),
                                    first_trailed_before_s50=int(((fs == 3) & (fx < s50))[valid].sum()),
                                    retries_mean=float(s.retries[valid].mean()), used1=int((s.retries[valid] == 1).sum()), used2=int((s.retries[valid] == 2).sum()),
                                    retry_after_be=int(s.retry_after_be[valid].sum()), trunc=int(s.trunc[valid].sum()), adr_sum_mean=float(s.adr_sum[valid].mean()),
                                    chain_r_mean=float(s.r_sum[valid].mean()), chain_r_q=q(s.r_sum[valid]), any5=int(s.any5[valid].sum()), any10=int(s.any10[valid].sum()),
                                    still_in_s50_needing_retry=int((still & (s.retries.to_numpy() >= 1))[valid].sum()),
                                    kept_half_needing_retry=int(((kept >= 0.5) & (s.retries.to_numpy() >= 1))[valid].sum()),
                                    kept_quarter_needing_retry=int(((kept >= 0.25) & (s.retries.to_numpy() >= 1))[valid].sum()),
                                    trade_r=tq(d.realized_r), hit2r_first=int(np.nansum(chw[chw.attempt == 0].hit2r)))
        # ── P-all and P-ctl ──────────────────────────────────────────────────────────────────────
        chr_ = walk_chain_v(F, r1.t.to_numpy(), r1.tj.to_numpy(), r1.pivot_full.to_numpy("float32"), r1.base_low.to_numpy("float32"), STOP, VARIANT, n_avg, trig, part, 2, with_race=is_base)
        chr_["ticker"] = r1.ticker.to_numpy()[chr_.base]; chr_["cell"] = key
        r1_rows.append(chr_)
        rt = chr_[(chr_.attempt >= 1) & (chr_.status >= 0)]
        G["r1_retry_trades"] = int(len(rt))
        chc = walk_chain_v(F, ctl.ci.to_numpy(), ctl.tj.to_numpy(), ctl.proxy_hi.to_numpy("float32"), ctl.proxy_lo.to_numpy("float32"), STOP, VARIANT, n_avg, trig, part, 2, with_race=is_base)
        sm = chc[chc.base.isin(sample_ids)].copy(); sm["ticker"] = ctl.ticker.to_numpy()[sm.base]; sm["cell"] = key
        samp_rows.append(sm)
        MEAS = MEAS0 + (RACE_MEAS if is_base else [])
        DIFFS = DIFF0 + (DIFF_RACE if is_base else [])
        sums_r1 = {T: summarize(chr_, T, len(r1)) for T in (0, 1, 2)}
        sums_c = {T: summarize(chc, T, len(ctl)) for T in (0, 1, 2)}
        f0 = chr_[chr_.attempt == 0]
        G["r1_width_adr_q"] = q(((f0.fill - f0.stop0) / (r1.adr_t1.to_numpy()[f0.base] * f0.fill)).to_numpy())
        G["r1_skipped_first"] = int((f0.status == -1).sum()); G["ctl_skipped_first"] = int((sums_c[0].f_valid != 1).sum())
        # the FULL control's per-trade distribution, per T, complete bases and all
        G["ctl_trade_r"] = {}
        for T in (0, 1, 2):
            dc = chc[(chc.attempt <= T) & (chc.status >= 0)]
            G["ctl_trade_r"][f"T{T}"] = dict(all=tq(dc.realized_r), complete=tq(dc.realized_r[ctl_complete[dc.base] == 1]),
                                             held_trade_q_complete=q((dc.exit_idx - dc.e).to_numpy()[ctl_complete[dc.base] == 1]),
                                             status_mix_complete={str(k): int(v) for k, v in dc.status[ctl_complete[dc.base] == 1].value_counts().to_dict().items()})
        for es in ("R1", "R2"):
            C = cells[es]; eidx = C["ent_index"]; ent = r1.loc[eidx]
            for T in (0, 1, 2):
                se = sums_r1[T].loc[eidx].reset_index(drop=True); sc = sums_c[T]
                mm_all, fb_all = matched_means(C["ek"], C["ck"], sc, MEAS)
                for comp in ("complete", "all"):
                    keep = (ent.complete120.to_numpy() == 1) if comp == "complete" else np.ones(len(ent), bool)
                    keep &= se.f_valid.to_numpy() == 1
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
                                 retries_mean=float(np.nanmean(S.retries)), retry_after_be=float(np.nansum(S.retry_after_be)), trunc=float(np.nansum(S.trunc)),
                                 held_mean=float(np.nanmean(S.held)))
                        if is_base:
                            for k in (2, 5, 10):
                                o[f"race{k}_hit"] = float(np.nanmean(S[f"f_race{k}_hit"])); o[f"race{k}_stop"] = float(np.nanmean(S[f"f_race{k}_stop"])); o[f"race{k}_r"] = float(np.nanmean(S[f"f_race{k}_r"]))
                        return o
                    ent_s = summ(E); ctl_s = summ(M)
                    dtr = chr_[(chr_.attempt <= T) & (chr_.status >= 0) & np.isin(chr_.base, eidx[keep])]
                    ent_s.update(ge5_per100_trades=float(100 * (dtr.realized_r >= 5).mean()), ge10_per100_trades=float(100 * (dtr.realized_r >= 10).mean()),
                                 r_per_trade_median=float(dtr.realized_r.median()), win_per_trade=float((dtr.realized_r > 0).mean()), r_per_base_median=float(np.nanmedian(E.r_sum)),
                                 all_status_mix={str(k): int(v) for k, v in dtr.status.value_counts().to_dict().items()},
                                 all_pkind_mix={str(k): int(v) for k, v in dtr.pkind.value_counts().to_dict().items()},
                                 all_trail_kind_mix={str(k): int(v) for k, v in dtr.trail_kind.value_counts().to_dict().items()},
                                 width_q=q(E.f_width_adr, (0.05, 0.1, 0.25, 0.5, 0.75)),
                                 r_top5_share=float(dtr.realized_r.nlargest(5).sum() / dtr.realized_r.sum()) if dtr.realized_r.sum() else np.nan,
                                 trade_r=tq(dtr.realized_r), held_trade_q=q((dtr.exit_idx - dtr.e).to_numpy()), held_chain_q=q(E.held),
                                 r_per_base_q=q(E.r_sum, (0.05, 0.25, 0.5, 0.75, 0.95)), r_per_base_worst=float(np.nanmin(E.r_sum)))
                    if is_base:
                        ent_s["race_complete"] = int(np.nansum(E.f_race_complete))
                    ctl_s.update(width_q=q(sc.f_width_adr, (0.05, 0.1, 0.25, 0.5, 0.75)))
                    diffs = {}
                    for col, name in DIFFS:
                        dv = E[col].to_numpy(float) - M[col].to_numpy(float)
                        scale = 100.0 if name in PCT_SCALE else 1.0
                        m_, lo, hi, nn = month_block_ci(dv * scale, months)
                        diffs[name] = dict(diff=m_, lo=lo, hi=hi, n=nn)
                    acc = account_view(dtr.realized_r.to_numpy(), dtr.exit_idx.to_numpy(), dtr.e.to_numpy())
                    sids = C["sample"][keep]
                    sm_k = sm[(sm.attempt <= T) & (sm.status >= 0) & sm.base.isin(sids)]
                    mult = pd.Series(sids).value_counts()
                    wts = sm_k.base.map(mult).fillna(0).to_numpy()
                    rr = np.repeat(sm_k.realized_r.to_numpy(), wts.astype(int)); xx = np.repeat(sm_k.exit_idx.to_numpy(), wts.astype(int)); ee = np.repeat(sm_k.e.to_numpy(), wts.astype(int))
                    acc_c = account_view(rr, xx, ee)
                    G[f"{es}_T{T}_{comp}"] = dict(entries=ent_s, control=ctl_s, diff=diffs, fallback=fb, account=acc, account_control=acc_c, weeks=float(weeks) if weeks else np.nan,
                                                  sample_trade_r=tq(rr))
                    if comp == "complete":
                        mr = M.copy(); mr.insert(0, "ent_index", eidx[keep]); mr.insert(0, "T", T); mr.insert(0, "es", es); mr.insert(0, "cell", key)
                        match_rows.append(mr)
        del chc
        numbers["grid"][key] = G
        if is_base:
            acc_ = compare(G, ref)
            # keys the 10-22 JSON has and this build does not compute by design: the ≥ 0.25-ADR width-floor arm (identical to 'complete' on S2) and the T1/T2 'complete_w025' arms
            missing = [m for m in acc_["missing"] if "complete_w025" not in m and "r1_retry_is_another_r1" not in m and "r1_width_adr_q_r2" not in m and "ctl_width_adr_q" not in m]
            log(f"  PARITY (c) the pp baseline cell {key} vs 02_numbers_{era}.json['grid']['S2_close']: {acc_['n']} numeric leaves compared, max |diff| {acc_['maxd']:.3g} at '{acc_['worst']}'; "
                f"ref keys not computed here {len(acc_['missing'])} (by design: the ≥ 0.25-ADR arm, the retry-overlap count, the control width quantiles; unexpected: {missing})", sink)
            assert acc_["maxd"] <= 1e-9 and not missing, "PARITY (c) FAILED — the build stops before any new arm is read"
        R1c = G["R1_T2_complete"]; R1c0 = G["R1_T0_complete"]
        log(f"  {key}: {time.time()-t0:.0f}s; P-win T2 still-in {G['win']['T2']['still_in_s50']}/{G['win']['T2']['n']} kept-½ {G['win']['T2']['kept_half']} kept-¼ {G['win']['T2']['kept_quarter']} "
            f"kept-share med {G['win']['T2']['kept_share_q'][1]:.3f} held med {G['win']['T2']['held_chain_q'][1]:.0f}; R1 T0 r/trade {R1c0['entries']['r_per_trade']:+.3f} vs ctl {R1c0['control']['r_per_trade']:+.3f} "
            f"worst {R1c0['entries']['trade_r']['worst']:+.2f} p5 {R1c0['entries']['trade_r']['p5']:+.2f}; T2 r/base {R1c['entries']['r_per_base']:+.3f} vs {R1c['control']['r_per_base']:+.3f} "
            f"diff {R1c['diff']['r_per_base']['diff']:+.3f} ({R1c['diff']['r_per_base']['lo']:+.3f} .. {R1c['diff']['r_per_base']['hi']:+.3f}); ≥5R/100 bases {R1c['entries']['any5_per100']:.1f} vs {R1c['control']['any5_per100']:.1f}", sink)
    # ── write ────────────────────────────────────────────────────────────────────────────────────
    W = pd.concat(win_rows, ignore_index=True)
    for c in ("t", "s50", "p", "close_t", "close_p", "gain", "adr20_bprev", "L_p", "base_high_p", "base_low_p", "complete120"):
        W[c] = win[c].to_numpy()[W.base]
    W.to_csv(f"{data}/out/trail_win_{era}.tsv.gz", sep="\t", index=False, float_format="%.7g")
    R = pd.concat(r1_rows, ignore_index=True)
    for c in ("t", "entry_date", "r2_exp", "adr_t1", "ret63_t1", "pivot_full", "base_low", "base_len", "complete120"):
        R[c] = r1[c].to_numpy()[R.base]
    R.to_csv(f"{data}/out/trail_r1_{era}.tsv.gz", sep="\t", index=False, float_format="%.7g")
    SM = pd.concat(samp_rows, ignore_index=True)
    SM["ci"] = ctl.ci.to_numpy()[SM.base]; SM["complete120"] = ctl.complete120.to_numpy()[SM.base]
    SM.to_csv(f"{data}/out/trail_ctlsample_{era}.tsv.gz", sep="\t", index=False, float_format="%.7g")
    MR = pd.concat(match_rows, ignore_index=True)
    MR.to_parquet(f"{data}/out/trail_ctlmatch_{era}.parquet", index=False)
    log(f"  wrote trail_win ({len(W)} rows), trail_r1 ({len(R)}), trail_ctlsample ({len(SM)}), trail_ctlmatch ({len(MR)})", sink)
    with open(f"{HERE}/02_numbers_{era}.json", "w") as fh:
        json.dump(numbers, fh, indent=1, default=lambda o: float(o) if isinstance(o, (np.floating, np.integer)) else str(o))
    with open(f"{HERE}/02_build_{era}.log", "w") as fh:
        fh.write("\n".join(sink) + "\n")


if __name__ == "__main__":
    for era in (sys.argv[1:] or list(ERAS)):
        build(era)
