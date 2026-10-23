#!/usr/bin/env python3
"""#705 breakout definition, step 3: Question A (was our trigger early) and Question B (does a real breakout follow through) from the
step-2 tables. Writes 03_report.md (every table; n on every row) and 03_numbers.json. Reads only bdef_* (no bar after 2024-12-31
was used to build them). Matching + intervals exactly as yesterday's 03_report.py (cells on the entry day, deciles cut on the entry
set; month-block bootstrap, seed 702, 2,000)."""
from __future__ import annotations
import json, os, sys
import numpy as np, pandas as pd

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_breakout_definition_1022"
DATA = {"2017-21": "/Users/alvinfung/apollo_data/cb702_pre/out", "2022-24": "/Users/alvinfung/apollo_data/cb702/out"}
# optional re-run switches, 2017-21 only (all unset = unchanged): CB_PRE_OUT = the dir holding the bdef_* tables (default cb702_pre/out), CB_PRE_LOG = where
# 03_report.md / 03_numbers.json go (default HERE); an era argument limits the run
PRE_OUT, LOG_DIR = os.environ.get("CB_PRE_OUT"), os.environ.get("CB_PRE_LOG", HERE)
if PRE_OUT:
    DATA["2017-21"] = PRE_OUT
if sys.argv[1:]:
    DATA = {k: v for k, v in DATA.items() if k in sys.argv[1:]}
assert (not (PRE_OUT or LOG_DIR != HERE)) or list(DATA) == ["2017-21"], "CB_PRE_OUT / CB_PRE_LOG re-run the 2017-21 era only"
SEED, NB = 702, 2000
L: list[str] = []; NUM: dict = {}


def p(s=""):
    L.append(s)


def pct(x, d=1):
    return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{100*x:.{d}f}%"


