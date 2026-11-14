#!/usr/bin/env python3
"""#717 QUESTION B — "extended / late, looks broken out already" checks (2026-11-14; offline, $0, read-only, ERA A ONLY;
research, no rule changed, nothing deployed). `cb702/` is never opened: every input is an era-A capture of an earlier card.

PRE-REGISTERED BEFORE ANY RESULT WAS COMPUTED (the rules, the pool, the loss rule and the bar are fixed here).

POOL  = the FIRE rows of list_eraA_4pct.parquet (list nights 2017-01..2022-03-31; the unit every earlier card scored) that
        pass the three live checks exactly as _717_lowline_1114/02_score.py applies them: 1d (close > 3% under a 50-day
        lower than 10 sessions ago), A2(10) (50-day lower than 10 sessions ago AND a negative 126-session return), and the
        lower line (ll.flag — the research line 0.212; live is 0.2123). Bridge: 156,695 -> 136,305 -> 120,872 -> 114,824.
BARS  = fires_windows200.npy (200 bars ending the list night D) for fires; _717_context_1114/fixtures_windows200.npy for
        Qullamaggie's scorecard / High rows. ADR20 = the captured adr20 (a FRACTION of the close).
LEVEL = the live list's level, breakout_v1.v1_gates: the LOWER of the lowest qualifying range high (bv.range_levels) and the
        settled 5-day level (bv.settled_level), computed with the module's own functions; bridged against the captured level.
        STRUCTURAL NOTE written before running: both parts are maxima that include the list night's own high, so
        level(D) >= high(D) >= close(D). E1 as worded can therefore never fire and E3 can only fire on wick-settled levels
        (a close before the wick day above the highs after it). They are run as worded and reported as such; the
        supplementary E1b / E3b below measure the same idea against the level the list showed on EARLIER nights.

THE RULES (each flags = takes the name off; a blank measure passes):
  E1(k)   (close(D) / level(D) - 1) / ADR20 > k                       k in 0.5, 1, 1.5      [as asked]
  E2(k)   (close(D) / SMA10(D) - 1) / ADR20 > k, SMA10 = mean of the 10 closes ending D   k in 1, 2, 3   [as asked]
  E3      close(D-3) or close(D-2) or close(D-1) > level(D)            no threshold          [as asked]
  E1b(k)  (close(D) / level(D-3) - 1) / ADR20 > k, level(D-3) = the live level as the list computed it 3 nights earlier
          (bars <= D-3)                                                k in 0.5, 1, 1.5      [supplementary, added by this card]
  E3b     for some s in {D-3, D-2, D-1}: close(s) > level(s-1) — the level the list showed the night before was closed
          through on one of the 3 sessions before the list night       no threshold          [supplementary]
LOSS  a Qullamaggie buy is LOST when none of its fired scorecard sessions survives (02_score.py's convention), counted
      BEYOND what the three live checks already lose. Denominator for the 2% = the fired buys that survive the three checks.
BAR   a check FAILS if it loses ANY big winner (big == 1) or MORE THAN 2% of his buys. High-tier losses are reported (the
      56 listed High rows and the High-tier fired buys), fires a day removed = median over all 1,322 list nights (zeros in).
GRADED PICKS  all 60 MODEL_PICK_GRADES are era-A fire rows (2017..2022-03, matched on ticker + list night, exactly one row).
      EXTENDED SET (named before running): sheet 4 PS 2019-05-01, GBT 2019-06-24, WPX 2018-04-23, PINS 2020-10-22;
      sheet 5 WPM 2020-05-13, TAL 2017-09-08, TRXC 2018-06-25.  OK/GOOD SET = grade ok or good, TAL excluded.
      Reported on all 60 and on those passing the three live checks.
BEST  among passing checks: the most extended-set picks flagged, then fewest ok/good flagged, then fewest buys lost.

    python3 scripts/probes/_717_extended_1114/01_extended.py > scripts/probes/_717_extended_1114/01_extended.out
"""
import os, sys
from multiprocessing import get_context
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
os.chdir(REPO); sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts/probes/_717_lowline_1114")); sys.path.insert(0, os.path.join(REPO, "scripts/probes/_717_context_1114"))
import ll, ctx  # noqa: E402
from agents.market_intelligence import breakout_v1 as bv  # noqa: E402
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 200)
OUTD = "/Users/alvinfung/apollo_data/bv1_extended_1114"
LLD = "/Users/alvinfung/apollo_data/bv1_lowline_1114"
EXT = [("PS", "2019-05-01"), ("GBT", "2019-06-24"), ("WPX", "2018-04-23"), ("PINS", "2020-10-22"),
       ("WPM", "2020-05-13"), ("TAL", "2017-09-08"), ("TRXC", "2018-06-25")]
