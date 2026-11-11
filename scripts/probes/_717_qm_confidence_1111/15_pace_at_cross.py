#!/usr/bin/env python3
"""#717: the volume PACE at the moment Qullamaggie's buys cross the wired level — not the full-day volume, which nobody
knows at the entry. No gate is changed.

Population: every Qullamaggie buy whose DAILY bar takes out the wired level (the lower of the range high and the 5-day
high, with the wick rule) on a session of its window while the name is listed the night before — split into FIRED
(the daily volume also meets 1.2 x the 10-day average: the 272) and VOLUME-MISSED (it does not).
Minute bars: per-DATE files, only dates <= 2024 and only stores that hold no 2025-26 file:
  cb702_pre_v2/minutes, cb702_pre/minutes (2017-03..2022-01), cb702/minutes_{intra_1025,bv1_1101,tgrid_1101,rev_1024,
  asis_1026,ep_1023,ep_1024}. NOT opened: cb702/minutes, minutes_pre_com_1018, minutes_com_delta_1018 (they run to 2026).
The pace is the live entry's own: at the cross minute k (the first minute >= 5 whose high reaches
max(5-minute opening-range high, list level) — `breakout_v1_entry.evaluate`'s level), volume of minutes <= k-1 against
the list's 10-day average daily volume x `CUM_SHARE[k-1]` (`f1_permits`, `first_break`). pace = that ratio; the live
entry needs pace >= 1.2 (vol_bar = 1.2 x the 10-day average). Minute prices are put on the daily fixture's scale by the
ratio of the day's highs (split adjustment), volumes by its inverse.

    python3 scripts/probes/_717_qm_confidence_1111/15_pace_at_cross.py > scripts/probes/_717_qm_confidence_1111/15_pace_at_cross.out"""
import gzip
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
sys.path.insert(0, "scripts/probes/_717_qm_confidence_1111")
import rating as R  # noqa: E402
from agents.market_intelligence import breakout_v1 as bv, consolidation_breakout as cb  # noqa: E402
from agents.market_intelligence.broker import breakout_v1_entry as be  # noqa: E402
from agents.market_intelligence.broker.breakout_v1_volume_curve import CUM_SHARE  # noqa: E402

DATA = "/Users/alvinfung/apollo_data/"
STORES = ["cb702_pre_v2/minutes", "cb702_pre/minutes", "cb702/minutes_intra_1025", "cb702/minutes_bv1_1101", "cb702/minutes_tgrid_1101",
          "cb702/minutes_rev_1024", "cb702/minutes_asis_1026", "cb702/minutes_ep_1023", "cb702/minutes_ep_1024"]
F = pd.read_parquet(DATA + "qm_breakouts_1102/features_eraA.parquet", columns=["scan_date", "ticker", "rs_best", "raw_close"])
assert str(F.scan_date.max())[:10] <= "2022-03-31"
RS = {(t, str(d)[:10]): (r, rc) for t, d, r, rc in zip(F.ticker, F.scan_date, F.rs_best, F.raw_close)}
del F

# ── the population ────────────────────────────────────────────────────────────────────────────────────────────
pop = []
for b in R.load():
    bars = cb.daily_bars_from_arrays(b["dates"], b["o"], b["h"], b["l"], b["c"], b["v"])
    best = None
    for t in b["win"]:
        D = t - 1
        if b["set"] == "dated":
            rs, raw = float(b["row"]["rs_best"]), float(b["row"]["raw_close_D"])
        else:
            rs, raw = RS.get((b["ticker"], b["dates"][D].isoformat()), (None, None))
        try:
            g = bv.v1_gates(bars, D, rs_best=rs, raw_close=raw)
        except Exception:
            continue
        if not g["ok"]:
            continue
        tr = bv.breakout_triggered({"h": float(b["h"][t]), "v": float(b["v"][t])}, g)
        if tr["level_pass"] and (best is None or (tr["fired"] and not best["fired"])):
            best = dict(b=b, t=t, level=g["level"], vol10=g["vol10"], fired=tr["fired"], day_ratio=float(b["v"][t]) / g["vol10"])
            if tr["fired"]:
                break
    if best:
        pop.append(best)
