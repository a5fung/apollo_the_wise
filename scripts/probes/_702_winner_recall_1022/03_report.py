#!/usr/bin/env python3
"""#705 big-winner recall, step 3: the tables (markdown, n on every row) from the step-1/2 tables. Writes HERE/03_report.md and
HERE/03_numbers.json. Read-only on DATA."""
from __future__ import annotations
import json, os, sys
import numpy as np, pandas as pd

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_winner_recall_1022"
DATA = {"2017-21": "/Users/alvinfung/apollo_data/cb702_pre", "2022-24": "/Users/alvinfung/apollo_data/cb702"}
# optional re-run switches, 2017-21 only (all unset = unchanged): CB_PRE_DIR data dir, CB_PRE_OUT the step-1/2 tables (default DATA/out), CB_PRE_LOG logs + report; an era argument limits the run
PRE_OUT, LOG_DIR = os.environ.get("CB_PRE_OUT"), os.environ.get("CB_PRE_LOG", HERE)
if os.environ.get("CB_PRE_DIR"):
    DATA["2017-21"] = os.environ["CB_PRE_DIR"]
if sys.argv[1:]:
    DATA = {k: v for k, v in DATA.items() if k in sys.argv[1:]}
assert (not (PRE_OUT or LOG_DIR != HERE)) or list(DATA) == ["2017-21"], "CB_PRE_OUT / CB_PRE_LOG re-run the 2017-21 era only"


def out_dir(era):
    return PRE_OUT if (era == "2017-21" and PRE_OUT) else f"{DATA[era]}/out"


VAR = {"p": "primary: longest window, span <= 5 ADR60, sideways", "s4": "span <= 4 ADR60", "s7": "span <= 7 ADR60", "a20": "unit ADR20(b-1), span <= 5",
       "nosw": "no sideways rule", "shortL": "SHORTEST window (post hoc, added after the first build)"}
GATES_PLAIN = {"universe_sectype": "not a common stock / ADR", "universe_price": "raw close under $5", "universe_dv": "under $10M median dollar volume",
               "universe_history": "under 130 readable sessions", "history": "130 bars not consecutive", "prior_move": "prior move < 30% (no pole)",
               "close_above_pole_high": "a close above the pole high (base resolved)", "sma50": "close below the 50-day", "deal_pin_median": "deal-pin (median range)",
               "fresh_pin": "fresh deal-pin", "pole_artifact": "pole data artifact", "adr_unusable": "ADR unusable", "close_nonpositive": "bad close", "pass": "passes (my rebuild)", "": "n/a"}
out: list[str] = []; NUM: dict = {}


def w(s=""):
    out.append(s)


def pct(a, b):
    return f"{a:,} ({100*a/b:.0f}%)" if b else f"{a:,} (n/a)"


def q(s, d=2):
    s = pd.Series(s).dropna()
    if len(s) == 0:
        return "n/a"
    qs = s.quantile([.25, .5, .75]).tolist()
    return f"{qs[1]:.{d}f} ({qs[0]:.{d}f} .. {qs[2]:.{d}f})"


