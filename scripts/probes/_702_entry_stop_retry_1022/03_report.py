"""#705 entry/stop/retry — step 3: the tables, from 02_numbers_<era>.json (no bar is re-read). Writes 03_report.md (every table, n on every
row) and 03_headline.json (the numbers the doc's lead quotes)."""
import json, os, sys
import numpy as np

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_entry_stop_retry_1022"
ERAS = tuple(sys.argv[1:]) or ("2017-21", "2022-24")      # optional: an era argument limits the run
LOG_DIR = os.environ.get("CB_PRE_LOG", HERE)             # optional re-run switch (2017-21 only): where 02_numbers_<era>.json is read and the report is written
assert LOG_DIR == HERE or ERAS == ("2017-21",), "CB_PRE_LOG re-runs the 2017-21 era only"
STOPS = ("S1", "S2", "S3", "S4")
STOP_NAME = {"S1": "S1 breakout-day low", "S2": "S2 entry − 1.0 ADR", "S3": "S3 entry − 1.5 ADR", "S4": "S4 base low"}
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


def ci(d, d_=2, scale=1.0, unit=""):
    return f"{d['diff']*scale:+.{d_}f} ({d['lo']*scale:+.{d_}f} .. {d['hi']*scale:+.{d_}f}){unit}"


def qs(qv, d=2):
    return f"{qv[1]:.{d}f} ({qv[0]:.{d}f} .. {qv[2]:.{d}f})"


