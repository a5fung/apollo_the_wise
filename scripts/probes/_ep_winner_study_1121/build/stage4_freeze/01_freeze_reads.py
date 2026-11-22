#!/usr/bin/env python3
"""STAGE 4 / step 6 — code HIS READS (H1-H3) + H4 (= B2), corrupt-E test, discovery yes/no COUNTS (no outcome).
OUTCOME-FREE: no return, no label, no bar dated after E is used for any event. Enforced three ways:
  (1) every event's series is TRUNCATED at E before the coding function sees it, and E's high / low / close / volume are replaced by
      NaN — asserted for every event (for E >= 2021-01-01 this IS the "confirm outcomes not read" assert);
  (2) the coding function cuts to calendar index < ci(E) again;
  (3) the corrupt-E test (garbage in E's h/l/c/v and in every later bar) must change nothing.
NOT opened: stage3/discovery_outcomes.tsv.gz, _594 events_scored.tsv.gz, run.txt, any minute bar.
Run: python3 01_freeze_reads.py > 01_freeze_reads.txt"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
STAGE1 = HERE.parent / "stage1"
sys.path.insert(0, str(STAGE1))
import common as C      # noqa: E402
import features as F    # noqa: E402
import stats as S       # noqa: E402
import hreads as H      # noqa: E402

FT_SHA = "ade1d7802eaf70aa60a9b5514d79b72084876d9601b0999328c9b1aad0cf0de7"
CONF_FIRST = "2021-01-01"
PATTERNS = ("huge (1e9, volume 1e15)", "tiny (1e-9, volume 0)", "random lognormal")

print("# STAGE 4 / 01 — his gallery reads H1-H3 + H4 (ADR20), frozen BEFORE any confirm outcome (prereg §6 step 6, §11)")
print(f"prereg sha256 at this run {C.sha(C.PREREG)}")
print(f"code sha256: hreads.py {C.sha(HERE / 'hreads.py')} | this script {C.sha(__file__)}")
print(f"stage-1 code sha256 (unchanged, imported read-only): common.py {C.sha(STAGE1 / 'common.py')} | features.py {C.sha(STAGE1 / 'features.py')} | stats.py {C.sha(STAGE1 / 'stats.py')}")
ft_sha = C.sha(STAGE1 / "feature_table.tsv.gz")
assert ft_sha == FT_SHA
print(f"feature_table.tsv.gz sha256 {ft_sha} (ASSERT OK = the stage-1 table)")

ev = C.build_population(verbose=lambda *_: None)
cal = C.calendars()
bars = C.bars_cached(ev, cal, verbose=lambda *_: None)
flags = C.load_flags()
breaks = C.load_breaks()
T = pd.read_csv(STAGE1 / "feature_table.tsv.gz", sep="\t", keep_default_na=False, na_values=[""], dtype={"ticker": str, "E": str, "year": str})
assert len(T) == len(ev) == 4665 and (T.ticker.to_numpy() == ev.ticker.to_numpy()).all() and (T.E.to_numpy() == ev.E.to_numpy()).all() and (T.era.to_numpy() == ev.era.to_numpy()).all()
N = len(ev)


def truncated(r):
    """series cut at E (inclusive), E's h/l/c/v = NaN. Returns (series, i)."""
    d, ci, o, h, l, c, v = bars[(r.era, r.ticker)]
    ciE = int(np.searchsorted(cal[r.era], r.E))
    i = int(np.searchsorted(ci, ciE))
    assert ci[i] == ciE and d[i] == r.E
    h2, l2, c2, v2 = h[:i + 1].copy(), l[:i + 1].copy(), c[:i + 1].copy(), v[:i + 1].copy()
    h2[i] = l2[i] = c2[i] = v2[i] = np.nan
    return (d[:i + 1], ci[:i + 1], o[:i + 1].copy(), h2, l2, c2, v2), i


def run(r, series):
    return H.h_features(r.era, r.ticker, r.E, series, cal[r.era], flags[r.era].get(r.ticker, []), breaks[r.era].get(r.ticker, []))