fired = [x for x in pop if x["fired"]]
missed = [x for x in pop if not x["fired"]]
big = lambda x: x["b"]["row"].get("big_winner") == "1"  # noqa: E731
print(f"POPULATION: daily bar takes out the wired level while listed: {len(pop)} buys — FIRED {len(fired)} ({sum(map(big, fired))} big winners), "
      f"VOLUME-MISSED {len(missed)} ({sum(map(big, missed))} big winners)")

# ── minute bars: one pass per needed date over the allowed stores ─────────────────────────────────────────────
need = defaultdict(set)
for x in pop:
    d = x["b"]["dates"][x["t"]].isoformat()
    assert d < "2025-01-01"
    need[d] |= {x["b"]["ticker"], x["b"]["sym"]}
mins = {}
for d, tks in need.items():
    for st in STORES:
        p = f"{DATA}{st}/{d}.psv.gz"
        if not os.path.exists(p):
            continue
        with gzip.open(p, "rt") as f:
            for line in f:
                tk, m, o, h, l, c, v = line.rstrip("\n").split("|")
                if tk in tks:
                    mins.setdefault((tk, d), {}).setdefault(st, {})[int(m)] = (float(h), float(l), float(v))


def minute_series(x):
    b, d = x["b"], x["b"]["dates"][x["t"]].isoformat()
    for tk in (b["ticker"], b["sym"]):
        got = mins.get((tk, d))
        if got:
            st = max(got, key=lambda s: len(got[s]))           # the store with the most minutes that day
            return st, got[st]
    return None, None


def pace(ms, vol10, k_last):
    """The live number: volume of minutes <= k_last against vol10 x CUM_SHARE[k_last] (f1_permits with vol_bar = vol10)."""
    cum = sum(v for m, (_, _, v) in ms.items() if m <= k_last)
    return cum / (vol10 * CUM_SHARE[max(0, min(k_last, len(CUM_SHARE) - 1))])


rows = []
for x in pop:
    st, ms = minute_series(x)
    if not ms:
        rows.append(dict(x, covered=False))
        continue
    b, t = x["b"], x["t"]
    hi = max(h for h, _, _ in ms.values())
    r = float(b["h"][t]) / hi                                   # minute price scale -> the daily fixture's (splits)
    ms = {m: (h * r, l * r, v / r) for m, (h, l, v) in ms.items() if 0 <= m < 390}
    assert be.f1_permits(1.0, 1.0, 0)[1] == CUM_SHARE[0]       # the live function reads the same curve
    orh5 = max((h for m, (h, _, _) in ms.items() if m < be.OR_MINUTES), default=None)
    out = dict(x, covered=True, store=st, scale=r, p5=pace(ms, x["vol10"], 4), p15=pace(ms, x["vol10"], 14), cross=None, pace=None,
               reg_share=sum(v for _, _, v in ms.values()) / float(b["v"][t]))
    if orh5 is not None:
        lvl = max(orh5, x["level"])
        k = next((m for m in sorted(ms) if m >= be.FIRST_MINUTE and ms[m][0] >= lvl), None)
        if k is not None:
            out.update(cross=k, pace=pace(ms, x["vol10"], k - 1), live_level=lvl, orh_above=orh5 > x["level"])
    rows.append(out)