def funnel(c: pd.DataFrame, label: str, key: str):
    """c = the episode-level catch table (one factor, one era, possibly a subset); the MB funnel then the all-class funnel"""
    n = len(c); mb = c[c.class_p == "measurable_breakout"]; cov = mb[mb.covered == 1]
    wt = cov[cov.watched == 1]; tr = cov[cov.triggered == 1]; nr = tr[tr.near_b == 1]
    si = tr[tr.still_in_s50 == 1]; kh = tr[tr.kept_half_episode == 1]; kha = tr[tr.kept_half_avail == 1]
    si_nr = nr[nr.still_in_s50 == 1]; kh_nr = nr[nr.kept_half_episode == 1]
    rows = [("big winners (episodes)", n, n), ("with a measurable breakout (primary rule)", len(mb), n), ("… whose base nights our watch covers", len(cov), len(mb)),
            ("… WATCHED (a watch row on some base night)", len(wt), len(cov)), ("… watched with a trendline level (C0_tl) on some base night", int(cov.watched_tl.sum()), len(cov)),
            ("… watched on the night before the breakout day", int(cov.watched_bprev.sum()), len(cov)),
            ("… TRIGGERED (a tl ORH5 fill, E in the catch window)", len(tr), len(cov)), ("… triggered NEAR the breakout (E within 5 sessions of b)", len(nr), len(cov)),
            ("… triggered and STILL IN at s50 (half the gain made)", len(si), len(cov)), ("… near the breakout and still in at s50", len(si_nr), len(cov)),
            ("… triggered and KEPT >= half of the episode's gain", len(kh), len(cov)), ("… near the breakout and kept >= half of the episode's gain", len(kh_nr), len(cov)),
            ("… triggered and kept >= half of the gain available from the fill", len(kha), len(cov))]
    w(f"**{label}** — the funnel (shares are of the row named in the third column)\n")
    w("| step | n | share of |"); w("|---|---|---|")
    for name, a, b in rows:
        w(f"| {name} | n = {a:,} | {100*a/b:.0f}% of {b:,} |" if b else f"| {name} | n = {a:,} | n/a |")
    NUM[f"{key}/funnel"] = {r[0]: [int(r[1]), int(r[2])] for r in rows}
    # all classes
    cv = c[c.covered == 1]; trr = cv[cv.triggered == 1]
    w(f"\nAll {n:,} big winners, any class (covered n = {len(cv):,}): watched {pct(int(cv.watched.sum()), len(cv))}; triggered (tl fill in the catch window) "
      f"{pct(len(trr), len(cv))}; still in at s50 {pct(int(trr.still_in_s50.sum()), len(cv))}; kept >= half of the episode's gain {pct(int(trr.kept_half_episode.sum()), len(cv))}; "
      f"a tl fill ANYWHERE in [trough − 20, peak] {pct(int(cv.any_fill_t20_to_p.sum()), len(cv))}; any K (k5/k10/full/tl/com/comb where held) triggered in the catch window {pct(int(cv.trig_anyK.sum()), len(cv))}.\n")
    NUM[f"{key}/all_classes"] = dict(n=n, covered=len(cv), watched=int(cv.watched.sum()), triggered=len(trr), still_in_s50=int(trr.still_in_s50.sum()), kept_half=int(trr.kept_half_episode.sum()),
                                     any_fill_t20_to_p=int(cv.any_fill_t20_to_p.sum()), any_K=int(cv.trig_anyK.sum()))
    return cov, tr