# ════════════════ the coding, every event, on a series that ENDS AT E with E's h/l/c/v blanked ════════════════
vals_all, nulls_all, parts_all = [], [], []
n_conf_assert = 0
for k in range(N):
    r = ev.iloc[k]
    series, i = truncated(r)
    assert series[0][-1] == r.E and len(series[1]) == i + 1                      # NOTHING after E is handed in
    assert np.isnan(series[3][-1]) and np.isnan(series[4][-1]) and np.isnan(series[5][-1]) and np.isnan(series[6][-1])   # E's h/l/c/v blanked
    if r.E >= CONF_FIRST:
        n_conf_assert += 1
    vv, nn, pp = run(r, series)
    assert set(vv) | set(nn) == set(H.HS) and not (set(vv) & set(nn))
    vals_all.append(vv); nulls_all.append(nn); parts_all.append(pp)
assert n_conf_assert == int((ev.set == "CONF").sum()) == 2251
print(f"\nCONFIRM OUTCOMES NOT READ — ASSERT OK: for all {N} events (incl. all {n_conf_assert} confirm events, E >= {CONF_FIRST}) the series handed to the coding"
      f" ends AT E and E's high / low / close / volume are NaN; no bar after E, no return and no label is computed in this script.")

O = ev[["era", "ticker", "E", "set", "year", "month", "quarter", "sectype"]].copy()
for hname in H.HS:
    O[hname] = [v.get(hname, np.nan) for v in vals_all]
    O[hname + "_null"] = [n.get(hname, "") for n in nulls_all]
    assert (O[hname].notna() == (O[hname + "_null"] == "")).all()
# H4 = benchmark B2 (ADR20) — NOT recomputed: the stage-1 column, same definition (§4.0 ADR20, §4.1 B2)
O["H4"] = T.B2.to_numpy()
O["H4_null"] = T.B2_null.fillna("").to_numpy()
assert (O.H4.notna() == (O.H4_null == "")).all()
for p in ("open", "sma200", "sma200_lag21", "sma50", "ema10", "ema21"):
    O["part_" + p] = [pp.get(p, np.nan) for pp in parts_all]
# logical nesting (H2 yes => H1 yes; H3 yes => H1 no)
both = O.H1.notna() & O.H2.notna()
assert ((O.H2[both] == 1) <= (O.H1[both] == 1)).all()
assert not ((O.H3 == 1) & (O.H1 == 1)).any()
out = HERE / "h_reads.tsv.gz"
O.to_csv(out, sep="\t", index=False, float_format="%.10g", compression={"method": "gzip", "mtime": 0})
print(f"written {out.name}: {len(O)} rows, sha256 {C.sha(out)}  (the confirm run must read H1-H4 from THIS file)")

# ════════════════ corrupt-E test — the frozen 600-event sample of stage1/05_corrupt.py ════════════════
print("\n## CORRUPT-E TEST (prereg §5.7 / §4.1 (c)): E's high / low / close / volume + EVERY later bar (o, h, l, c, v) replaced by garbage; H1-H4 must not change")
samp = sorted(np.random.default_rng(C.SEED).choice(N, 600, replace=False).tolist())
print(f"sample: default_rng(1121).choice({N}, 600, replace=False) — the same frozen 600 events as stage1/05_corrupt.py (b); 3 garbage patterns each")


def garbage(kind, n, rng):
    if kind == 0:
        return np.full(n, 1e9), np.full(n, 1e15)
    if kind == 1:
        return np.full(n, 1e-9), np.zeros(n)
    return np.exp(rng.normal(3.0, 3.0, n)), np.exp(rng.normal(12.0, 4.0, n))