for era in ERAS:
    try:
        J = json.load(open(f"{LOG_DIR}/02_numbers_{era}.json"))
    except FileNotFoundError:
        continue
    head[era] = {}
    W, R, C = J["win"], J["r1"], J["ctl"]
    P(f"## {era}")
    P()
    P(f"### Composition ({era}; sessions {J['cal_first']}..{J['cal_last']}, {J['sessions']})")
    P()
    tbl(["population", "n", "detail"], [
        ["P-win: covered measurable-breakout doublers", f"n = {W['n']}", f"b + 120 sessions past the last readable {W['n'] - W['complete120']}; peak extension truncated {W['ext_truncated']}; gain median +{100*W['gain_med']:.0f}%; base length median {W['L_med']:.0f}; ADR20 at b−1 median {100*W['adr_bprev_med']:.1f}%; the published catch (tl ORH5 + pp): triggered {W['pub_triggered']}, still in at s50 {W['pub_still_in_s50']}, kept half {W['pub_kept_half']}"],
        ["P-all: R1 real breakouts (one per ticker × day)", f"n = {R['n']}", f"{R['days']} entry days {R['first']}..{R['last']}; R2 expansion subset {R['n_r2']}; COMPLETE (t + 120 ≤ last) {R['complete']} (R2 {R['complete_r2']}), entry days {R['complete_first']}..{R['complete_last']} = {R['weeks_complete']:.0f} weeks; base length median {R['base_len_q'][1]:.0f} ({R['base_len_q'][0]:.0f} .. {R['base_len_q'][2]:.0f}); ADR20 median {100*R['adr_q'][1]:.1f}%; 63-session return median {100*R['ret63_q'][1]:.0f}%"],
        ["P-ctl: matched control rows on those days", f"n = {C['n']:,}", f"complete {C['complete']:,}; ADR20 median {100*C['adr_q'][1]:.1f}%; 63-session return median {100*C['ret63_q'][1]:.0f}%; R1 cells: ADR deciles {[round(x,3) for x in C['cells']['R1']['adr_cuts']]}, return quintiles {[round(x,2) for x in C['cells']['R1']['ret_cuts']]}"],
    ])
    G = J["grid"]
    P("**Stop widths (first trade, entry at the close; ADR = ADR20 at t − 1 × entry; median (quartiles); 'tiny' = under 0.25 ADR)**")
    P()
    rows = []
    for s in STOPS:
        g = G[f"{s}_close"]; e = g["R1_T0_complete"]["entries"]; c = g["R1_T0_complete"]["control"]
        extra = f"; the 20-session-prior-low proxy ON the R1 entries would be {qs(g['r1_proxy_width_adr_q'])}" if s == "S4" else ""
        rows.append([STOP_NAME[s], f"n = {g['win']['T0']['n']}: {qs(g['win']['width_adr_q'])}; skipped {g['win']['n_skipped_first']}", f"n = {e['n']}: {qs(g['r1_width_adr_q'])}; tiny {pct(e['tiny_share'],1)}",
                     f"n = {R['complete_r2']}: {qs(g['r1_width_adr_q_r2'])}", f"n = {C['n'] - g['ctl_skipped_first']:,}: {qs(g['ctl_width_adr_q'])}; tiny {pct(c['tiny_share'],1)}; skipped (stop ≥ entry) {g['ctl_skipped_first']:,}{extra}"])
    tbl(["stop", "P-win doublers", "P-all R1 (complete)", "R2", "P-ctl control"], rows)

    # ── P-win ────────────────────────────────────────────────────────────────────────────────────
    for var in ("close", "nopen"):
        P(f"### P-win — the covered doublers, entry at the {'breakout close' if var == 'close' else 'NEXT OPEN'} ({era}; n on every row; s50 = the session the close first made half the gain)")
        P()
        rows = []
        for s in STOPS:
            g = G[f"{s}_{var}"]["win"]
            for T in (0, 1, 2):
                w = g[f"T{T}"]; n = w["n"]
                sm = w["first_status_mix"]
                rows.append([STOP_NAME[s], f"T{T}", f"n = {n}", f"{w['still_in_s50']} ({100*w['still_in_s50']/n:.0f}%)", f"{w['kept_half']} ({100*w['kept_half']/n:.0f}%)", f"{w['kept_quarter']} ({100*w['kept_quarter']/n:.0f}%)",
                             f"{w['first_stopped_before_s50']} ({100*w['first_stopped_before_s50']/n:.0f}%)", f"{w['first_cut']} ({100*w['first_cut']/n:.0f}%)",
                             f"{w['retries_mean']:.2f}; 1: {w['used1']}, 2: {w['used2']}" if T else "—", f"{w['still_in_s50_needing_retry']} / {w['kept_half_needing_retry']} / {w['kept_quarter_needing_retry']}" if T else "—",
                             f"{w['chain_r_mean']:+.2f} / {w['chain_r_q'][1]:+.2f}", f"{w['any5']} / {w['any10']}", f"{w['kept_share_mean']:.3f} / {w['kept_share_q'][1]:.3f}", w["trunc"]])
                if var == "close":
                    head[era][f"win_{s}_T{T}"] = dict(n=n, still_in_s50=w["still_in_s50"], kept_half=w["kept_half"], kept_quarter=w["kept_quarter"], retries_mean=w["retries_mean"], used1=w["used1"], used2=w["used2"], first_cut=w["first_cut"], first_stopped_before_s50=w["first_stopped_before_s50"])
        tbl(["stop", "retries", "bases", "still in a trade at s50", "chain kept ≥ ½ of the gain", "kept ≥ ¼", "first trade STOPPED before s50", "first trade CUT at session 3 (no +1R)", "retries used (mean; bases using 1 / 2)", "of the still-in / kept-½ / kept-¼ bases, how many needed a retry", "chain R mean / median", "bases with a ≥ 5R / ≥ 10R trade", "kept share of the gain: mean / median", "chains marked at the cut"], rows)

    # ── P-all vs P-ctl ──────────────────────────────────────────────────────────────────────────
    for es in ("R1", "R2"):
        for var in ("close", "nopen"):
            for comp in ("complete", "complete_w025", "all"):
                lab = {"complete": "COMPLETE bases (t + 120 ≤ last readable session) — the headline", "complete_w025": "complete bases whose FIRST-trade stop is at least 0.25 ADR wide, both sides (the R-unit sensitivity)", "all": "ALL bases, open chains marked at the last readable close"}[comp]
                if var == "nopen" and comp != "complete":
                    continue
                P(f"### P-all {es} vs P-ctl — entry at the {'breakout close' if var == 'close' else 'NEXT OPEN'}, {lab} ({era})")
                P()
                rows = []
                for s in STOPS:
                    for T in (0, 1, 2):
                        c = G[f"{s}_{var}"][f"{es}_T{T}_{comp}"]; e, m, d = c["entries"], c["control"], c["diff"]
                        rows.append([STOP_NAME[s], f"T{T}", f"n = {e['n']}", f"{e['trades']:.0f} = {e['trades_per_week']:.1f}/wk (ctl {m['trades_per_week']:.1f})",
                                     f"{e['r_per_trade']:+.3f} vs {m['r_per_trade']:+.3f}", f"{e['adr_per_trade']:+.3f} vs {m['adr_per_trade']:+.3f}",
                                     f"{e['r_per_base']:+.3f} vs {m['r_per_base']:+.3f}; **{ci(d['r_per_base'], 3)}**", f"{e['adr_per_base']:+.3f} vs {m['adr_per_base']:+.3f}; **{ci(d['adr_per_base'], 3)}**",
                                     f"{pct(e['win_per_trade'])} vs {pct(m['win'])} (first) {ci(d['win'], 1, 1, ' pts')}",
                                     f"{e['ge5_per100_trades']:.1f} / {e['ge10_per100_trades']:.1f} per 100 trades; per 100 bases {e['any5_per100']:.1f} vs {m['any5_per100']:.1f} {ci(d['any5'], 1, 1)}; {e['any10_per100']:.1f} vs {m['any10_per100']:.1f} {ci(d['any10'], 1, 1)}",
                                     f"{pct(e['race2_hit'])} / {pct(e['race5_hit'])} / {pct(e['race10_hit'])} vs {pct(m['race2_hit'])} / {pct(m['race5_hit'])} / {pct(m['race10_hit'])}; +5R {ci(d['race5_hit'], 1, 1, ' pts')}; +10R {ci(d['race10_hit'], 1, 1, ' pts')}",
                                     f"{pct(e['stopped'])} / {pct(e['cut'])} / {pct(e['trailed'])} vs {pct(m['stopped'])} / {pct(m['cut'])} / {pct(m['trailed'])}",
                                     f"{e['retries_mean']:.2f} vs {m['retries_mean']:.2f}" if T else "—", f"{pct(e['tiny_share'],1)} vs {pct(m['tiny_share'],1)}", f"{c['fallback']['cell']} / {c['fallback']['to_decile']} / {c['fallback']['to_day']}", f"{e['trunc']:.0f}"])
                        if es == "R1" and var == "close" and comp == "complete":
                            head[era][f"all_{s}_T{T}"] = dict(n=e["n"], trades_per_week=e["trades_per_week"], r_per_trade=e["r_per_trade"], ctl_r_per_trade=m["r_per_trade"], r_per_base=e["r_per_base"], ctl_r_per_base=m["r_per_base"],
                                                              diff_r_per_base=d["r_per_base"], adr_per_base=e["adr_per_base"], ctl_adr_per_base=m["adr_per_base"], diff_adr_per_base=d["adr_per_base"],
                                                              ge5_per100_trades=e["ge5_per100_trades"], ge10_per100_trades=e["ge10_per100_trades"], any5=e["any5_per100"], ctl_any5=m["any5_per100"], diff_any5=d["any5"], diff_any10=d["any10"],
                                                              race5_hit=e["race5_hit"], ctl_race5_hit=m["race5_hit"], diff_race5=d["race5_hit"], stopped=e["stopped"], cut=e["cut"], trailed=e["trailed"], win_per_trade=e["win_per_trade"],
                                                              account=c["account"], account_control=c["account_control"], tiny=e["tiny_share"], ctl_tiny=m["tiny_share"])
                        if es == "R1" and var == "close" and comp == "complete_w025":
                            head[era][f"w025_{s}_T{T}"] = dict(n=e["n"], diff_r_per_base=d["r_per_base"], diff_adr_per_base=d["adr_per_base"], diff_any5=d["any5"], diff_race5=d["race5_hit"], r_per_trade=e["r_per_trade"], ctl_r_per_trade=m["r_per_trade"])
                        if es == "R2" and var == "close" and comp == "complete":
                            head[era][f"r2_{s}_T{T}"] = dict(n=e["n"], trades_per_week=e["trades_per_week"], r_per_trade=e["r_per_trade"], ctl_r_per_trade=m["r_per_trade"], r_per_base=e["r_per_base"], diff_r_per_base=d["r_per_base"], diff_adr_per_base=d["adr_per_base"], diff_any5=d["any5"], diff_race5=d["race5_hit"], ge5_per100_trades=e["ge5_per100_trades"], account=c["account"], account_control=c["account_control"])
                tbl(["stop", "retries", "bases", "trades (per week; control matched)", "mean R per TRADE: entries vs control", "P&L in ADR per trade", "mean R per BASE (chain): entries vs control; diff (95% month-block)", "ADR P&L per base; diff",
                     "win rate per trade (control: first trade); first-trade diff", "≥ 5R / ≥ 10R", "race: first trade reaches +2R / +5R / +10R before its stop (entries vs control)", "first-trade exit: stopped / cut at session 3 / trailed", "retries used", "stops under 0.25 ADR", "matched in cell / fell back to decile / to day", "chains marked at the cut"], rows)
                if comp == "complete" and var == "close":
                    P(f"**Account view — fixed 0.5% of equity risked per trade, additive, no position cap, sequenced by exit ({es}, {era}, complete bases)**")
                    P()
                    rows = []
                    for s in STOPS:
                        for T in (0, 1, 2):
                            c = G[f"{s}_{var}"][f"{es}_T{T}_{comp}"]; a, b = c["account"], c["account_control"]
                            rows.append([STOP_NAME[s], f"T{T}", f"n = {a['n']} trades", f"{a['total_pct']:+.0f}%", f"{a['max_dd_pct']:.0f}%", f"{a['open_median']:.0f} / {a['open_max']:.0f}", f"n = {b['n']}", f"{b['total_pct']:+.0f}%", f"{b['max_dd_pct']:.0f}%", (f"{c['entries']['r_top5_share']*100:.0f}%" if (np.isfinite(c['entries']['r_top5_share']) and a['total_r'] > 0) else "— (total R not positive)")])
                    tbl(["stop", "retries", "entries' trades", "total return", "worst drawdown", "positions open at once: median / max", "matched-sample control trades", "its total return", "its worst drawdown", "5 best trades' summed R ÷ total R (only where the total is positive)"], rows)

json.dump(head, open(f"{LOG_DIR}/03_headline.json", "w"), indent=1)
open(f"{LOG_DIR}/03_report.md", "w").write("\n".join(out) + "\n")
print(f"wrote 03_report.md ({len(out)} lines) and 03_headline.json for {list(head)}")