def losses(cov: pd.DataFrame, tr: pd.DataFrame, label: str, key: str):
    w(f"**{label}** — where we lost them (measurable-breakout episodes whose base nights are covered, n = {len(cov):,})\n")
    nw = cov[cov.watched == 0]
    w(f"- NOT WATCHED on any base night: n = {len(nw):,} ({100*len(nw)/len(cov):.0f}% of {len(cov):,}). The furthest gate any base night reached (my rebuilt funnel; the first failing gate in evaluation order):")
    vc = nw.furthest_gate.value_counts()
    for g, k in vc.items():
        w(f"  - {GATES_PLAIN.get(g, g)} (`{g}`): n = {k:,} ({100*k/len(nw):.0f}% of {len(nw):,})")
    vb = nw.gate_bprev.value_counts()
    w(f"  - on the night before the breakout day alone: " + "; ".join(f"`{g}` n = {k:,}" for g, k in vb.items()))
    NUM[f"{key}/not_watched_furthest_gate"] = {str(g): int(k) for g, k in vc.items()}; NUM[f"{key}/not_watched_gate_bprev"] = {str(g): int(k) for g, k in vb.items()}
    wnt = cov[(cov.watched == 1) & (cov.triggered == 0)]
    w(f"- WATCHED BUT NO TRIGGER in the catch window: n = {len(wnt):,} ({100*len(wnt)/len(cov):.0f}%); of them a trendline level existed on some base night (C0_tl) n = {int(wnt.watched_tl.sum()):,}, "
      f"watched on the night before the breakout n = {int(wnt.watched_bprev.sum()):,}, a tl fill came later anywhere before the peak n = {int(wnt.any_fill_t20_to_p.sum()):,}, some other K filled in the window n = {int(wnt.trig_anyK.sum()):,}")
    NUM[f"{key}/watched_no_trigger"] = dict(n=len(wnt), tl_level=int(wnt.watched_tl.sum()), bprev=int(wnt.watched_bprev.sum()), later_fill=int(wnt.any_fill_t20_to_p.sum()), anyK=int(wnt.trig_anyK.sum()))
    if len(tr):
        st = tr[tr.stopped_before_s50 == 1]; ex = tr[tr.exited_before_s50_not_stop == 1]; si = tr[tr.still_in_s50 == 1]
        w(f"- TRIGGERED: n = {len(tr):,} ({100*len(tr)/len(cov):.0f}%). Fills per episode in the window: median {tr.n_fills_win.median():.0f}, max {int(tr.n_fills_win.max())}; retrigger rows as the first fill n = {int(tr.retrigger.sum()):,}; non-mature n = {int((tr.mature == 0).sum()):,}.")
        w(f"  - timing: E − b (sessions; negative = before the breakout day) median (quartiles) {q(tr.E_minus_b, 0)}; before b n = {int((tr.E_minus_b < 0).sum()):,}, on b n = {int((tr.E_minus_b == 0).sum()):,}, "
          f"1–5 after n = {int(((tr.E_minus_b > 0) & (tr.E_minus_b <= 5)).sum()):,}, later n = {int((tr.E_minus_b > 5).sum()):,}; share of the episode's gain already made at the fill: median (quartiles) {q(tr.gain_made_at_fill)}")
        w(f"  - the original STOP fired before s50: n = {len(st):,} ({100*len(st)/len(tr):.0f}% of {len(tr):,}) — of which before the breakout day itself n = {int(st.stopped_before_b.sum()):,}; "
          f"the exit (trail / day-3 rule), not the stop, ended it before s50: n = {len(ex):,} ({100*len(ex)/len(tr):.0f}%); still in at s50: n = {len(si):,} ({100*len(si)/len(tr):.0f}%); "
          f"status split: " + ", ".join(f"{k} n = {v}" for k, v in tr.status.value_counts().items()))
        w(f"  - realized R of the catch: mean {tr.realized_r.mean():+.2f}, median (quartiles) {q(tr.realized_r)}; >= 3R n = {int((tr.realized_r >= 3).sum()):,}, >= 10R n = {int((tr.realized_r >= 10).sum()):,}; sessions held median {tr.sessions_held.median():.0f}")
        w(f"  - kept, in the trade's ADR unit: the episode's gain = {q(tr.gain_adr, 1)} ADR, the gain available from the fill = {q(tr.avail_adr, 1)} ADR, the trade's P&L = {q(tr.pnl_adr)} ADR; "
          f"kept share of the episode's gain median (quartiles) {q(tr.kept_share_episode, 3)}, mean {tr.kept_share_episode.mean():.3f}; kept share of the available gain median {q(tr.kept_share_avail, 3)}; "
          f"kept >= half of the episode's gain n = {int(tr.kept_half_episode.sum()):,}, >= half of the available n = {int(tr.kept_half_avail.sum()):,}, >= a quarter of the episode's gain n = {int((tr.kept_share_episode >= 0.25).sum()):,}")
        w(f"  - counting EVERY fill in the window (not only the first): some fill still in at s50 n = {int(tr.any_fill_still_in_s50.sum()):,}; best fill's kept share of the episode's gain median {q(tr.best_fill_kept_share_episode, 3)}, >= half n = {int((tr.best_fill_kept_share_episode >= 0.5).sum()):,}")
        NUM[f"{key}/triggered"] = dict(n=len(tr), stopped_before_s50=len(st), stopped_before_b=int(st.stopped_before_b.sum()), exited_before_s50=len(ex), still_in_s50=len(si),
                                      E_minus_b_median=float(tr.E_minus_b.median()), before_b=int((tr.E_minus_b < 0).sum()), on_b=int((tr.E_minus_b == 0).sum()),
                                      mean_r=float(tr.realized_r.mean()), kept_half=int(tr.kept_half_episode.sum()), kept_half_avail=int(tr.kept_half_avail.sum()),
                                      kept_share_median=float(tr.kept_share_episode.median()), any_fill_still_in=int(tr.any_fill_still_in_s50.sum()))
    w()


