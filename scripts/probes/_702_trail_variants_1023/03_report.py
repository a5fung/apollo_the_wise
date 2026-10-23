"""#705 Track B — step 3: the tables, from 02_numbers_<era>.json (no bar is re-read). Writes 03_report.md (every table, n on every row) and
03_headline.json (the numbers the doc's lead quotes)."""
import json
import numpy as np

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_trail_variants_1023"
ERAS = ("2017-21", "2022-24")
out, head = [], {}


def P(s=""):
    out.append(s)


def tbl(headers, rows):
    P("| " + " | ".join(headers) + " |"); P("|" + "---|" * len(headers))
    for r in rows:
        P("| " + " | ".join(str(x) for x in r) + " |")
    P()


def f(x, d=2, sign=False):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:+.{d}f}" if sign else f"{x:.{d}f}"


def pct(x, d=0):
    return "—" if x is None or not np.isfinite(x) else f"{100*x:.{d}f}%"


def ci(d, d_=3, scale=1.0, unit=""):
    return f"{d['diff']*scale:+.{d_}f} ({d['lo']*scale:+.{d_}f} .. {d['hi']*scale:+.{d_}f}){unit}"


def cname(G):
    t = {"X1": "X1 close below", "X2": "X2 decisive", "X3": "X3 reclaim forgiven", "X4": "X4 intraday"}[G["trigger"]]
    return f"{G['sma_n']}-day · {t} · {G['partial']}" + (" **(= pp)**" if (G["sma_n"], G["trigger"], G["partial"]) == (20, "X1", "P1") else "")