def month_block_ci(vals, months, n=NB, seed=SEED):
    df = pd.DataFrame({"v": vals, "m": months}).dropna()
    g = df.groupby("m").v.agg(["sum", "count"]); s, c = g["sum"].to_numpy(), g["count"].to_numpy()
    rng = np.random.default_rng(seed); idx = rng.integers(0, len(s), size=(n, len(s)))
    means = s[idx].sum(1) / c[idx].sum(1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def wmedian(vals, w):
    o = np.argsort(vals); v, ww = np.asarray(vals)[o], np.asarray(w)[o]
    cw = np.cumsum(ww); return float(v[np.searchsorted(cw, cw[-1] / 2)]) if len(v) else float("nan")


# measures: name -> (prefix-relative value column builder). Each returns (values with NaN where incomplete)
def mvals(df, pre):
    out = {}
    c60 = df[f"{pre}c60"] == 1
    out["share >= 5 ADR within 60"] = np.where(c60, (df[f"{pre}mfe60"] >= 5).astype(float), np.nan)
    out["share >= 10 ADR within 60"] = np.where(c60, (df[f"{pre}mfe60"] >= 10).astype(float), np.nan)
    out["share reaching +5 ADR by session 5"] = np.where(df[f"{pre}c5"] == 1, ((df[f"{pre}first5"] >= 1) & (df[f"{pre}first5"] <= 5)).astype(float), np.nan)
    out["share reaching +5 ADR by session 20"] = np.where(df[f"{pre}c20"] == 1, ((df[f"{pre}first5"] >= 1) & (df[f"{pre}first5"] <= 20)).astype(float), np.nan)
    for k in (1, 5, 20, 60):
        out[f"mean close return +{k} (ADR)"] = np.where(df[f"{pre}c{k}"] == 1, df[f"{pre}ret{k}"].astype(float), np.nan)
    return pd.DataFrame(out, index=df.index)


RATE = lambda name: name.startswith("share")


def matched_table(label, ent, ctl, pre, adr_col, ret_col, era):
    """ent: entry rows with columns t (date str), <adr_col>, <ret_col>, month; ctl: control rows with t, adr20, ret63 and the measure cols."""
    ent = ent.copy(); ctl = ctl.copy()
    dec = np.percentile(ent[adr_col], range(10, 100, 10))
    rq = np.percentile(ent[ret_col].dropna(), [20, 40, 60, 80])
    ent["dec"] = np.searchsorted(dec, ent[adr_col]); ctl["dec"] = np.searchsorted(dec, ctl.adr20)
    ent["q"] = np.searchsorted(rq, ent[ret_col].fillna(-9)); ctl["q"] = np.searchsorted(rq, ctl.ret63.fillna(-9))
    me, mc = mvals(ent, pre), mvals(ctl, pre)
    mc["t"], mc["dec"], mc["q"] = ctl.t.values, ctl.dec.values, ctl.q.values
    me["t"], me["dec"], me["q"], me["month"] = ent.t.values, ent.dec.values, ent.q.values, ent.month.values
    cells = {"ADR decile": mc.groupby(["t", "dec"]).mean(), "ADR decile x 63-session return quintile": mc.groupby(["t", "dec", "q"]).mean()}
    fb_t = mc.groupby("t").mean()
    # composition line
    comp = (f"**{label} — composition.** n = {len(ent):,} over {ent.t.nunique()} entry days; control rows on those days {len(ctl[ctl.t.isin(set(ent.t))]):,}. "
            f"ADR20 (the entry's unit): median {ent[adr_col].median():.4f}, decile cuts {np.round(dec, 4).tolist()}; 63-session return quintile cuts {np.round(rq, 3).tolist()} "
            f"(entries' median {ent[ret_col].median():+.3f} vs the pooled control's {ctl.ret63.median():+.3f}).")
    p(comp); p()
    p(f"| {era}: {label} | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |")
    p("|---|---|---|---|---|---|---|---|---|")
    res = {}
    for mname, cell in cells.items():
        keys = ["t", "dec"] if mname == "ADR decile" else ["t", "dec", "q"]
        for meas in [c for c in me.columns if c not in ("t", "dec", "q", "month")]:
            v = me[meas]
            j = me[keys].join(cell[meas].rename("ctl"), on=keys)["ctl"]
            miss1 = j.isna()
            if miss1.any():
                j[miss1] = me.loc[miss1, ["t", "dec"]].join(cells["ADR decile"][meas].rename("fb"), on=["t", "dec"])["fb"]
            miss2 = j.isna()
            if miss2.any():
                j[miss2] = me.loc[miss2, ["t"]].join(fb_t[meas].rename("fb"), on="t")["fb"]
            diff = (v - j).to_numpy(float); ok = ~np.isnan(diff)
            if ok.sum() < 2:
                continue
            lo, hi = month_block_ci(diff[ok], me.month.to_numpy()[ok])
            fmt = (lambda x: pct(x, 2)) if RATE(meas) else (lambda x: f"{x:+.3f}")
            m1, m2 = int((miss1 & ok).sum()), int((miss2 & ok).sum())
            p(f"| {mname} | {meas} | n = {int(ok.sum()):,} | {fmt(float(v[ok].mean()))} | {fmt(float(j[ok].mean()))} | {fmt(float(diff[ok].mean()))} | {fmt(lo)} .. {fmt(hi)} | {m1} / {m2} |")
            res[(mname, meas)] = dict(n=int(ok.sum()), e=float(v[ok].mean()), c=float(j[ok].mean()), d=float(diff[ok].mean()), lo=lo, hi=hi)
    # the median start session: entries directly; control pooled over the finer cells weighted by entry counts
    e60 = ent[(ent[f"{pre}c60"] == 1)]
    big = e60[(e60[f"{pre}first5"] >= 1) & (e60[f"{pre}first5"] <= 60)]
    c60 = ctl[ctl[f"{pre}c60"] == 1].copy()
    wcount = e60.groupby(["t", "dec", "q"]).size().rename("w_e")
    ccount = c60.groupby(["t", "dec", "q"]).size().rename("n_c")
    cb = c60[(c60[f"{pre}first5"] >= 1) & (c60[f"{pre}first5"] <= 60)].join(wcount, on=["t", "dec", "q"]).join(ccount, on=["t", "dec", "q"])
    cb = cb[cb.w_e.notna()]
    cmed = wmedian(cb[f"{pre}first5"].to_numpy(), (cb.w_e / cb.n_c).to_numpy()) if len(cb) else float("nan")
    p(f"| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = {len(big):,} entries / {len(cb):,} control rows | {big[f'{pre}first5'].median():.0f} | {cmed:.0f} (pooled over the entries' cells, weighted) | - | - | - |")
    big10 = e60[(e60[f"{pre}first10"] >= 1) & (e60[f"{pre}first10"] <= 60)]
    cb10 = c60[(c60[f"{pre}first10"] >= 1) & (c60[f"{pre}first10"] <= 60)].join(wcount, on=["t", "dec", "q"]).join(ccount, on=["t", "dec", "q"]); cb10 = cb10[cb10.w_e.notna()]
    cmed10 = wmedian(cb10[f"{pre}first10"].to_numpy(), (cb10.w_e / cb10.n_c).to_numpy()) if len(cb10) else float("nan")
    p(f"| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = {len(big10):,} / {len(cb10):,} | {big10[f'{pre}first10'].median():.0f} | {cmed10:.0f} | - | - | - |")
    p()
    res["s5_med"] = (float(big[f"{pre}first5"].median()) if len(big) else None, cmed, len(big))
    res["s10_med"] = (float(big10[f"{pre}first10"].median()) if len(big10) else None, cmed10, len(big10))
    NUM[f"{era}|{label}"] = {f"{a}|{b}" if isinstance(k, tuple) else k: v for k, v in res.items() for a, b in [k if isinstance(k, tuple) else (k, "")]}
    return res


def main():
    for era, d in DATA.items():
        f = pd.read_csv(f"{d}/bdef_fills_{era}.tsv.gz", sep="\t", low_memory=False)
        r = pd.read_csv(f"{d}/bdef_r1_{era}.tsv.gz", sep="\t", low_memory=False)
        kv = pd.read_csv(f"{d}/bdef_kvar_{era}.tsv.gz", sep="\t", low_memory=False)
        ctl = pd.read_csv(f"{d}/bdef_control_{era}.tsv.gz", sep="\t", low_memory=False)
        f["t"] = f.E; f["month"] = f.E.str[:7]
        r["t"] = r.entry_date; r["month"] = r.entry_date.str[:7]
        kv["t"] = kv.E; kv["month"] = kv.E.str[:7]
        p(f"# {era}"); p()

        # ── Question A ───────────────────────────────────────────────────────────────────────
        p(f"## A. Was our trigger early? ({era}; n = {len(f):,} published fills with a readable E bar)"); p()
        dist = f.dist_adr
        p("| era | n fills | fill distance below the base high (ADR20 at D): median | quartiles | p10 / p90 | fill already at/above the base high | E's own close above it (s_c = 0) | trendline level below the base high, median (ADR) |")
        p("|---|---|---|---|---|---|---|---|")
        p(f"| {era} | n = {len(f):,} | {dist.median():.2f} | {dist.quantile(.25):.2f} .. {dist.quantile(.75):.2f} | {dist.quantile(.1):.2f} / {dist.quantile(.9):.2f} | {int((dist <= 0).sum()):,} ({pct((dist <= 0).mean())}) | {int((f.s_c == 0).sum()):,} ({pct((f.s_c == 0).mean())}) | {f.dist_tl_adr.median():.2f} |")
        p()
        p("First CLOSE above the base high (E = session 0; cumulative; 'never' needs the 60-session window complete):"); p()
        p("| era | n (window complete) | on E itself | by session 5 | by session 20 | by session 60 | never within 60 | window cut (unknown) |")
        p("|---|---|---|---|---|---|---|---|")
        g = f[f.sc_complete == 1]; sc = g.s_c
        row = {k: int(((sc >= 0) & (sc <= k)).sum()) for k in (0, 5, 20, 60)}
        p(f"| {era} | n = {len(g):,} | {row[0]:,} ({pct(row[0]/len(g))}) | {row[5]:,} ({pct(row[5]/len(g))}) | {row[20]:,} ({pct(row[20]/len(g))}) | {row[60]:,} ({pct(row[60]/len(g))}) | {int((sc < 0).sum()):,} ({pct((sc < 0).mean())}) | {int((f.sc_complete == 0).sum())} |")
        NUM[f"A_sc_{era}"] = dict(n=len(g), **{f"by{k}": v for k, v in row.items()}, never=int((sc < 0).sum()))
        p()
        p("Sessions from our fill (E) to that first close above the base high, where it happened within 60:"); p()
        hit = g[g.s_c >= 0].s_c
        p("| era | n | median | quartiles | p90 | share at s_c <= 5 | <= 20 |"); p("|---|---|---|---|---|---|---|")
        p(f"| {era} | n = {len(hit):,} | {hit.median():.0f} | {hit.quantile(.25):.0f} .. {hit.quantile(.75):.0f} | {hit.quantile(.9):.0f} | {pct((hit <= 5).mean())} | {pct((hit <= 20).mean())} |")
        p()
        p("The big movers (s\\* = yesterday's first session 1..60 whose HIGH reached fill + T x ADR20; 60-session window complete): did the stock clear the base high on a close first, and how long from that close to the move?"); p()
        p("| era / threshold | n big movers | closed above the base high at or before s\\* (s_c <= s\\*) | move started before any close above it (s_c > s\\*) | never closed above it within 60 | fill -> first close above base high (s_c): median / quartiles | that close -> the move (s\\* - s_c): median / quartiles | fill -> move (s\\*): median | s_c <= 5 | s_c <= 20 |")
        p("|---|---|---|---|---|---|---|---|---|---|")
        for T in (5, 10):
            col = f"first_{T}adr"
            b = g[(g[col] >= 1) & (g[col] <= 60)]
            before = b[(b.s_c >= 0) & (b.s_c <= b[col])]; after = b[(b.s_c >= 0) & (b.s_c > b[col])]; never = b[b.s_c < 0]
            gap = before[col] - before.s_c
            p(f"| {era}, +{T} ADR | n = {len(b):,} | {len(before):,} ({pct(len(before)/len(b))}) | {len(after):,} ({pct(len(after)/len(b))}) | {len(never):,} ({pct(len(never)/len(b))}) | "
              f"{before.s_c.median():.0f} / {before.s_c.quantile(.25):.0f} .. {before.s_c.quantile(.75):.0f} | {gap.median():.0f} / {gap.quantile(.25):.0f} .. {gap.quantile(.75):.0f} | {b[col].median():.0f} | {pct((before.s_c <= 5).mean())} of those | {pct((before.s_c <= 20).mean())} |")
            NUM[f"A_big_{era}_{T}"] = dict(n=len(b), before=len(before), after=len(after), never=len(never), sc_med=float(before.s_c.median()), gap_med=float(gap.median()), s_med=float(b[col].median()),
                                           sc_le5=float((before.s_c <= 5).mean()), sc_le20=float((before.s_c <= 20).mean()))
        p()
        p("Same, for the fills that never made the move (A bin): how often did they still clear the base high on a close?"); p()
        p("| era | n fills with no +5 ADR move within 60 | closed above the base high within 60 | never |"); p("|---|---|---|---|")
        nb = g[~((g.first_5adr >= 1) & (g.first_5adr <= 60))]
        p(f"| {era} | n = {len(nb):,} | {int((nb.s_c >= 0).sum()):,} ({pct((nb.s_c >= 0).mean())}) | {int((nb.s_c < 0).sum()):,} ({pct((nb.s_c < 0).mean())}) |")
        p()
        p("Where the fill sat vs the move rate (distance below the base high in ADR20 at D, quartiles cut on this era; from the fill, yesterday's columns):"); p()
        p("| era | distance quartile | n (window complete) | >= 5 ADR within 60 | >= 10 ADR | mean R | closed above the base high within 60 |"); p("|---|---|---|---|---|---|---|")
        qs = np.percentile(g.dist_adr, [25, 50, 75]); g = g.copy(); g["dq"] = np.searchsorted(qs, g.dist_adr)
        labs = [f"<= {qs[0]:.2f} (at/near the base high)", f"{qs[0]:.2f}-{qs[1]:.2f}", f"{qs[1]:.2f}-{qs[2]:.2f}", f"> {qs[2]:.2f} (deep in the base)"]
        for i in range(4):
            h = g[g.dq == i]; hc = h[h.complete_60 == 1]
            p(f"| {era} | Q{i+1} {labs[i]} | n = {len(hc):,} | {pct((hc.mfe60_adr_fill >= 5).mean())} | {pct((hc.mfe60_adr_fill >= 10).mean())} | {hc.realized_r.mean():+.3f} | {pct((hc.s_c >= 0).mean())} |")
        p()

        # ── Question B ───────────────────────────────────────────────────────────────────────
        p(f"## B. Does a REAL breakout follow through? ({era}; every entry against its matched control; tail first)"); p()
        # composition of the entry sets
        p("Composition of the entry sets (one row per (ticker, entry day) for the new sets):"); p()
        p("| era | entry set | n | entry days | median ADR20 (unit) | median 63-session return at t-1 | median 20-session dollar volume | notes |"); p("|---|---|---|---|---|---|---|---|")
        fc = f[f.cl_c60.notna()]
        p(f"| {era} | our fills (C0 tl ORH5, from E's close) | n = {len(f):,} | {f.E.nunique()} | {f.adr20.median():.4f} | {f.ret63_D.median():+.3f} | ${f.dv_D.median()/1e6:.0f}M | published rows; retrigger_chain = 1: {int((f.retrigger_chain==1).sum()):,} |")
        p(f"| {era} | R3 — E meets the expansion test | n = {int(f.e_exp.sum()):,} | {f[f.e_exp==1].E.nunique()} | {f[f.e_exp==1].adr20.median():.4f} | {f[f.e_exp==1].ret63_D.median():+.3f} | ${f[f.e_exp==1].dv_D.median()/1e6:.0f}M | range >= 1 ADR: {int(f.e_range_ok.sum()):,} ({pct(f.e_range_ok.mean())}); close in top 30%: {int(f.e_loc_ok.sum()):,} ({pct(f.e_loc_ok.mean())}); volume >= 1.5x: {int(f.e_vol_ok.sum()):,} ({pct(f.e_vol_ok.mean())}) |")
        p(f"| {era} | R3 — E does NOT meet it | n = {int((f.e_exp==0).sum()):,} | {f[f.e_exp==0].E.nunique()} | {f[f.e_exp==0].adr20.median():.4f} | {f[f.e_exp==0].ret63_D.median():+.3f} | ${f[f.e_exp==0].dv_D.median()/1e6:.0f}M | |")
        p(f"| {era} | R1 base-high close (ADR20 at t-1) | n = {len(r):,} | {r.entry_date.nunique()} | {r.adr_t1.median():.4f} | {r.ret63_t1.median():+.3f} | ${r.dv_t1.median()/1e6:.0f}M | from {int(((f.s_c>=0)&(f.s_c<60)).sum()):,} fills reaching a close above the base high in sessions 0..59; dedup removed {int(((f.s_c>=0)&(f.s_c<60)).sum()) - len(r)}; R1 day = E itself {int((r.s_c==0).sum()):,} ({pct((r.s_c==0).mean())}); median s_c {r.s_c.median():.0f}; close over the base high median {r.close_over_base_adr.median():.2f} ADR; next-open gap median {r.gap_next_adr.median():+.2f} ADR; splits in the volume window {int((r.split_in_vol_window==1).sum()) if (r.split_in_vol_window>=0).any() else 'unknown'} |")
        r2, r2n = r[r.r2_exp == 1], r[r.r2_exp == 0]
        p(f"| {era} | R2 expansion breakout (R1 + range/close/volume) | n = {len(r2):,} | {r2.entry_date.nunique()} | {r2.adr_t1.median():.4f} | {r2.ret63_t1.median():+.3f} | ${r2.dv_t1.median()/1e6:.0f}M | range >= 1 ADR: {int(r.r2_range_ok.sum()):,} ({pct(r.r2_range_ok.mean())}); close in top 30%: {int(r.r2_loc_ok.sum()):,} ({pct(r.r2_loc_ok.mean())}); volume >= 1.5x: {int(r.r2_vol_ok.sum()):,} ({pct(r.r2_vol_ok.mean())}); R2 day = E itself {int((r2.s_c==0).sum()):,} |")
        p(f"| {era} | R1 but NOT R2 | n = {len(r2n):,} | {r2n.entry_date.nunique()} | {r2n.adr_t1.median():.4f} | {r2n.ret63_t1.median():+.3f} | ${r2n.dv_t1.median()/1e6:.0f}M | |")
        for K, h in kv.groupby("K"):
            p(f"| {era} | K = {K} (ORH5 first break, from E's close) | n = {len(h):,} | {h.E.nunique()} | {h.adr20.median():.4f} | {h.ret63_D.median():+.3f} | ${h.dv_D.median()/1e6:.0f}M | fill below the base high: median {h.dist_adr.median():.2f} ADR; fill at/above it {pct((h.dist_adr<=0).mean())}; includes the 5 non-mature fills |")
        p()
        sets = [("our fills (from E's close)", f, "cl_", "adr20", "ret63_D"),
                ("R3: E meets the expansion test", f[f.e_exp == 1], "cl_", "adr20", "ret63_D"),
                ("R3: E does not meet it", f[f.e_exp == 0], "cl_", "adr20", "ret63_D"),
                ("R1 base-high close — entry at that close", r, "cl_", "adr_t1", "ret63_t1"),
                ("R1 — entry at the next open", r, "no_", "adr_t1", "ret63_t1"),
                ("R1 — measured from the NEXT close (same-day-effect check)", r, "nc_", "adr_t1", "ret63_t1"),
                ("R2 expansion breakout — entry at that close", r2, "cl_", "adr_t1", "ret63_t1"),
                ("R2 — entry at the next open", r2, "no_", "adr_t1", "ret63_t1"),
                ("R2 — measured from the NEXT close (same-day-effect check)", r2, "nc_", "adr_t1", "ret63_t1"),
                ("R1 but NOT R2 — entry at that close", r2n, "cl_", "adr_t1", "ret63_t1")]
        if (r.split_in_vol_window >= 0).any():
            sets.append(("R2 without the rows with a split in the volume window", r2[r2.split_in_vol_window == 0], "cl_", "adr_t1", "ret63_t1"))
        for K, h in kv.groupby("K"):
            sets.append((f"K = {K} (ORH5 first break, from E's close)", h, "cl_", "adr20", "ret63_D"))
        for label, ent, pre, acol, rcol in sets:
            if len(ent) < 10:
                p(f"**{label}: n = {len(ent)} — too few to judge; no table.**"); p(); continue
            matched_table(label, ent, ctl, pre, acol, rcol, era)
    with open(f"{LOG_DIR}/03_report.md", "w") as fh:
        fh.write("\n".join(L) + "\n")
    with open(f"{LOG_DIR}/03_numbers.json", "w") as fh:
        json.dump(NUM, fh, indent=1, default=float)
    print("\n".join(L))


if __name__ == "__main__":
    main()