def composition(e: pd.DataFrame, era: str, tag: str):
    n = len(e)
    w(f"### {era}, {tag} — composition (n = {n:,} episodes after exclusions)\n")
    w("| item | value |"); w("|---|---|")
    w(f"| episodes by trough year | " + ", ".join(f"{y}: n = {k:,}" for y, k in e.trough_date.str[:4].value_counts().sort_index().items()) + " |")
    w(f"| tickers | n = {e.ticker.nunique():,} (episodes per ticker max {int(e.groupby('ticker').size().max())}) |")
    w(f"| close at the trough, $ (median, quartiles) | {q(e.close_t)} (n = {n:,}) |")
    w(f"| ADR20 at the trough (median, quartiles) | {q(e.adr20_t, 3)} (n = {n:,}) |")
    w(f"| 63-session return into the trough (median, quartiles) | {q(e.ret63_t, 2)} (n = {int(e.ret63_t.notna().sum()):,}) |")
    w(f"| gain trough → peak (median, quartiles) | {q(e.gain, 2)} (n = {n:,}); >= +200% n = {int((e.gain >= 2).sum()):,} |")
    w(f"| sessions trough → peak (median, quartiles) | {q(e.sessions_t_to_p, 0)}; peak extended past the 63-session window n = {int(e.extended.sum()):,}; extension truncated at the cut n = {int(e.ext_truncated.sum()):,} |")
    w(f"| sessions trough → s25 / s50 (median) | {(e.s25 - e.t).median():.0f} / {(e.s50 - e.t).median():.0f} (n = {n:,}) |")
    w(f"| EP-gap start (a >= 10% gap on >= 3x volume within 5 sessions of the trough) | n = {int((e.gap_day >= 0).sum()):,} ({100*(e.gap_day >= 0).mean():.0f}%) |")
    w(f"| trough moved to a lower close inside the run / a lower universe-failing close just before it / a lower close in the 10 sessions before | n = {int(e.trough_moved.sum()):,} / {int(e.lower_close_pre10.sum()):,} (see log for the universe-fail count) |")
    w(f"| split inside [trough − 60, peak] (flag only) | n = {int(e.split_flag.sum()):,} |")
    w()
    w("| breakout class (one per episode) | " + " | ".join(VAR[v] for v in VAR) + " |"); w("|---|" + "---|" * len(VAR))
    for cls in ("measurable_breakout", "ep_gap", "late_base", "no_consolidation", "other"):
        w(f"| {cls} | " + " | ".join(pct(int((e[f'class_{v}'] == cls).sum()), n) for v in VAR) + " |")
    NUM[f"{era}/{tag}/classes"] = {v: {c: int(k) for c, k in e[f"class_{v}"].value_counts().items()} for v in VAR}
    w(f"\nA base breakout AND a gap start (overlap, primary rule): n = {int(e.bo_and_gap_p.sum()):,}.\n")
    mb = e[e.class_p == "measurable_breakout"]
    w(f"The measurable breakouts under the primary rule (n = {len(mb):,}): breakout day b − trough median (quartiles) {q(mb.b_minus_t, 0)} sessions; base length L {q(mb.L_p, 0)}; "
      f"the base contains the trough {pct(int(mb.base_contains_trough.sum()), len(mb))}; base span {q(mb.span_adr60, 1)} ADR60 = {q(mb.span_adr20, 1)} ADR20; base depth {q(mb.base_depth_pct, 2)}; "
      f"share of the episode's gain made at the close BEFORE b {q(mb.gain_made_at_b_prev, 2)} and at b's close {q(mb.gain_made_at_b_close, 2)}; the breakout close over the base high {q(mb.bo_close_over_high_adr, 2)} ADR20; "
      f"b opened with a gap of {q(mb.bo_gap_open_pct * 100, 1)}%.")
    w(f"The expansion-day version (range >= 1 ADR20, close in the top 30%, volume >= 1.5x the 50-day) holds on {pct(int(mb.bo_expansion.sum()), len(mb))} of them — "
      f"range ok {pct(int((mb.bo_range_adr >= 1).sum()), len(mb))}, close location ok {pct(int((mb.bo_close_loc >= 0.7).sum()), len(mb))}, volume ok {pct(int((mb.bo_vol_x >= 1.5).sum()), len(mb))}.")
    lb = e[e.class_p == "late_base"]
    if len(lb):
        w(f"The late-base episodes (n = {len(lb):,}): the first close above the longest base's high came when {q(lb.gain_made_at_b_close, 2)} of the gain was already made, "
          f"b − trough {q(lb.b_minus_t, 0)} sessions, base depth {q(lb.base_depth_pct, 2)}, the base contains the trough {pct(int(lb.base_contains_trough.sum()), len(lb))}.")
    w()
    NUM[f"{era}/{tag}/composition"] = dict(n=n, by_year={str(y): int(k) for y, k in e.trough_date.str[:4].value_counts().sort_index().items()}, gap_start=int((e.gap_day >= 0).sum()),
                                           mb=len(mb), mb_expansion=int(mb.bo_expansion.sum()), mb_b_minus_t_median=float(mb.b_minus_t.median()), mb_L_median=float(mb.L_p.median()),
                                           gain_median=float(e.gain.median()), close_t_median=float(e.close_t.median()))