KS = {"E1": (0.5, 1.0, 1.5), "E2": (1.0, 2.0, 3.0), "E1b": (0.5, 1.0, 1.5)}


def live_level(h, l, c, D):
    rl = bv.range_levels(h, l, D)
    settled, level5, wick_k = bv.settled_level(h, l, c, D)
    if rl and float(rl[0]["level"]) < settled:
        return float(rl[0]["level"]), "range"
    return settled, ("settled_after_wick" if wick_k is not None else "five_day")


def row_measures(w):
    """w (4, 200) o/h/l/c NaN-padded left, index -1 = D -> the raw measures (no ADR, no threshold)."""
    w = np.asarray(w, np.float64); ok = np.isfinite(w[1]) & np.isfinite(w[2]) & np.isfinite(w[3])
    h, l, c = w[1][ok], w[2][ok], w[3][ok]; D = len(c) - 1
    out = dict(lv0=np.nan, src="", lv1=np.nan, lv2=np.nan, lv3=np.nan, lv4=np.nan, c0=np.nan, c1=np.nan, c2=np.nan, c3=np.nan, sma10=np.nan, nb=D + 1)
    if D < 30:
        return out
    out["lv0"], out["src"] = live_level(h, l, c, D)
    for j in (1, 2, 3, 4):
        out[f"lv{j}"] = live_level(h, l, c, D - j)[0]
    for j in (0, 1, 2, 3):
        out[f"c{j}"] = c[D - j]
    out["sma10"] = c[D - 9:D + 1].mean()
    return out


def _work(args):
    path, pos = args
    W = np.load(path, mmap_mode="r")
    return [row_measures(W[p]) for p in pos]


def measure_file(path, pos):
    chunks = [(path, pos[i:i + 2000]) for i in range(0, len(pos), 2000)]
    with get_context("fork").Pool(8) as pool:
        res = pool.map(_work, chunks)
    return pd.DataFrame([r for ch in res for r in ch])


def add_flags(d):
    """d has lv0..lv4, c0..c3, sma10, adr20 -> the continuous measures and every flag column."""
    eps = 1e-6
    d["e1"] = (d.c0 / d.lv0 - 1) / d.adr20
    d["e2"] = (d.c0 / d.sma10 - 1) / d.adr20
    d["e1b"] = (d.c0 / d.lv3 - 1) / d.adr20
    for k in KS["E1"]: d[f"E1({k})"] = (d.e1 > k).fillna(False)
    for k in KS["E2"]: d[f"E2({k})"] = (d.e2 > k).fillna(False)
    d["E3"] = ((d.c1 > d.lv0 * (1 + eps)) | (d.c2 > d.lv0 * (1 + eps)) | (d.c3 > d.lv0 * (1 + eps))).fillna(False)
    for k in KS["E1b"]: d[f"E1b({k})"] = (d.e1b > k).fillna(False)
    d["E3b"] = ((d.c1 > d.lv2 * (1 + eps)) | (d.c2 > d.lv3 * (1 + eps)) | (d.c3 > d.lv4 * (1 + eps))).fillna(False)
    return d
RULES = [f"E1({k})" for k in KS["E1"]] + [f"E2({k})" for k in KS["E2"]] + ["E3"] + [f"E1b({k})" for k in KS["E1b"]] + ["E3b"]