changed = {h: [0, 0, 0] for h in H.HS + ["H4"]}
leak_changed = 0
leak_scored = 0
for k in samp:
    r = ev.iloc[k]
    rng = np.random.default_rng([C.SEED, k])
    d, ci, o, h, l, c, v = bars[(r.era, r.ticker)]
    ciE = int(np.searchsorted(cal[r.era], r.E)); i = int(np.searchsorted(ci, ciE))
    base_v, base_n = vals_all[k], nulls_all[k]
    sma = parts_all[k].get("sma200")
    leak_scored += int(sma is not None)
    for kind in range(3):
        o2, h2, l2, c2, v2 = o.copy(), h.copy(), l.copy(), c.copy(), v.copy()
        n = len(ci) - i
        gp, gv = garbage(kind, n, rng)
        h2[i:] = gp; l2[i:] = gp * 0.5; c2[i:] = gp * 0.75; v2[i:] = gv
        o2[i + 1:] = gp[1:]
        gv_, gn_, _ = run(r, (d, ci, o2, h2, l2, c2, v2))
        for hn in H.HS:
            if gn_.get(hn) != base_n.get(hn) or (hn in base_v) != (hn in gv_) or (hn in base_v and base_v[hn] != gv_[hn]):
                changed[hn][kind] += 1
        # H4 (= B2): the stage-1 entry point re-run on the corrupted copy vs the frozen table value
        sd, sci, so, sh, sl, sc, sv = bars[(r.era, "SPY")]
        fv, fn = F.event_features(r.era, r.ticker, r.E, (d, ci, o2, h2, l2, c2, v2), (sd, sci, so, sh, sl, sc, sv), cal[r.era], flags[r.era].get(r.ticker, []),
                                  breaks[r.era].get(r.ticker, []), float(r.prev_close_raw), float(r.med_dv20),
                                  e_row_fill=(float(h2[i]), float(l2[i]), float(c2[i]), float(v2[i])))
        tb = O.H4.iat[k]
        if ("B2" in fv) != bool(np.isfinite(tb)) or ("B2" in fv and not np.isclose(fv["B2"], tb, rtol=1e-9, atol=0)) or fn.get("B2", "") != O.H4_null.iat[k]:
            changed["H4"][kind] += 1
        # positive control: a deliberately LEAKY read "close(E) < SMA200" under the HUGE-garbage close vs the TINY-garbage close.
        # E's REAL close is never read (it is an outcome, prereg §2): only two garbage closes are compared, as stage1/05_corrupt.py did.
        if sma is not None and kind == 1:
            leak_changed += int((0.75e9 < sma) != (float(c2[i]) < sma))
print(f"{'read':6} {'non-NULL of 600':>16}  " + " | ".join(p.rjust(26) for p in PATTERNS) + "   <- events whose value or NULL reason CHANGED")
for hn in H.HS + ["H4"]:
    print(f"{hn:6} {int(O[hn].iloc[samp].notna().sum()):>16}  " + " | ".join(str(x).rjust(26) for x in changed[hn]))
tot = sum(sum(x) for x in changed.values())
print(f"positive control (the test can fail): a deliberately leaky read 'close(E) < SMA200' answers differently under the huge-garbage close than under the tiny-garbage close on {leak_changed} of the {leak_scored} scored sample events (E's real close is never read)")
assert leak_changed == leak_scored > 0, "positive control did not fire"
assert tot == 0, "LOOK-AHEAD: a read changed under the corrupt-E test"
print(f"CORRUPT-E RESULT: PASS — 0 changed on H1, H2, H3, H4 across 600 events x 3 patterns (total changed {tot}).")

# ════════════════ NULL counts ════════════════
print("\n## NULL counts per read (reason: n), by set and era")
for hn in H.HS + ["H4"]:
    for st, era in (("DISC", "A"), ("CONF", "A"), ("CONF", "B")):
        m = (O.set == st) & (O.era == era)
        vc = O.loc[m & (O[hn + "_null"] != ""), hn + "_null"].value_counts().to_dict()
        print(f"  {hn} {st} era {era}: events {int(m.sum()):4d} | scored {int((m & O[hn].notna()).sum()):4d} | NULL {vc if vc else '{}'}")
print("  per year scored / events (H1 · H2):")
for (era, y), g in O.groupby(["era", "year"]):
    print(f"    era {era} {y}: events {len(g):3d} | H1/H3 scored {int(g.H1.notna().sum()):3d} | H2 scored {int(g.H2.notna().sum()):3d} | H4 scored {int(g.H4.notna().sum()):3d}")
for era in "AB":
    for hn in ("H1", "H2"):
        s = O[(O.era == era) & O[hn].notna()]
        print(f"    era {era}: first E scored on {hn} = {s.E.min()}")

