#!/usr/bin/env python3
"""#702 R decomposition, step 3: the waterfall, the matched control, the 39 lens and the side rows, from the step-2 tables.
Writes scripts/probes/_702_r_decomposition_1022/03_report.md (every table of the doc, n on every row) and 03_numbers.json.
Reads only r_decomp_fills_<era> / r_decomp_control_<era> (no bar after 2024-12-31 was used to build them)."""
from __future__ import annotations
import json, re
import numpy as np, pandas as pd

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_r_decomposition_1022"
DATA = {"2017-21": "/Users/alvinfung/apollo_data/cb702_pre/out", "2022-24": "/Users/alvinfung/apollo_data/cb702/out"}
STOP_KINDS = {"stop", "stop_gap", "day0_stop", "day0_gap"}
THRESH = (5, 10)
SEED = 702
L: list[str] = []
NUM: dict = {}


def p(s=""):
    L.append(s)


def pct(x, d=1):
    return f"{100*x:.{d}f}%"


def month_block_ci(vals: np.ndarray, months: np.ndarray, n=2000, seed=SEED):
    """95% interval of the mean by resampling calendar months (the standard's month-block bootstrap)."""
    df = pd.DataFrame({"v": vals, "m": months})
    g = df.groupby("m").v.agg(["sum", "count"])
    s, c = g["sum"].to_numpy(), g["count"].to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(s), size=(n, len(s)))
    means = s[idx].sum(1) / c[idx].sum(1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def waterfall(f: pd.DataFrame, T: int, horizon: int = 60, small_rule: str = "half_threshold") -> dict:
    """Every fill in exactly one bin. s* = the first session in 1..horizon whose HIGH reached fill x (1 + T x ADR20).
    A: no s*.  Out before s* (exit_session < s*, or == s* on a stop exit - the bar touched both, the walk books the stop):
       B if the exit was the ORIGINAL stop (a stop exit with no third taken - under pp the stop never moves without a third),
       C_out otherwise (a breakeven stop after a third, a trail, the session-3 cut).
    In at s*: D if pnl_adr >= T/2 (kept at least half the defining move), else C_in. small_rule 'half_mfe': C_in if pnl_adr < mfe/2."""
    first = f[f"first_{T}adr"].to_numpy()
    big = (first >= 1) & (first <= horizon)
    ex_s = f.exit_session.to_numpy(float)
    ek = f.exit_kind.fillna("").to_numpy()
    pk = f.partial_kind.fillna("").to_numpy()
    isstop = np.isin(ek, list(STOP_KINDS))
    out_before = big & ((ex_s < first) | ((ex_s == first) & isstop))
    B = out_before & isstop & (pk == "")
    C_out = out_before & ~B
    in_at = big & ~out_before
    kept = f.pnl_adr.to_numpy(float)
    if small_rule == "half_threshold":
        small = kept < T / 2
    else:
        small = kept < 0.5 * f[f"mfe{horizon}_adr_fill"].to_numpy(float)
    D = in_at & ~small
    C_in = in_at & small
    A = ~big
    n = len(f)
    assert A.sum() + B.sum() + C_out.sum() + C_in.sum() + D.sum() == n
    nb = int(big.sum())
    r = f.realized_r.to_numpy(float)
    res = dict(n=n, big=nb, A=int(A.sum()), B=int(B.sum()), C_out=int(C_out.sum()), C_in=int(C_in.sum()), D=int(D.sum()),
               same_bar_stop=int((big & (ex_s == first) & isstop).sum()),
               B_day0=int((B & (f.fill_day_stop.to_numpy() == 1)).sum()), B_later=int((B & (f.fill_day_stop.to_numpy() != 1)).sum()),
               B_lowtouch=int((big & (f.first_low_le_stop.to_numpy() >= 1) & (f.first_low_le_stop.to_numpy() < first)).sum()),
               r_sum=dict(A=float(r[A].sum()), B=float(r[B].sum()), C_out=float(r[C_out].sum()), C_in=float(r[C_in].sum()), D=float(r[D].sum())),
               r_mean=dict(A=float(r[A].mean()) if A.any() else None, B=float(r[B].mean()) if B.any() else None,
                           C_out=float(r[C_out].mean()) if C_out.any() else None, C_in=float(r[C_in].mean()) if C_in.any() else None,
                           D=float(r[D].mean()) if D.any() else None),
               mfe_mean=dict(B=float(f.loc[B, f"mfe{horizon}_adr_fill"].mean()) if B.any() else None,
                             C_out=float(f.loc[C_out, f"mfe{horizon}_adr_fill"].mean()) if C_out.any() else None,
                             C_in=float(f.loc[C_in, f"mfe{horizon}_adr_fill"].mean()) if C_in.any() else None,
                             D=float(f.loc[D, f"mfe{horizon}_adr_fill"].mean()) if D.any() else None),
               kept_mean=dict(C_in=float(kept[C_in].mean()) if C_in.any() else None, D=float(kept[D].mean()) if D.any() else None),
               ge10r=dict(B=int((r[B] >= 10).sum()), C_out=int((r[C_out] >= 10).sum()), C_in=int((r[C_in] >= 10).sum()), D=int((r[D] >= 10).sum()), A=int((r[A] >= 10).sum())),
               day0_flag=int(f[f"day0_high_ge_{T}adr"].sum()),
               s_star_median=float(np.median(first[big])) if nb else None)
    return res


def wf_table(title: str, rows: list[tuple[str, dict]]):
    p(f"**{title}**")
    p()
    p("| era / threshold | n fills | A never made the move | B stop hit first | C exit gave it back (out before / in but kept < half) | D captured | big moves lost to B | lost to C |")
    p("|---|---|---|---|---|---|---|---|")
    for lab, w in rows:
        nb = max(w["big"], 1)
        p(f"| {lab} | n = {w['n']:,} | {w['A']:,} ({pct(w['A']/w['n'])}) | {w['B']:,} ({pct(w['B']/w['n'])}) | {w['C_out']+w['C_in']:,} ({pct((w['C_out']+w['C_in'])/w['n'])}) = {w['C_out']:,} / {w['C_in']:,} | {w['D']:,} ({pct(w['D']/w['n'])}) | {pct(w['B']/nb)} of {w['big']:,} | {pct((w['C_out']+w['C_in'])/nb)} |")
    p()


def main():
    fills = {e: pd.read_csv(f"{d}/r_decomp_fills_{e}.tsv.gz", sep="\t", low_memory=False) for e, d in DATA.items()}
    ctl = {e: pd.read_csv(f"{d}/r_decomp_control_{e}.tsv.gz", sep="\t", low_memory=False) for e, d in DATA.items()}

    # ── 0. population / completeness ────────────────────────────────────────────────────────
    p("## Population and completeness (n on every row)")
    p()
    p("| era | published mature fills | with a readable E bar | 20-session window complete | 60-session window complete | fwd_hole rows (a missing session inside the walk) |")
    p("|---|---|---|---|---|---|")
    for e, f in fills.items():
        pub = 13363 if e == "2017-21" else 8984
        p(f"| {e} | n = {pub:,} | {len(f):,} | {int(f.complete_20.sum()):,} | {int(f.complete_60.sum()):,} | {int(f.fwd_hole.sum())} |")
        NUM[f"pop_{e}"] = dict(published=pub, readable=len(f), c20=int(f.complete_20.sum()), c60=int(f.complete_60.sum()))
    p()

    # ── 1. the stock's path, tail first ───────────────────────────────────────────────────
    p("## 1. The stock's path after the fill, independent of our stop (ADR units; window (E, E+k] starts the session AFTER E)")
    p()
    p("| era | n (60-window complete) | max move from the fill within 60: >= 5 ADR | >= 10 ADR | p90 | median | max move within 20: >= 5 ADR | >= 10 ADR | worst low within 60 from the fill, median | fills with a 10R result (= about 4.5 ADR at the median stop) |")
    p("|---|---|---|---|---|---|---|---|---|---|")
    for e, f in fills.items():
        g = f[f.complete_60 == 1]; g20 = f[f.complete_20 == 1]
        m60, m20 = g.mfe60_adr_fill, g20.mfe20_adr_fill
        p(f"| {e} | n = {len(g):,} | {int((m60>=5).sum()):,} ({pct((m60>=5).mean())}) | {int((m60>=10).sum()):,} ({pct((m60>=10).mean(),2)}) | {m60.quantile(.9):.2f} ADR | {m60.median():.2f} ADR | {int((m20>=5).sum()):,} ({pct((m20>=5).mean())}, n = {len(g20):,}) | {int((m20>=10).sum()):,} ({pct((m20>=10).mean(),2)}) | {g.mae60_adr_fill.median():.2f} ADR | {int((g.realized_r>=10).sum()):,} ({pct((g.realized_r>=10).mean(),2)}) |")
        NUM[f"path_{e}"] = dict(n60=len(g), ge5=int((m60>=5).sum()), ge10=int((m60>=10).sum()), p90=float(m60.quantile(.9)), med=float(m60.median()),
                                n20=len(g20), ge5_20=int((m20>=5).sum()), ge10_20=int((m20>=10).sum()), r10=int((g.realized_r>=10).sum()))
    p()
    p("What was on the table vs what was kept, in ADR units (fills whose best 60-session move from the fill reached the threshold; 'on the table' = the sum of those best moves, a CEILING no exit reaches, not a forecast; 'kept' = the sum of realized R x width_adr on the same fills):")
    p()
    p("| era | threshold | n fills reaching it | on the table (ADR) | kept (ADR) | kept share | per fill: on the table | kept |")
    p("|---|---|---|---|---|---|---|---|")
    for e, f in fills.items():
        g = f[f.complete_60 == 1]
        for T in THRESH:
            b = g[g.mfe60_adr_fill >= T]
            p(f"| {e} | >= {T} ADR | n = {len(b):,} | {b.mfe60_adr_fill.sum():,.0f} | {b.pnl_adr.sum():+,.0f} | {pct(b.pnl_adr.sum()/b.mfe60_adr_fill.sum())} | {b.mfe60_adr_fill.mean():.1f} | {b.pnl_adr.mean():+.2f} |")
            NUM[f"table_{e}_{T}"] = dict(n=len(b), on_table=float(b.mfe60_adr_fill.sum()), kept=float(b.pnl_adr.sum()))
    p()
    p("Same, measured from E's CLOSE (the control's base; the fill is earlier in the day, so moves from the close read smaller):")
    p()
    p("| era | n | >= 5 ADR within 60 | >= 10 ADR within 60 | p90 | mean close-to-close +20 (ADR) | mean +60 (ADR) |")
    p("|---|---|---|---|---|---|---|")
    for e, f in fills.items():
        g = f[f.complete_60 == 1]; m = g.mfe60_adr_close
        p(f"| {e} | n = {len(g):,} | {int((m>=5).sum()):,} ({pct((m>=5).mean())}) | {int((m>=10).sum()):,} ({pct((m>=10).mean(),2)}) | {m.quantile(.9):.2f} | {g.ret20_adr_close.mean():+.2f} | {g.ret60_adr_close.mean():+.2f} |")
    p()

    # ── 2. the waterfall ──────────────────────────────────────────────────────────────────
    p("## 2. The waterfall: every fill with a complete 60-session window lands in exactly one bin")
    p()
    rows = []
    for e, f in fills.items():
        g = f[f.complete_60 == 1]
        for T in THRESH:
            w = waterfall(g, T); rows.append((f"{e}, +{T} ADR", w)); NUM[f"wf_{e}_{T}"] = w
    wf_table("Within 60 sessions of the fill; C_in = in at the move's start but kept < half the threshold move (pnl in ADR < T/2)", rows)
    p("B split by WHEN the original stop was hit (fill day = the ORH5 entry's own-day shake-out; later = a stop hit on sessions 1+ before the move):")
    p()
    p("| era / threshold | B total | stopped on the fill day | stopped on a later session (before s*) | share of B on the fill day |")
    p("|---|---|---|---|---|")
    for lab, w in rows:
        p(f"| {lab} | n = {w['B']:,} | {w['B_day0']:,} | {w['B_later']:,} | {pct(w['B_day0']/max(w['B'],1))} |")
    p()
    p("Bin detail (mean realized R per bin; the stock's mean best move in the B / C bins = what was on the table; n per bin above):")
    p()
    p("| era / threshold | mean R: A | B | C_out | C_in | D | mean best move (ADR) B | C_out | C_in | D | 10R trades in D / C_in / elsewhere | same-bar stop at s* (counted in B/C_out) | big movers whose daily LOW reached the original stop level on a session in E+1..s*-1 (whatever our stop was by then) | median s* (sessions) | E's own high already >= T ADR over the fill |")
    p("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for lab, w in rows:
        rm, mm, g10 = w["r_mean"], w["mfe_mean"], w["ge10r"]
        fm = lambda x: "-" if x is None else f"{x:+.2f}"
        p(f"| {lab} (n = {w['n']:,}) | {fm(rm['A'])} | {fm(rm['B'])} | {fm(rm['C_out'])} | {fm(rm['C_in'])} | {fm(rm['D'])} | {fm(mm['B'])} | {fm(mm['C_out'])} | {fm(mm['C_in'])} | {fm(mm['D'])} | {g10['D']} / {g10['C_in']} / {g10['A']+g10['B']+g10['C_out']} | {w['same_bar_stop']} | {w['B_lowtouch']} | {w['s_star_median']:.0f} | {w['day0_flag']} |")
    p()
    # sensitivity: half-MFE rule; 20-session horizon
    rows2 = []
    for e, f in fills.items():
        g = f[f.complete_60 == 1]
        for T in THRESH:
            rows2.append((f"{e}, +{T} ADR, small = kept < half the stock's best 60-session move", waterfall(g, T, small_rule="half_mfe")))
    wf_table("Sensitivity: 'small' read as kept < half of the stock's own best move (instead of half the threshold)", rows2)
    rows3 = []
    for e, f in fills.items():
        g = f[f.complete_20 == 1]
        for T in THRESH:
            rows3.append((f"{e}, +{T} ADR within 20 sessions", waterfall(g, T, horizon=20)))
    wf_table("Sensitivity: the move must come within 20 sessions (more fills have a complete window)", rows3)
    # R lost per bin, as a share of the sum of positive MFE
    p("What the bins cost in R (sum of realized R per bin; the published mean R is the sum over all bins / n):")
    p()
    p("| era / threshold | n | sum R: A | B | C_out | C_in | D | total | mean R (this subset) |")
    p("|---|---|---|---|---|---|---|---|---|")
    for lab, w in rows:
        rs = w["r_sum"]; tot = sum(rs.values())
        p(f"| {lab} | n = {w['n']:,} | {rs['A']:+,.0f} | {rs['B']:+,.0f} | {rs['C_out']:+,.0f} | {rs['C_in']:+,.0f} | {rs['D']:+,.0f} | {tot:+,.0f} | {tot/w['n']:+.3f} |")
    p()

    # ── 3. the control ────────────────────────────────────────────────────────────────────
    p("## 3. The matched control (selection): the same E dates, the setup's universe filter at D, matched on ADR20 decile (and on the 63-session return quintile)")
    p()
    for e, f in fills.items():
        c = ctl[e]
        g = f[f.complete_60 == 1].copy(); cc = c[c.complete_60 == 1].copy()
        dec = np.percentile(g.adr20, range(10, 100, 10))
        g["adr_dec"] = np.searchsorted(dec, g.adr20); cc["adr_dec"] = np.searchsorted(dec, cc.adr20)
        rq = np.percentile(g.ret63_D.dropna(), [20, 40, 60, 80])
        g["ret_q"] = np.searchsorted(rq, g.ret63_D.fillna(-9)); cc["ret_q"] = np.searchsorted(rq, cc.ret63_D.fillna(-9))
        p(f"**{e} — composition first.** Breakouts n = {len(g):,} over {g.E.nunique()} E dates; control n = {len(cc):,} (ticker-dates; mean {len(cc)/cc.E.nunique():.0f} per E). "
          f"ADR20 deciles cut on the breakouts: {np.round(dec, 4).tolist()}; 63-session return quintile cuts: {np.round(rq, 3).tolist()}. "
          f"Breakouts' median ADR20 {g.adr20.median():.4f} vs the pooled control's {cc.adr20.median():.4f}; median 63-session return {g.ret63_D.median():+.3f} vs {cc.ret63_D.median():+.3f}; median 20-session dollar volume ${g.dv_D.median()/1e6:.0f}M vs ${cc.dv_D.median()/1e6:.0f}M.")
        p()
        p("Per decile, POOLED over all E dates (not date-matched - breakouts cluster in strong months; the date-matched rows below are the verdict):")
        p()
        p("| ADR20 decile | breakouts n | control n | breakout >= 5 ADR from E close within 60 | control >= 5 ADR | breakout >= 10 ADR | control >= 10 ADR | breakout mean +20 close (ADR) | control mean +20 |")
        p("|---|---|---|---|---|---|---|---|---|")
        for d_ in range(10):
            gb, cb_ = g[g.adr_dec == d_], cc[cc.adr_dec == d_]
            p(f"| {d_+1} | n = {len(gb):,} | n = {len(cb_):,} | {pct((gb.mfe60_adr_close>=5).mean())} | {pct((cb_.mfe60_adr_close>=5).mean())} | {pct((gb.mfe60_adr_close>=10).mean(),2)} | {pct((cb_.mfe60_adr_close>=10).mean(),2)} | {gb.ret20_adr_close.mean():+.2f} | {cb_.ret20_adr_close.mean():+.2f} |")
        p()
        # exact matching on (E, cell): each fill's control rate = the control's rate in its own (E, cell); fills with an empty cell fall back to (E, decile), then to E
        out = {}
        for name, keys in (("ADR decile", ["E", "adr_dec"]), ("ADR decile x 63-session return quintile", ["E", "adr_dec", "ret_q"])):
            for metric, col, fn in (("share >= 5 ADR within 60 (from E close)", "mfe60_adr_close", lambda s: (s >= 5).astype(float)),
                                    ("share >= 10 ADR within 60 (from E close)", "mfe60_adr_close", lambda s: (s >= 10).astype(float)),
                                    ("mean +20-session close return (ADR)", "ret20_adr_close", lambda s: s.astype(float)),
                                    ("mean +60-session close return (ADR)", "ret60_adr_close", lambda s: s.astype(float))):
                cc["_v"] = fn(cc[col]); g["_v"] = fn(g[col])
                cell = cc.groupby(keys)["_v"].agg(["mean", "count"])
                fb1 = cc.groupby(["E", "adr_dec"])["_v"].mean(); fb2 = cc.groupby("E")["_v"].mean()
                j = g.join(cell, on=keys)
                matched = j["mean"].copy()
                miss1 = matched.isna()
                matched[miss1] = g.loc[miss1].join(fb1.rename("fb"), on=["E", "adr_dec"])["fb"]
                miss2 = matched.isna()
                matched[miss2] = g.loc[miss2].join(fb2.rename("fb"), on="E")["fb"]
                diff = (g["_v"] - matched).to_numpy()
                ok = ~np.isnan(diff)
                lo, hi = month_block_ci(diff[ok], g.E.str[:7].to_numpy()[ok])
                out[(name, metric)] = dict(n=int(ok.sum()), b=float(g["_v"][ok].mean()), c=float(matched[ok].mean()), d=float(diff[ok].mean()), lo=lo, hi=hi,
                                           empty_cells=int(miss1.sum()), fallback_E=int(miss2.sum()))
        p(f"| {e}: matching | measure | n fills | breakouts | matched control | difference | 95% month-block interval | fills whose cell had no control (fell back to decile / to the date) |")
        p("|---|---|---|---|---|---|---|---|")
        for (name, metric), v in out.items():
            is_rate = "share" in metric
            fmt = (lambda x: pct(x, 2)) if is_rate else (lambda x: f"{x:+.2f}")
            p(f"| {name} | {metric} | n = {v['n']:,} | {fmt(v['b'])} | {fmt(v['c'])} | {fmt(v['d'])} | {fmt(v['lo'])} .. {fmt(v['hi'])} | {v['empty_cells']} / {v['fallback_E']} |")
            NUM[f"ctl_{e}|{name}|{metric}"] = v
        p()

    # ── 4. the 39 lens ────────────────────────────────────────────────────────────────────
    src = open("/Users/alvinfung/apollo_the_wise/scripts/probes/_cb_backtest/aplus_read.py").read()
    m39 = re.search(r"THE_39\s*=\s*\((.*?)\)", src, re.S)
    the39 = tuple(re.findall(r'"([A-Z]+)"', m39.group(1)))
    assert len(the39) == 39, len(the39)
    hs = open(f"{DATA['2017-21']}/aplus_hindsight_pre.txt").read()
    assert all(tk in hs for tk in the39)
    f = fills["2017-21"]; g = f[f.complete_60 == 1]
    l39 = g[g.ticker.isin(the39)]
    p("## 4. The 39-winner lens (2017-21 only; selection held fixed at perfect by hindsight - NOT evidence about selection)")
    p()
    p(f"The 39 tickers (parsed from `aplus_read.py` `THE_39`, cross-checked against `aplus_hindsight_pre.txt`) have n = {len(l39):,} C0 `tl` ORH5 fills in 2017-21 with a complete 60-session window (the whole era, not only 2020-21; {l39.ticker.nunique()} of the 39 appear).")
    p()
    p("| group | n | mean R | 10R trades | best 60-session move from the fill: >= 5 ADR | >= 10 ADR | p90 (ADR) | median (ADR) | sum of best moves (ADR, fills >= 5 ADR) | sum kept (pnl in ADR, same fills) | fill-day stop share |")
    p("|---|---|---|---|---|---|---|---|---|---|---|")
    for lab, h in (("the 39's fills", l39), ("all other 2017-21 fills", g[~g.ticker.isin(the39)])):
        big = h[h.mfe60_adr_fill >= 5]
        p(f"| {lab} | n = {len(h):,} | {h.realized_r.mean():+.3f} | {int((h.realized_r>=10).sum())} ({pct((h.realized_r>=10).mean(),2)}) | {int((h.mfe60_adr_fill>=5).sum())} ({pct((h.mfe60_adr_fill>=5).mean())}) | {int((h.mfe60_adr_fill>=10).sum())} ({pct((h.mfe60_adr_fill>=10).mean())}) | {h.mfe60_adr_fill.quantile(.9):.2f} | {h.mfe60_adr_fill.median():.2f} | {big.mfe60_adr_fill.sum():,.0f} | {big.pnl_adr.sum():+,.0f} | {pct(h.fill_day_stop.mean())} |")
    p()
    rows39 = [(f"the 39, +{T} ADR", waterfall(l39, T)) for T in THRESH]
    for lab, w in rows39:
        NUM[f"wf39_{lab}"] = w
    wf_table("The 39's waterfall (60 sessions)", rows39)
    p("| the 39 / threshold | mean R: B | C_out | C_in | D | mean best move (ADR): B | C_out | C_in | D | 10R trades in D / C_in / elsewhere |")
    p("|---|---|---|---|---|---|---|---|---|---|")
    for lab, w in rows39:
        rm, mm, g10 = w["r_mean"], w["mfe_mean"], w["ge10r"]
        fm = lambda x: "-" if x is None else f"{x:+.2f}"
        p(f"| {lab} (n = {w['n']:,}) | {fm(rm['B'])} | {fm(rm['C_out'])} | {fm(rm['C_in'])} | {fm(rm['D'])} | {fm(mm['B'])} | {fm(mm['C_out'])} | {fm(mm['C_in'])} | {fm(mm['D'])} | {g10['D']} / {g10['C_in']} / {g10['A']+g10['B']+g10['C_out']} |")
    p()
    # per-ticker lines for the 39
    p("Per ticker (fills with a complete window; sorted by the sum of best moves):")
    p()
    p("| ticker | n fills | mean R | sum R | 10R | fills whose best 60-session move >= 5 ADR | of those: stop hit first (B) | exit gave it back (C) | captured (D) | sum best move (ADR) | sum kept (ADR) |")
    p("|---|---|---|---|---|---|---|---|---|---|---|")
    per = []
    for tk, h in l39.groupby("ticker"):
        w = waterfall(h, 5)
        per.append((tk, len(h), h.realized_r.mean(), h.realized_r.sum(), int((h.realized_r >= 10).sum()), w["big"], w["B"], w["C_out"] + w["C_in"], w["D"],
                    h.loc[h.mfe60_adr_fill >= 5, "mfe60_adr_fill"].sum(), h.loc[h.mfe60_adr_fill >= 5, "pnl_adr"].sum()))
    for r_ in sorted(per, key=lambda x: -x[9]):
        p(f"| {r_[0]} | n = {r_[1]} | {r_[2]:+.2f} | {r_[3]:+.1f} | {r_[4]} | {r_[5]} | {r_[6]} | {r_[7]} | {r_[8]} | {r_[9]:.0f} | {r_[10]:+.0f} |")
    p()

    # ── 5. side rows ──────────────────────────────────────────────────────────────────────
    p("## 5. Side rows")
    p()
    p("Day-0 stop-out share by stop width (width_adr = (fill - stop) / (ADR20 x fill); quartiles cut per era on the mature population):")
    p()
    p("| era | width quartile (ADR) | n | stopped on the fill day | mean R | 10R trades | best 60-session move >= 5 ADR (complete windows) |")
    p("|---|---|---|---|---|---|---|")
    for e, f in fills.items():
        q = np.percentile(f.width_adr, [25, 50, 75])
        f["wq"] = np.searchsorted(q, f.width_adr)
        labs = [f"<= {q[0]:.2f}", f"{q[0]:.2f}-{q[1]:.2f}", f"{q[1]:.2f}-{q[2]:.2f}", f"> {q[2]:.2f}"]
        for i in range(4):
            h = f[f.wq == i]; hc = h[h.complete_60 == 1]
            p(f"| {e} | Q{i+1} {labs[i]} | n = {len(h):,} | {pct(h.fill_day_stop.mean())} | {h.realized_r.mean():+.3f} | {int((h.realized_r>=10).sum())} | {pct((hc.mfe60_adr_fill>=5).mean())} (n = {len(hc):,}) |")
    p()
    # what a 10R trade is in ADR terms
    p("R vs ADR (why 10R is not a big move): realized R x width_adr = pnl in ADR units.")
    p()
    p("| era | n 10R trades | their median stop width (ADR) | their median pnl (ADR) | their median best 60-session move (ADR) | fills with best move >= 10 ADR that were NOT 10R trades |")
    p("|---|---|---|---|---|---|")
    for e, f in fills.items():
        g = f[f.complete_60 == 1]; t10 = g[g.realized_r >= 10]
        p(f"| {e} | n = {len(t10)} | {t10.width_adr.median():.2f} | {t10.pnl_adr.median():.1f} | {t10.mfe60_adr_fill.median():.1f} | {int(((g.mfe60_adr_fill>=10)&(g.realized_r<10)).sum())} of {int((g.mfe60_adr_fill>=10).sum())} |")
    p()
    with open(f"{HERE}/03_report.md", "w") as fh:
        fh.write("\n".join(L) + "\n")
    with open(f"{HERE}/03_numbers.json", "w") as fh:
        json.dump(NUM, fh, indent=1, default=float)
    print("\n".join(L))


if __name__ == "__main__":
    main()