def main():
    w("# Generated tables — big-winner recall (03_report.py; n on every row)\n")
    for tag, name in (("x200", "the +100% set (close at least doubled from the trough within 63 sessions)"), ("x150", "the +50% sensitivity set")):
        w(f"## {name}\n")
        for era in DATA:
            e = pd.read_csv(f"{out_dir(era)}/wrecall_episodes_{era}_{tag}.tsv.gz", sep="\t", keep_default_na=False, na_values=[""])
            e = e[e.excluded == 0].reset_index(drop=True)
            c = pd.read_csv(f"{out_dir(era)}/wrecall_catch_{era}_{tag}.tsv.gz", sep="\t", keep_default_na=False, na_values=[""])
            assert len(c) == len(e)
            composition(e, era, tag)
            w(f"### {era}, {tag} — what we did\n")
            cov, tr = funnel(c, f"{era}, {tag}", f"{era}/{tag}")
            losses(cov, tr, f"{era}, {tag}", f"{era}/{tag}")
            if tag == "x200":
                # the K view
                Ks = [k[5:] for k in c.columns if k.startswith("trig_") and k not in ("trig_anyK",)]
                w(f"Any-K view on the covered measurable breakouts (n = {len(cov):,}; the entry tables' ORH5 filled C0 rows, E in the catch window): " +
                  "; ".join(f"{K}: {pct(int(cov[f'trig_{K}'].sum()), len(cov))}, E − b median {cov.loc[cov[f'trig_{K}'] == 1, f'E_minus_b_{K}'].median():+.0f}" for K in Ks) + ".\n")
                NUM[f"{era}/{tag}/anyK"] = {K: int(cov[f"trig_{K}"].sum()) for K in Ks}
                if era == "2017-21":
                    sub = c[c.trough_date.str[:4] != "2020"]
                    w(f"#### 2017-21 without the 2020 troughs (2020 holds {int((c.trough_date.str[:4] == '2020').sum()):,} of {len(c):,} episodes)\n")
                    cov2, tr2 = funnel(sub, "2017-21 excluding 2020, x200", "2017-21/x200/no2020")
                    losses(cov2, tr2, "2017-21 excluding 2020, x200", "2017-21/x200/no2020")
                    w("By trough year (measurable breakouts covered → watched → triggered → still in at s50 → kept >= half):\n")
                    w("| year | big winners | measurable breakouts covered | watched | triggered | still in at s50 | kept >= half |"); w("|---|---|---|---|---|---|---|")
                    for y, g in c.groupby(c.trough_date.str[:4]):
                        m = g[(g.class_p == "measurable_breakout") & (g.covered == 1)]; t_ = m[m.triggered == 1]
                        w(f"| {y} | n = {len(g):,} | n = {len(m):,} | n = {int(m.watched.sum()):,} | n = {len(t_):,} | n = {int(t_.still_in_s50.sum()):,} | n = {int(t_.kept_half_episode.sum()):,} |")
                    w()
            # the reverse view
        for era in DATA:
            for line in open(f"{LOG_DIR}/02_reverse_{era}.txt"):
                if f"[{tag}]" in line:
                    w(f"Reverse view, {era}: " + line.strip().split("reverse view: ")[1] + "\n")
    # the validation counts from the step-2 logs
    w("## Validation of the gate rebuild (from 02_catch_<era>.txt)\n")
    for era in DATA:
        for line in open(f"{LOG_DIR}/02_catch_{era}.txt"):
            if "validation on covered nights" in line:
                w(f"- {era}: " + line.strip())
    with open(f"{LOG_DIR}/03_report.md", "w") as fh:
        fh.write("\n".join(out) + "\n")
    with open(f"{LOG_DIR}/03_numbers.json", "w") as fh:
        json.dump(NUM, fh, indent=1, default=float)
    print("\n".join(out))


if __name__ == "__main__":
    main()