# ════════════════ discovery yes / no counts — NO OUTCOME ════════════════
print("\n## DISCOVERY yes / no COUNTS (transparency only — NO outcome is read or joined here; his reads skip the §5.2 gates)")
Dm = (O.set == "DISC").to_numpy()
Cm = (O.set == "CONF").to_numpy()
for hn in H.HS:
    for lab, m in (("DISCOVERY", Dm), ("CONFIRM", Cm)):
        s = O.loc[m, hn]
        sc = int(s.notna().sum()); y = int((s == 1).sum()); n_ = int((s == 0).sum())
        small = min(y, n_)
        print(f"  {hn} {H.HNAMES[hn]:48s} {lab:9s}: scored {sc:4d} of {int(m.sum())} | yes {y:4d} ({y / sc:.1%}) | no {n_:4d} ({n_ / sc:.1%}) | smaller group {small} = {small / sc:.1%}"
              f" -> §4.1 two-group minimum (>= 100 and >= 15%): {'met' if small >= 100 and small / sc >= 0.15 else 'NOT met'}")
    for y_, g in O[Dm].groupby("year"):
        s = g[hn]
        print(f"      {y_}: scored {int(s.notna().sum()):3d} | yes {int((s == 1).sum()):3d} | no {int((s == 0).sum()):3d}")
s = O.loc[Dm, "H4"]
t4 = S.assign_thirds(O[Dm].reset_index(drop=True), "H4", ["era", "month"], S.MIN_MONTH, True)
print(f"  H4 {H.HNAMES['H4']} DISCOVERY: scored {int(s.notna().sum())} of {int(Dm.sum())} | thirds within (era, month >= 6 scored), mid-rank ties: bottom {int((t4 == 0).sum())} · middle {int((t4 == 1).sum())} · top {int((t4 == 2).sum())} | not assigned {int((t4 < 0).sum())}")

print("\n## H1 x H2 x H3 cross-tab (events scored on all three; counts only) — the reads are nested, not independent")
for lab, m in (("DISCOVERY", Dm), ("CONFIRM", Cm)):
    g = O[m & O.H1.notna().to_numpy() & O.H2.notna().to_numpy() & O.H3.notna().to_numpy()]
    ct = g.groupby(["H1", "H2", "H3"]).size()
    print(f"  {lab} (n {len(g)}): " + " · ".join(f"H1 {'yes' if a else 'no'} / H2 {'yes' if b else 'no'} / H3 {'yes' if c_ else 'no'}: {n_}" for (a, b, c_), n_ in ct.items()))

# ════════════════ his named charts (gallery A sheet 1 + its failure sheet) — codings only, no outcome column read ════════════════
print("\n## HIS NAMED CHARTS (gallery A sheet 1 / fail 1, discovery; ticker + E hardcoded from the sheet key — no outcome column read)")
NAMED = [("ACB", "2020-05-21", "failure — 'clear downtrend, weak'"), ("GE", "2019-01-31", "failure — 'downtrend ... still under 200d'"),
         ("CRC", "2020-02-21", "failure — 'ugly downtrend'"), ("TLRY", "2018-09-05", "winner — 'broke out of downtrend, move above 200d, then 200d turned up'"),
         ("TLRY", "2020-11-05", "winner — same name, second sheet-1 chart"), ("NVAX", "2020-02-27", "winner — 'downtrend started basing then flipped up above all moving avg'")]
yn = lambda x: "NULL" if not np.isfinite(x) else ("yes" if x == 1 else "no")
for t, e, note in NAMED:
    g = O[(O.ticker == t) & (O.E == e)]
    if len(g) != 1:
        print(f"  {t} {e}: NOT FOUND in the population ({len(g)} rows)"); continue
    g = g.iloc[0]
    f = lambda x: "n/a" if not np.isfinite(x) else f"{x:.2f}"
    print(f"  {t:5s} {e} [{note}]\n        open {f(g.part_open)} | SMA200 {f(g.part_sma200)} (21 sessions earlier {f(g.part_sma200_lag21)}) | SMA50 {f(g.part_sma50)} | EMA10 {f(g.part_ema10)} | EMA21 {f(g.part_ema21)}"
          f" -> H1 below 200d: {yn(g.H1)}{'' if g.H1_null == '' else ' (' + g.H1_null + ')'} | H2 downtrend: {yn(g.H2)}{'' if g.H2_null == '' else ' (' + g.H2_null + ')'} | H3 above all MAs: {yn(g.H3)} | ADR20 {f(g.H4)}")
print("\n## END (outcome-free)")
