#!/usr/bin/env python3
"""#717 template — Qullamaggie's average good breakout setup, and ranking a day's fires by likeness to it.
Registration: Part 2 of docs/analysis/cb_pick_model_2026-11-13.md (committed BEFORE this ran). Offline, $0, read-only,
era A only; returns are not read; no rule changed.

    python3 .../06_template.py fit   > 06_fit.out     (the template from the 2017-2020 buys, picks W, writes template.json + template.png)
    python3 .../06_template.py test  > 06_test.out    (reads template.json + coef.json; ONCE)
    python3 .../06_template.py sheet <ranking>        (sheet_template_picks.png + key; ranking = sim | simxmodel | model)
"""
import importlib.util, json, os, sys
from datetime import date
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
spec = importlib.util.spec_from_file_location("m", os.path.join(HERE, "02_fit_test.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
P2, P, bv = M.P2, M.P, M.P.bv
os.chdir(REPO); sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts/probes/_717_qm_confidence_1111"))
import rating as RT  # noqa: E402
import sheet as SH   # noqa: E402
plt = SH.plt
PATHS = "/Users/alvinfung/apollo_data/bv1_pick_model_1113/fire_paths90.npz"
TPL = os.path.join(HERE, "template.json")
WS, WMAX, MIN_N, SEED = (40, 60, 90), 90, 40, 717
OK, NO = "ADEI", "BCFGHJK"


def template_paths():
    """The fit-year template set -> (rows [(set, eid, ticker, day, tier, big)], paths n x 90 in daily ranges from the buy level)."""
    import contextlib, io
    r = pd.read_csv("scripts/probes/_717_qm_confidence_1111/ratings.tsv", sep="\t", dtype=str, keep_default_na=False)
    r = r[((r.tier == "High") | (r.big_winner == "1")) & (r.day_cleared != "") & (r.day_cleared <= M.FIT_LAST)]
    with contextlib.redirect_stdout(io.StringIO()):
        buys = {(b["set"], b["eid"]): b for b in RT.load()}
    rows, out = [], []
    for x in r.itertuples():
        b = buys[(x.set, x.eid)]
        t = b["dates"].index(date.fromisoformat(x.day_cleared))
        with np.errstate(invalid="ignore", divide="ignore"):
            adr = bv.adr20_at((b["h"] - b["l"]) / b["c"], t - 1)
        lvl = float(x.buy_point_split_adjusted)
        c = b["c"][max(0, t - WMAX):t]
        p = np.full(WMAX, np.nan); p[WMAX - len(c):] = (c - lvl) / (adr * lvl)
        rows.append((x.set, x.eid, x.ticker, x.day_cleared, x.tier, x.big_winner == "1")); out.append(p)
    return rows, np.array(out)


def load_all():
    df, cal, big = M.load()
    co = json.load(open(M.COEF))["models"]["primary"]
    df["score_model"] = M.X_of(df, co["features"]) @ np.r_[co["intercept"], co["coef"]]
    z = np.load(PATHS)
    f = df.loc[z["idx"]].copy()
    assert f.fire.all() and len(f) == int(df.fire.sum())
    norm = (z["paths"].astype(float) - f.level.to_numpy()[:, None]) / (f.adr20.to_numpy() * f.level.to_numpy())[:, None]
    return f, norm, cal, big


def sims(norm, mean, W):
    """(distance: RMS gap in daily ranges; correlation) over the last W sessions; NaN when under MIN_N sessions."""
    a, m = norm[:, -W:], mean[-W:]
    ok = ~np.isnan(a); n = ok.sum(1)
    d = np.sqrt(np.nansum((a - m) ** 2, 1) / np.maximum(n, 1))
    am = np.nansum(a, 1) / np.maximum(n, 1); mm = (ok * m).sum(1) / np.maximum(n, 1)
    da, dm = np.where(ok, a - am[:, None], 0.0), np.where(ok, m - mm[:, None], 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = (da * dm).sum(1) / np.sqrt((da ** 2).sum(1) * (dm ** 2).sum(1))
    bad = n < min(MIN_N, W)
    d[bad] = np.nan; r[bad] = np.nan
    return d, r


def stage_fit():
    rows, tp = template_paths()
    mean = np.nanmean(tp, 0); q25, q75 = np.nanpercentile(tp, [25, 75], 0)
    print(f"TEMPLATE SET (fit years): {len(rows)} buys — High tier {sum(r[4] == 'High' for r in rows)}, big winners {sum(r[5] for r in rows)}, dated {sum(r[0] == 'dated' for r in rows)}; "
          f"by year {pd.Series([r[3][:4] for r in rows]).value_counts().sort_index().to_dict()}; with all 90 sessions {int((~np.isnan(tp[:, 0])).sum())}")
    print("the mean path, in daily ranges from the buy level (sessions before the break day): " + ", ".join(f"-{k}: {mean[WMAX - k]:+.1f}" for k in (90, 60, 40, 30, 20, 10, 5, 1)))
    f, norm, cal, big = load_all()
    fit = (f.E <= M.FIT_LAST).to_numpy()
    ff = f[fit]
    print(f"\nPICK W on the FIT years (E <= {M.FIT_LAST}; {len(ff):,} fires, {len(M.taken_set(ff))} Qullamaggie buys fire; in-sample by construction):")
    best = None
    for W in WS:
        d, r = sims(norm[fit], mean, W)
        nd = len(M.taken_set(P2.top_k(ff, pd.Series(-d, index=ff.index)))); nr = len(M.taken_set(P2.top_k(ff, pd.Series(r, index=ff.index))))
        print(f"  W = {W}: top 5 by distance takes {nd}; by correlation {nr}")
        if best is None or nd > best[1]:
            best = (W, nd)
    o, mo = len(M.taken_set(P2.top_k(ff, ff.score_order))), len(M.taken_set(P2.top_k(ff, ff.score_model)))
    print(f"  for scale (fit years): order score {o}, the learned model {mo}")
    W = best[0]
    print(f"W = {W} (the registered rule: most buys by the primary distance, ties to the shorter)")
    json.dump({"W": W, "mean": [float(v) for v in mean], "q25": [float(v) for v in q25], "q75": [float(v) for v in q75], "n": len(rows)}, open(TPL, "w"))
    # the picture
    fig, ax = plt.subplots(figsize=(11, 6.5))
    x = np.arange(-W, 0)
    rng = np.random.default_rng(SEED)
    for k in rng.choice(len(tp), size=min(14, len(tp)), replace=False):
        ax.plot(x, tp[k, -W:], color="#888888", lw=0.7, alpha=0.35)
    ax.fill_between(x, q25[-W:], q75[-W:], color="#1f77b4", alpha=0.22, lw=0, label="the middle half of them")
    ax.plot(x, mean[-W:], color="#1f77b4", lw=2.6, label="the average")
    ax.axhline(0, color="black", ls="--", lw=1.1); ax.text(-W + 0.5, 0.25, "the buy level", fontsize=9)
    ax.set_xlabel("sessions before the break day"); ax.set_ylabel("daily ranges from the buy level")
    ax.set_ylim(max(-20, np.nanmin(q25[-W:]) - 4), 3); ax.legend(loc="lower right", frameon=False)
    ax.set_title(f"Qullamaggie's average breakout setup, last {W} sessions before the break, in daily ranges from the buy level\n"
                 f"({len(rows)} of his best-confirmed breakout buys and big winners, 2017-2020; grey = a few of the individual charts)", fontsize=10.5)
    fig.savefig(os.path.join(HERE, "template.png"), dpi=110, bbox_inches="tight"); plt.close(fig)
    print("template.png, template.json written")


def scored():
    f, norm, cal, big = load_all()
    T = json.load(open(TPL)); W = T["W"]
    d, r = sims(norm, np.array(T["mean"]), W)
    f["dist"], f["corr"] = d, r
    te = f[f.E >= M.TEST_FIRST].copy()
    g = te.groupby("ci")
    te["p_model"] = g.score_model.rank(pct=True)
    te["p_sim"] = g.dist.rank(pct=True, ascending=False).fillna(0.0)          # 1 = the most alike that day
    te["p_corr"] = g["corr"].rank(pct=True).fillna(0.0)
    te["s_sim"], te["s_simxmodel"], te["s_model"] = te.p_sim, te.p_sim * te.p_model, te.score_model
    te["s_corr"], te["s_corrxmodel"] = te.p_corr, te.p_corr * te.p_model
    return te, cal, big, W


def stage_test():
    te, cal, big, W = scored()
    days = te.ci.nunique(); fired = M.taken_set(te)
    print(f"TEST — scored once; W = {W}. Days E {te.E.min()} .. {te.E.max()}: {days}; fires {len(te):,}; Qullamaggie buys that fire {len(fired)} ({len(fired & big)} big); fires with no similarity (under {min(MIN_N, W)} sessions): {int(te.dist.isna().sum())}")
    print(f"similarity of the fires that ARE his buys vs the rest: median distance {te[te.is_qm].dist.median():.2f} vs {te[~te.is_qm].dist.median():.2f} daily ranges; "
          f"median within-day similarity percentile of his buys {te[te.is_qm].p_sim.median():.2f} (0.50 = no better than chance; model percentile {te[te.is_qm].p_model.median():.2f})")
    print("\n== the day's top 5 fires by each ranking ==")
    res = {}
    for name, col in (("1 SIMILARITY alone (distance)", "s_sim"), ("2 SIMILARITY x MODEL", "s_simxmodel"), ("3 the learned MODEL alone (baseline)", "s_model"),
                      ("beside: correlation alone", "s_corr"), ("beside: correlation x model", "s_corrxmodel")):
        x = P2.top_k(te, te[col]); s = M.taken_set(x); c = x[x.covered]
        res[col] = (len(s), len(s & big))
        print(f"  {name:38s} buys taken {len(s):>3d}  big {len(s & big):>2d} | picks {len(x):,}  on a Qullamaggie buy {int(x.is_qm.sum()):>3d} = {x.is_qm.mean():6.2%}, {x.is_qm.sum() / days:.3f} a day | bought +-5 (covered) {c.bought.mean():6.2%} | median distance of the picks {x.dist.median():.2f}")
    order = sorted(("s_sim", "s_simxmodel", "s_model"), key=lambda k: (-res[k][0], -res[k][1], {"s_model": 0, "s_sim": 1, "s_simxmodel": 2}[k]))
    print(f"best of the three (most buys, then big winners, then the simpler): {order[0][2:]}")

    print("\n== THE OPERATOR'S EYE: his 12 graded model picks (ok = A D E I; no = B C F G H J K; L conditional) ==")
    sys.path.insert(0, os.path.join(REPO, "tests/fixtures"))
    from breakout_list_grades import MODEL_PICK_GRADES
    allp = te.dist.rank(pct=True, ascending=False)
    rows = {}
    print(f"  {'':2s} {'ticker':6s} {'grade':12s} {'distance':>8s} {'pct that day':>12s} {'pct all test':>12s} {'corr':>6s}  (percentile: 1.00 = the most like the template)")
    for gr in MODEL_PICK_GRADES:
        x = te[(te.ticker == gr.ticker) & (te.ci.map(lambda c: cal[c].isoformat()) == gr.list_date)]
        assert len(x) == 1, gr
        x = x.iloc[0]; rows[gr.sheet_card] = (x.p_sim, allp.loc[x.name], x.dist)
        print(f"  {gr.sheet_card:2s} {gr.ticker:6s} {gr.grade:12s} {x.dist:8.2f} {x.p_sim:12.2f} {allp.loc[x.name]:12.2f} {x['corr']:+6.2f}")
    for lab, k in (("that day's fires", 0), ("all test fires", 1)):
        ok, no = [rows[c][k] for c in OK], [rows[c][k] for c in NO]
        pairs = sum(a > b for a in ok for b in no)
        print(f"  percentile among {lab}: ok median {np.median(ok):.2f} vs no median {np.median(no):.2f}; ok-above-no pairs {pairs} of {len(ok) * len(no)}")


def stage_sheet(which):
    te, cal, big, W = scored()
    sys.path.insert(0, os.path.join(REPO, "tests/fixtures"))
    from breakout_list_grades import MODEL_PICK_GRADES
    graded = {(g.ticker, g.list_date) for g in MODEL_PICK_GRADES}
    te["rank"] = te.groupby("ci")["s_" + which].rank(ascending=False, method="first").astype(int)
    picks = P2.top_k(te, te["s_" + which]).sort_values(["ci", "ticker"]).reset_index(drop=True)
    chosen, seen = [], {t for t, _ in graded}
    for i in np.random.default_rng(SEED).permutation(len(picks)):
        r = picks.iloc[int(i)]
        if r.ticker not in seen:
            seen.add(r.ticker); chosen.append(r)
        if len(chosen) == 12:
            break
    win = {}
    b = pd.read_csv(f"{P2.FX}/buys.tsv", sep="\t", dtype=str, keep_default_na=False)
    w = pd.read_csv(f"{P2.FX}/buys_undated_widened.tsv", sep="\t", dtype=str, keep_default_na=False)
    win.update({"d" + r.eid: f"{r.E} (dated{', BIG WINNER' if r.big_winner == '1' else ''})" for r in b.itertuples()})
    win.update({"w" + r.eid: f"{r.lo}..{r.hi} (undated sighting)" for r in w.itertuples()})
    S, _ = P.setup(); D = S.D
    tid = {}
    for k, t in enumerate(D.tickers):
        tid.setdefault(t, []).append(k)
    OUT = os.path.join(HERE, "sheet_template_picks.png")
    fig = plt.figure(figsize=(26, 18))
    gs = fig.add_gridspec(6, 4, height_ratios=[3, 1] * 3, hspace=0.45, wspace=0.12)
    key = [f"ranking = {which} (W = {W})", "letter|ticker|fire day E (list night D)|rank among that day's fires|similarity percentile that day|distance (daily ranges)|model percentile that day|Qullamaggie bought? (scorecard, on E)|his-buy window|bought within +-5 sessions (panel)"]
    for n, r in enumerate(chosen):
        bars = Di = None
        for k in tid[r.ticker]:
            bb, cidx = P.runner.bars_for(D, k)
            hit = np.flatnonzero(np.asarray(cidx) == r.ci)
            if len(hit) and abs(float(bb.c[hit[0]]) - r.close) < 1e-6 * max(1.0, r.close):
                bars, Di = bb, int(hit[0]); break
        assert bars is not None, r.ticker
        o, h, l, cf, v = (np.asarray(x[:Di + 1], float) for x in (bars.o, bars.h, bars.l, bars.c, bars.v))
        off = max(0, len(cf) - 189)
        o, h, l, c, v = o[off:], h[off:], l[off:], cf[off:], v[off:]
        rr, cc = divmod(n, 4)
        ax = fig.add_subplot(gs[2 * rr, cc]); axv = fig.add_subplot(gs[2 * rr + 1, cc], sharex=ax)
        for k in range(len(c)):
            col = "#26a69a" if c[k] >= o[k] else "#ef5350"
            ax.vlines(k, l[k], h[k], color=col, lw=0.7)
            ax.add_patch(plt.Rectangle((k - 0.3, min(o[k], c[k])), 0.6, max(abs(c[k] - o[k]), 1e-9), color=col))
            axv.bar(k, v[k], color=col, width=0.7)
        for arr, col in ((SH.ema(cf, 10), "#1f77b4"), (SH.ema(cf, 21), "#d62728"), (SH.sma(cf, 50), "#2ca02c")):
            ax.plot(range(len(c)), arr[off:], color=col, lw=0.9)
        ax.hlines(r.level, max(0, len(c) - 46), len(c) + 1, colors="black", linestyles="dashed", lw=1.0)
        ax.set_yscale("log"); ax.yaxis.set_major_formatter(SH.ScalarFormatter()); ax.yaxis.set_minor_formatter(SH.NullFormatter())
        L = chr(ord("A") + n)
        ax.set_title(L, fontsize=13, loc="left"); ax.tick_params(labelsize=6); axv.tick_params(labelsize=5)
        ax.set_xticks([]); axv.set_xticks([])
        key.append(f"{L}|{r.ticker}|{r.E} ({cal[r.ci]})|{r['rank']}|{r.p_sim:.2f}|{r.dist:.2f}|{r.p_model:.2f}|{'YES' if r.is_qm else 'no'}|{'; '.join(win[i] for i in r.qm) or '-'}|{'yes' if r.bought else 'no'}{'' if r.covered else ' (no snapshot within 5 sessions)'}")
    fig.suptitle("Breakout v1 — 12 names; each chart ends the night before the buy day; dashed = the buy level; blue EMA10, red EMA21, green SMA50", fontsize=12)
    fig.savefig(OUT, dpi=100, bbox_inches="tight"); plt.close(fig)
    open(OUT + ".key_do_not_show.txt", "w").write("\n".join(key) + "\n")
    print(f"{OUT}: 12 charts of {len(picks)} '{which}' picks; Qullamaggie buys on the sheet (scorecard): {sum(bool(r.is_qm) for r in chosen)}; bought within +-5 (panel): {sum(bool(r.bought) for r in chosen)}")


if __name__ == "__main__":
    {"fit": stage_fit, "test": stage_test, "sheet": lambda: stage_sheet(sys.argv[2])}[sys.argv[1]]()