for era in ERAS:
    J = json.load(open(f"{HERE}/02_numbers_{era}.json"))
    head[era] = {}
    W, R, C = J["win"], J["r1"], J["ctl"]
    cells = J["cells"]; G_ = J["grid"]
    P(f"## {era}")
    P()
    P(f"### Composition ({era}; sessions {J['cal_first']}..{J['cal_last']}, {J['sessions']}; entry at the breakout close, stop = entry − 1.0 ADR20, up to two retries)")
    P()
    tbl(["population", "n", "detail"], [
        ["P-win: covered measurable-breakout doublers", f"n = {W['n']}", f"b + 120 past the last readable {W['n'] - W['complete120']}; peak extension truncated {W['ext_truncated']}; gain median +{100*W['gain_med']:.0f}%; sessions from the breakout day to half the gain (s50 − b) median {W['s50_minus_b_q'][1]:.0f} ({W['s50_minus_b_q'][0]:.0f} .. {W['s50_minus_b_q'][2]:.0f}); to the peak {W['p_minus_b_q'][1]:.0f} ({W['p_minus_b_q'][0]:.0f} .. {W['p_minus_b_q'][2]:.0f}); the published catch (tl ORH5 + pp): triggered {W['pub_triggered']}, still in at s50 {W['pub_still_in_s50']}, kept half {W['pub_kept_half']}"],
        ["P-all: R1 real breakouts", f"n = {R['n']}", f"{R['days']} entry days {R['first']}..{R['last']}; R2 expansion subset {R['n_r2']}; COMPLETE (t + 120 ≤ last) {R['complete']} (R2 {R['complete_r2']}), entry days {R['complete_first']}..{R['complete_last']} = {R['weeks_complete']:.0f} weeks"],
        ["P-ctl: matched control rows on those days", f"n = {C['n']:,}", f"complete {C['complete']:,}; the same (day, ADR decile, 63-session-return quintile) cells and the same seed-702 account-view draw as the 10-22 read"],
    ])
    # ── P-win ──
    for T in (2, 0):
        P(f"### P-win — the covered doublers, {'up to two retries (T2)' if T == 2 else 'no retry (T0)'} ({era}; n on every row; s50 = the session the close first made half the gain; 'held' = sessions from entry to exit, summed over the chain, median over bases)")
        P()
        rows = []
        for k in cells:
            G = G_[k]; w = G["win"][f"T{T}"]; n = w["n"]
            fm = w["first_trail_kind_mix"]; am = w["all_trail_kind_mix"]
            rows.append([cname(G), f"n = {n}", f"{w['still_in_s50']} ({100*w['still_in_s50']/n:.0f}%)", f"{w['kept_half']} ({100*w['kept_half']/n:.0f}%)", f"{w['kept_quarter']} ({100*w['kept_quarter']/n:.0f}%)",
                         f"{w['kept_share_q'][1]:.3f} ({w['kept_share_q'][0]:.3f} .. {w['kept_share_q'][2]:.3f}); mean {w['kept_share_mean']:.3f}",
                         f"{w['held_chain_q'][1]:.0f} ({w['held_chain_q'][0]:.0f} .. {w['held_chain_q'][2]:.0f}); first trade {w['held_first_q'][1]:.0f}",
                         f"{w['first_stopped_before_s50']} / {w['first_cut']} / {w['first_trailed_before_s50']}",
                         "—" if T == 0 else f"{w['retries_mean']:.2f} (1: {w['used1']}, 2: {w['used2']})",
                         f"{w['chain_r_mean']:+.2f} / {w['chain_r_q'][1]:+.2f}", f"{w['any5']} / {w['any10']}",
                         f"worst {w['trade_r']['worst']:+.2f}, p5 {w['trade_r']['p5']:+.2f}, n = {w['trade_r']['n']}",
                         "; ".join(f"{ {'1':'close','2':'decisive','3':'2 closes','4':'reclaim expired','5':'intraday level'}[kk] } {vv}" for kk, vv in sorted(am.items()) if kk != "0") or "—", w["trunc"]])
        tbl(["cell", "bases", "still in a trade at s50", "chain kept ≥ ½ of the gain", "kept ≥ ¼", "kept share of the gain: median (quartiles); mean", "sessions held: chain median (quartiles); first trade median",
             "first trade: stopped before s50 / cut at session 3 / trailed out before s50", "retries used: mean (bases using 1 / 2)", "chain R mean / median", "bases with a ≥ 5R / ≥ 10R trade",
             "per-trade R: worst, 5th percentile", "trail exits by kind (all chain trades)", "chains marked at the cut"], rows)
    # ── P-all vs P-ctl ──
    for es in ("R1", "R2"):
        for T in (0, 2):
            for comp in ("complete", "all"):
                if comp == "all" and (es == "R2" or T == 0):
                    continue
                g0 = G_[cells[0]][f"{es}_T{T}_{comp}"]
                P(f"### P-all {es} vs P-ctl — {'no retry (T0; the clean comparison)' if T == 0 else 'up to two retries (T2; ⚠ the control-retry caveat of the 10-22 read applies: the control re-enters at its 20-session prior high, a different event from the base high)'}, "
                  f"{'COMPLETE bases (t + 120 ≤ the last readable session)' if comp == 'complete' else 'ALL bases, open chains marked at the last readable close'} ({era}; n = {g0['entries']['n']} bases, {g0['weeks']:.0f} weeks; control = the matched cell mean; intervals = month-block bootstrap, seed 702, 2,000)")
                P()
                rows = []
                for k in cells:
                    G = G_[k]; g = G[f"{es}_T{T}_{comp}"]; E, M, D = g["entries"], g["control"], g["diff"]
                    rows.append([cname(G), f"n = {E['n']}", f"{E['trades_per_week']:.1f} (ctl {M['trades_per_week']:.1f})",
                                 f"{E['any5_per100']:.1f} vs {M['any5_per100']:.1f}; {ci(D['any5'], 1)}", f"{E['any10_per100']:.1f} vs {M['any10_per100']:.1f}; {ci(D['any10'], 1)}",
                                 f"{E['ge5_per100_trades']:.1f} / {E['ge10_per100_trades']:.1f}",
                                 f"{E['r_per_trade']:+.3f} vs {M['r_per_trade']:+.3f}", f"{E['r_per_base']:+.3f} vs {M['r_per_base']:+.3f}; {ci(D['r_per_base'])}",
                                 f"{E['r_per_trade_median']:+.2f}", f"{pct(E['win_per_trade'])} vs {pct(M['win'])} (first trade); {ci(D['win'], 1, unit=' pts')}",
                                 f"{E['trade_r']['worst']:+.2f} / {E['trade_r']['p5']:+.2f} (n = {E['trade_r']['n']})",
                                 f"{G['ctl_trade_r'][f'T{T}'][comp]['worst']:+.2f} / {G['ctl_trade_r'][f'T{T}'][comp]['p5']:+.2f} (n = {G['ctl_trade_r'][f'T{T}'][comp]['n']:,}); sample worst {g['sample_trade_r']['worst']:+.2f}",
                                 f"{E['held_trade_q'][1]:.0f} ({E['held_trade_q'][0]:.0f} .. {E['held_trade_q'][2]:.0f}) vs {G['ctl_trade_r'][f'T{T}']['held_trade_q_complete'][1]:.0f}" if comp == "complete" else f"{E['held_trade_q'][1]:.0f}",
                                 f"{pct(E['stopped'])} / {pct(E['cut'])} / {pct(E['trailed'])}",
                                 f"{g['account']['total_pct']:+.0f}% / {g['account']['max_dd_pct']:.0f}% / {g['account']['open_median']:.0f} ({g['account']['open_max']:.0f})",
                                 f"{g['account_control']['total_pct']:+.0f}% / {g['account_control']['max_dd_pct']:.0f}%", f"{E['r_top5_share']*100:.0f}%" if np.isfinite(E['r_top5_share']) and E['r_top5_share'] > 0 else "—"])
                tbl(["cell", "bases", "trades / week", "≥ 5R bases per 100: entries vs control; diff (95%)", "≥ 10R bases per 100; diff", "≥ 5R / ≥ 10R per 100 trades", "mean R per trade: entries vs control",
                     "mean R per base; diff (95%)", "median R per trade", "win rate per trade; first-trade diff", "entries' per-trade R: worst / 5th percentile", "control's per-trade R: worst / 5th percentile (full control); the seed-702 sample's worst",
                     "sessions held per trade: median (quartiles) vs control", "first-trade exit: stopped / cut / trailed", "account (0.5% risk, additive): total / worst drawdown / open at once median (max)", "control book: total / drawdown", "5 best trades ÷ total R"], rows)
    # headline numbers
    for k in cells:
        G = G_[k]
        head[era][k] = dict(win_T2={kk: G["win"]["T2"][kk] for kk in ("n", "still_in_s50", "kept_half", "kept_quarter", "kept_share_q", "held_chain_q", "any5", "any10", "chain_r_mean", "first_stopped_before_s50", "first_cut", "first_trailed_before_s50", "retries_mean")},
                            win_T0={kk: G["win"]["T0"][kk] for kk in ("n", "still_in_s50", "kept_half", "kept_quarter", "kept_share_q", "held_chain_q")},
                            R1_T0=dict(n=G["R1_T0_complete"]["entries"]["n"], tpw=G["R1_T0_complete"]["entries"]["trades_per_week"], r_trade=G["R1_T0_complete"]["entries"]["r_per_trade"], r_trade_ctl=G["R1_T0_complete"]["control"]["r_per_trade"],
                                       diff=G["R1_T0_complete"]["diff"]["r_per_base"], any5=G["R1_T0_complete"]["entries"]["any5_per100"], any5_ctl=G["R1_T0_complete"]["control"]["any5_per100"], any5_diff=G["R1_T0_complete"]["diff"]["any5"],
                                       any10=G["R1_T0_complete"]["entries"]["any10_per100"], any10_ctl=G["R1_T0_complete"]["control"]["any10_per100"], any10_diff=G["R1_T0_complete"]["diff"]["any10"],
                                       worst=G["R1_T0_complete"]["entries"]["trade_r"]["worst"], p5=G["R1_T0_complete"]["entries"]["trade_r"]["p5"], ctl_worst=G["ctl_trade_r"]["T0"]["complete"]["worst"], ctl_p5=G["ctl_trade_r"]["T0"]["complete"]["p5"],
                                       win=G["R1_T0_complete"]["entries"]["win_per_trade"], win_ctl=G["R1_T0_complete"]["control"]["win"], held=G["R1_T0_complete"]["entries"]["held_trade_q"][1], held_ctl=G["ctl_trade_r"]["T0"]["held_trade_q_complete"][1],
                                       acc=G["R1_T0_complete"]["account"], acc_ctl=G["R1_T0_complete"]["account_control"], median_trade=G["R1_T0_complete"]["entries"]["r_per_trade_median"]),
                            R1_T2=dict(n=G["R1_T2_complete"]["entries"]["n"], tpw=G["R1_T2_complete"]["entries"]["trades_per_week"], r_trade=G["R1_T2_complete"]["entries"]["r_per_trade"], r_trade_ctl=G["R1_T2_complete"]["control"]["r_per_trade"],
                                       r_base=G["R1_T2_complete"]["entries"]["r_per_base"], r_base_ctl=G["R1_T2_complete"]["control"]["r_per_base"], diff=G["R1_T2_complete"]["diff"]["r_per_base"],
                                       any5=G["R1_T2_complete"]["entries"]["any5_per100"], any5_ctl=G["R1_T2_complete"]["control"]["any5_per100"], any5_diff=G["R1_T2_complete"]["diff"]["any5"],
                                       worst=G["R1_T2_complete"]["entries"]["trade_r"]["worst"], p5=G["R1_T2_complete"]["entries"]["trade_r"]["p5"], acc=G["R1_T2_complete"]["account"], acc_ctl=G["R1_T2_complete"]["account_control"]),
                            R2_T0=dict(n=G["R2_T0_complete"]["entries"]["n"], tpw=G["R2_T0_complete"]["entries"]["trades_per_week"], r_trade=G["R2_T0_complete"]["entries"]["r_per_trade"], r_trade_ctl=G["R2_T0_complete"]["control"]["r_per_trade"],
                                       diff=G["R2_T0_complete"]["diff"]["r_per_base"], any5_diff=G["R2_T0_complete"]["diff"]["any5"], worst=G["R2_T0_complete"]["entries"]["trade_r"]["worst"], p5=G["R2_T0_complete"]["entries"]["trade_r"]["p5"]),
                            R2_T2=dict(n=G["R2_T2_complete"]["entries"]["n"], diff=G["R2_T2_complete"]["diff"]["r_per_base"], any5_diff=G["R2_T2_complete"]["diff"]["any5"]))
open(f"{HERE}/03_report.md", "w").write("\n".join(out) + "\n")
json.dump(head, open(f"{HERE}/03_headline.json", "w"), indent=1)
print(f"wrote {len(out)} lines")