def dist(name, g):
    cov = [x for x in g if x["covered"]]
    cr = [x for x in cov if x["cross"] is not None]
    print(f"\n=== {name}: n = {len(g)}; minute bars on the buy day {len(cov)} ({sum(map(big, cov))} of {sum(map(big, g))} big winners); "
          f"crossed the live level at or after 09:35: {len(cr)} ===")
    if not cr:
        return
    p = np.array([x["pace"] for x in cr])
    print(f"  pace at the cross (x the stock's normal volume by that minute; the live entry needs 1.2): median {np.median(p):.2f}, "
          f"10th pct {np.percentile(p, 10):.2f}, 5th pct {np.percentile(p, 5):.2f}, min {p.min():.2f}")
    print("  share of his buys at or above: " + ", ".join(f"{th}: {np.mean(p >= th):.0%} ({int((p >= th).sum())})" for th in (0.5, 0.8, 1.0, 1.2, 1.5, 2.0)))
    k = np.array([x["cross"] for x in cr])
    print(f"  cross minute after the open: median {int(np.median(k))}, by 09:45 {np.mean(k <= 15):.0%}, by 10:30 {np.mean(k <= 60):.0%}; "
          f"the opening-range high was the level (above the list level) on {sum(x['orh_above'] for x in cr)}")
    for lab, key in (("pace 5 minutes after the open", "p5"), ("pace 15 minutes after the open", "p15")):
        q = np.array([x[key] for x in cov])
        print(f"  {lab} (n = {len(q)}): median {np.median(q):.2f}; at or above 1.2: {np.mean(q >= 1.2):.0%}")
    bw = [x for x in cr if big(x)]
    print(f"  big winners (n = {len(bw)}): pace at the cross >= 1.2 on {sum(x['pace'] >= 1.2 for x in bw)}; lowest "
          + ", ".join(f"{x['b']['ticker']} {x['b']['dates'][x['t']]} {x['pace']:.2f}" for x in sorted(bw, key=lambda x: x['pace'])[:5]))
    low = sorted(cr, key=lambda x: x["pace"])[:max(1, int(len(cr) * 0.05) + 3)]
    print("  the lowest: " + ", ".join(f"{x['b']['ticker']} {x['b']['dates'][x['t']]} {x['pace']:.2f}@{x['cross']}" for x in low))
    for keep in (0.95, 0.90):
        print(f"  the bar that keeps {keep:.0%} of these: pace >= {np.quantile(p, 1 - keep):.2f}")


F_ = [x for x in rows if x["fired"]]
M_ = [x for x in rows if not x["fired"]]
print(f"stores read: {STORES}")
for lab, f in (("buy day to 2022-01-03", lambda x: x["b"]["dates"][x["t"]].isoformat() <= "2022-01-03"), ("buy day after 2022-01-03", lambda x: x["b"]["dates"][x["t"]].isoformat() > "2022-01-03")):
    g = [x for x in F_ if f(x)]
    print(f"  FIRED, {lab}: minute bars on {sum(x['covered'] for x in g)} of {len(g)}")
sc = np.array([x["scale"] for x in rows if x["covered"]])
rs_ = np.array([x["reg_share"] for x in rows if x["covered"]])
print(f"checks: minute->daily price scale is 1.00 +/- 1% on {np.mean(np.abs(sc - 1) < 0.01):.0%} of covered days (others are split-adjusted differently and rescaled); "
      f"regular-hours minute volume / the daily volume: median {np.median(rs_):.2f} (the curve's own end is {CUM_SHARE[-1]:.2f})")
dist("FIRED (the daily volume met his bar)", F_)
dist("VOLUME-MISSED (level taken out, the DAY's volume under 1.2 x the 10-day average)", M_)
dist("ALL that took out the level", rows)
print("\n=== the four volume-missed big winners ===")
for tk, d in (("DOYU", "2020-08-24"), ("MDB", "2020-09-21"), ("NVDA", "2020-09-25"), ("JMIA", "2021-01-12")):
    x = next((x for x in rows if x["b"]["ticker"] == tk and x["b"]["dates"][x["t"]].isoformat() == d), None)
    if x is None:
        print(f"  {tk} {d}: not in the population (the daily bar did not take out the level while listed)")
    elif not x["covered"]:
        print(f"  {tk} {d}: NO minute bars in the allowed stores (day volume {x['day_ratio']:.2f}x the 10-day average)")
    elif x["cross"] is None:
        print(f"  {tk} {d}: minute bars ({x['store']}), never reached the live level at or after 09:35; pace at 5 / 15 min {x['p5']:.2f} / {x['p15']:.2f}; day {x['day_ratio']:.2f}x")
    else:
        print(f"  {tk} {d}: crossed at minute {x['cross']} with pace {x['pace']:.2f} (needs 1.2: {'PASS' if x['pace'] >= 1.2 else 'fail'}); "
              f"pace at 5 / 15 min {x['p5']:.2f} / {x['p15']:.2f}; the day ended {x['day_ratio']:.2f}x the 10-day average")
print("\nevery volume-missed big winner in the population: " + ", ".join(f"{x['b']['ticker']} {x['b']['dates'][x['t']]}" for x in M_ if big(x)))