def load():
    """_717_lowline_1114/02_score.py's load(), verbatim in substance."""
    df = pd.read_parquet(ctx.CAP)
    cal = [ctx.date.fromisoformat(s) for s in open(ctx.CAP + ".cal.txt").read().split()]
    assert cal[-1] < ctx.date(2025, 1, 1)
    nights = sorted(df.ci.unique())
    f = df[df.fire].join(pd.read_parquet(ctx.MEASF), rsuffix="_m"); assert (f.base_len == f.base_len_m).all()
    tr = pd.read_parquet(ctx.TRENDF); assert (tr.index == f.index).all(); f = f.join(tr)
    f["Dd"] = [cal[c].isoformat() for c in f.ci]; f["Ed"] = [cal[c + 1].isoformat() for c in f.ci]
    assert f.Dd.max() <= "2022-03-31" and f.Dd.min() >= "2016-12-30", (f.Dd.min(), f.Dd.max())   # first list night 2016-12-30 (its fire day is 2017-01-03), as on every earlier card
    CX = os.path.join(REPO, "scripts/probes/_717_context_1114")
    def fx(name, keys):
        a = pd.read_csv(os.path.join(ctx.PREV, name), sep="\t", dtype={"eid": str})
        b = pd.read_csv(os.path.join(CX, name), sep="\t", dtype={"eid": str})
        assert len(a) == len(b) and all((a[k].astype(str) == b[k].astype(str)).all() for k in keys), name
        a["w"] = b.wid; return a
    WX = np.load(os.path.join(CX, "fixtures_windows200.npy"))
    sc = fx("scorecard_rows.tsv", ["set", "eid", "E", "fired"]); sc["key"] = sc.set + sc.eid; sc["w"] = sc.w.astype(int)
    sc["ret126"] = ctx.ret126_of(WX[sc.w.to_numpy()]); assert sc.E.max() < "2025-01-01"
    hi_all = fx("high_rows.tsv", ["set", "eid", "E", "ok"]); hi = hi_all[hi_all.ok == 1].copy(); hi["w"] = hi.w.astype(int)
    assert len(hi) == 56
    return f, sc, hi, nights, cal, WX, os.path.join(CX, "fixtures_windows200.npy")


if __name__ == "__main__":
    f, sc, hi, nights, cal, WX, WXP = load()
    m = pd.read_parquet(os.path.join(LLD, "fires_lowline.parquet")); assert (m.index == f.index).all()
    f = f.join(m); f["pos"] = np.arange(len(f)); f["OUT"] = ll.flag(f.V3, f.LS30, f.nbars)
    ONE_D = lambda d: ~((d.u50 < -0.03) & (d.s50_chg10 < 0))
    A2 = lambda d: ~((d.s50_chg10 < 0) & (d.ret126 < 0))
    KEEP3 = lambda d: ONE_D(d) & A2(d) & ~d.OUT
    f["keep3"] = KEEP3(f)
    f1 = f[ONE_D(f)]; f2 = f1[A2(f1)]; pool0 = f2[~f2.OUT]
    print("== BRIDGE ==")
    print(f"  pool: fires {len(f):,} -> {len(f1):,} -> {len(f2):,} -> {len(pool0):,} after the three live checks (expect 156,695 / 136,305 / 120,872 / 114,824)")
    assert (len(f), len(f1), len(f2), len(pool0)) == (156695, 136305, 120872, 114824) and len(pool0) == int(f.keep3.sum())

    # graded picks (all 60 are era-A fire rows)
    sys.path.insert(0, os.path.join(REPO, "tests/fixtures"))
    from breakout_list_grades import MODEL_PICK_GRADES
    assert len(MODEL_PICK_GRADES) == 60
    gidx = []
    for g in MODEL_PICK_GRADES:
        x = f[(f.ticker == g.ticker) & (f.Dd == g.list_date)]; assert len(x) == 1, g
        gidx.append(x.index[0])
    need = f[f.keep3 | f.index.isin(gidx)]
    cache = os.path.join(OUTD, "fires_extended_raw.parquet")
    if os.path.exists(cache):
        raw = pd.read_parquet(cache); assert (raw.index == need.index).all()
    else:
        raw = measure_file(os.path.join(LLD, "fires_windows200.npy"), need.pos.to_numpy()); raw.index = need.index
        raw.to_parquet(cache)
    p = need.join(raw); p = add_flags(p)
    rel = (p.lv0 / p.level - 1).abs()
    print(f"  level bridge (module functions on the 200-bar window vs the captured live level): equal within 1e-4 on {int((rel < 1e-4).sum()):,} of {len(p):,} ({(rel < 1e-4).mean():.3%}); max rel diff {rel.max():.4f}")
    print(f"  close bridge: max |c0/close - 1| = {(p.c0 / p.close - 1).abs().max():.2e}")
    print(f"  level source on the pool: {p[p.keep3].src.value_counts().to_dict()}")
    print(f"  STRUCTURAL: pool rows with close(D) > level(D): {int((p[p.keep3].c0 > p[p.keep3].lv0 * (1 + 1e-6)).sum())} (expected 0 by construction)")
    pool = p[p.keep3].copy()
    assert len(pool) == 114824

    # Qullamaggie rows
    def fixture_rows(d):
        r = measure_file(WXP, d.w.to_numpy()); r.index = d.index
        return add_flags(d.join(r, rsuffix="_x"))
    V, L, n = ll.measure(WX[sc.w.to_numpy()]); sc["OUT"] = ll.flag(V, L, n)
    sc = fixture_rows(sc)
    V, L, n = ll.measure(WX[hi.w.to_numpy()]); hi["OUT"] = ll.flag(V, L, n)
    hi = fixture_rows(hi)
    F = sc[sc.fired == 1].copy()
    relq = (F.lv0 / F.level - 1).abs()
    print(f"  Qullamaggie fired sessions: level recomputed == the scorecard level within 1e-4 on {int((relq < 1e-4).sum())} of {len(F)}; max rel diff {relq.max():.4f}")
    def lost(keep):
        s = F[keep(F)]
        return F[~F.key.isin(s.key)].drop_duplicates("key")
    lost3 = lost(KEEP3)
    surv = F.key.nunique() - len(lost3)
    bigs = F.drop_duplicates("key"); nbig = int(bigs.big.sum()); nbig_surv = int(bigs[~bigs.key.isin(lost3.key)].big.sum())
    print(f"  Qullamaggie fired buys {F.key.nunique()}; lost by the three live checks {len(lost3)}; surviving (the 2% denominator) {surv}; 2% = {0.02 * surv:.1f} buys")
    print(f"  big winners among fired buys {nbig} (of the 26; the rest never fired), surviving the three checks {nbig_surv}; High-tier fired buys {int((bigs.tier == 'High').sum())}")

    def perday(d):
        return d.groupby("ci").size().reindex(nights).fillna(0)
    base_n = perday(pool)
    TOP = lambda d: set(map(tuple, d.sort_values("dollar_vol20", ascending=False).groupby("ci").head(5)[["ci", "ticker"]].to_numpy()))
    t0 = TOP(pool)
    G = p.loc[gidx].copy()
    G["grade"] = [g.grade for g in MODEL_PICK_GRADES]; G["words"] = [g.operator_words for g in MODEL_PICK_GRADES]
    G["sheet"] = [os.path.basename(g.sheet) for g in MODEL_PICK_GRADES]; G["card"] = [g.sheet_card for g in MODEL_PICK_GRADES]
    G["ext"] = [(t, d) in EXT for t, d in zip(G.ticker, G.Dd)]; assert int(G.ext.sum()) == 7
    G["okgood"] = G.grade.isin(["ok", "good"]) & ~G.ext
    print(f"  graded picks 60: extended set 7 ({int((G.ext & G.keep3).sum())} pass the three checks); ok/good set {int(G.okgood.sum())} ({int((G.okgood & G.keep3).sum())} pass); other no/conditional {int((~G.ext & ~G.okgood).sum())}")

    rows = []
    detail = []
    for r in RULES:
        fl = pool[r]
        after = perday(pool[~fl]); rem = base_n - after
        t1 = TOP(pool[~fl])
        x = lost(lambda d: KEEP3(d) & ~d[r]); x = x[~x.key.isin(lost3.key)]
        fs = F[KEEP3(F) & F[r]]
        nl, nb_, nh = len(x), int(x.big.sum()), int((x.tier == "High").sum())
        hl = hi[hi[r]]
        passed = (nb_ == 0) and (nl / surv <= 0.02)
        rows.append(dict(rule=r, flagged=int(fl.sum()), pct=f"{fl.mean():.1%}", fires_med=f"{base_n.median():.0f}->{after.median():.0f}", removed_med=rem.median(), removed_mean=round(rem.mean(), 1),
                         top5_replaced=f"{1 - len(t0 & t1) / len(t0):.1%}",
                         qm_lost=nl, qm_lost_pct=f"{nl / surv:.1%}", high_lost=nh, big_lost=nb_, qm_sessions_flagged=len(fs), high56_flagged=len(hl),
                         ext_flag=f"{int(G[G.ext][r].sum())}/7", ext_flag_pass3=f"{int(G[G.ext & G.keep3][r].sum())}/{int((G.ext & G.keep3).sum())}",
                         okgood_flag=f"{int(G[G.okgood][r].sum())}/{int(G.okgood.sum())}", okgood_flag_pass3=f"{int(G[G.okgood & G.keep3][r].sum())}/{int((G.okgood & G.keep3).sum())}",
                         other_flag=f"{int(G[~G.ext & ~G.okgood][r].sum())}/{int((~G.ext & ~G.okgood).sum())}",
                         VERDICT="PASS" if passed else "FAIL"))
        detail.append(f"  {r}: lost buys: " + (", ".join(f"{q.ticker} {q.E} ({q.tier}{', BIG' if q.big else ''})" for q in x.itertuples()) or "none")
                      + f" | big-winner sessions flagged (buy may survive): {fs[fs.big == 1][['ticker', 'E']].values.tolist()} | listed High rows flagged: {hl[['ticker', 'E']].values.tolist()}"
                      + f" | extended flagged: {G[G.ext & G[r]].ticker.tolist()} | ok/good flagged: {G[G.okgood & G[r]].ticker.tolist()}")
    T = pd.DataFrame(rows)
    print(f"\n== RESULT TABLE (era A, pool = {len(pool):,} fires passing the three live checks; {len(nights)} list nights) ==")
    print(T.to_string(index=False))
    T.to_csv(os.path.join(HERE, "01_result_table.tsv"), sep="\t", index=False)
    print("\n== WHICH ==")
    print("\n".join(detail))
    print(f"\n  E3 flags by level source: {pool[pool.E3].src.value_counts().to_dict()}; E3b: {pool[pool.E3b].src.value_counts().to_dict()}")

    print("\n== THE 7 EXTENDED PICKS + all 60 graded: raw measures (diagnostic; printed after the rules were fixed) ==")
    cols = ["sheet", "card", "ticker", "Dd", "grade", "ext", "keep3", "src", "e1", "e1b", "e2", "E3", "E3b"] + [r for r in RULES if r not in ("E3", "E3b")]
    Gs = G[cols].copy(); Gs[["e1", "e1b", "e2"]] = Gs[["e1", "e1b", "e2"]].round(2)
    for c in RULES + ["ext", "keep3"]: Gs[c] = Gs[c].astype(int)
    print(Gs.sort_values(["ext", "sheet", "card"], ascending=[False, True, True]).to_string(index=False))
    G[cols + ["words", "lv0", "lv3", "c0", "sma10", "adr20"]].to_csv(os.path.join(HERE, "01_graded_rows.tsv"), sep="\t", index=False)
    print("\n== DISTRIBUTIONS on the pool (diagnostic) ==")
    print(pool[["e1", "e1b", "e2"]].describe(percentiles=[.5, .75, .9, .95, .99]).round(2).to_string())
    print("  Qullamaggie fired sessions surviving the three checks:")
    print(F[KEEP3(F)][["e1", "e1b", "e2"]].describe(percentiles=[.5, .75, .9, .95, .99]).round(2).to_string())
    print("  big-winner fired sessions (surviving the three checks), max per buy of e2 / e1b — the buy is lost at a threshold under its MIN across sessions:")
    bw = F[KEEP3(F) & (F.big == 1)].groupby(["key", "ticker"]).agg(E=("E", "first"), e2_min=("e2", "min"), e1b_min=("e1b", "min"), E3b_all=("E3b", "all"), n=("E", "size")).round(2)
    print(bw.sort_values("e2_min", ascending=False).head(12).to_string())
    pool[["ci", "ticker", "Dd", "Ed", "dollar_vol20", "adr20", "level", "lv0", "lv3", "src", "e1", "e1b", "e2"] + RULES].to_parquet(os.path.join(OUTD, "pool_extended_flags.parquet"))
    F[["key", "ticker", "E", "tier", "big", "adr20", "level", "lv0", "lv3", "src", "e1", "e1b", "e2", "OUT"] + RULES].assign(keep3=KEEP3(F)).to_csv(os.path.join(HERE, "01_qm_fired_rows.tsv"), sep="\t", index=False)
    print("\nsaved:", os.path.join(OUTD, "pool_extended_flags.parquet"), os.path.join(OUTD, "fires_extended_raw.parquet"), "01_result_table.tsv 01_graded_rows.tsv 01_qm_fired_rows.tsv")
