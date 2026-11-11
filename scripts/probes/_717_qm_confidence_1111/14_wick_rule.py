#!/usr/bin/env python3
"""#717 wick rule: head to head on all 757 Qullamaggie buys — the wired set of 49bb0b27 (wick rule OFF) against the
same set with the wick rule (docs/analysis/cb_initial_rules_2026-11-11.md §WICK RULE), any window session, daily bar.
Names every buy that changes; the sweep of X.

    python3 scripts/probes/_717_qm_confidence_1111/14_wick_rule.py > scripts/probes/_717_qm_confidence_1111/14_wick_rule.out"""
import sys

import pandas as pd

sys.path.insert(0, ".")
sys.path.insert(0, "scripts/probes/_717_qm_confidence_1111")
import rating as R  # noqa: E402
from agents.market_intelligence import breakout_v1 as bv, consolidation_breakout as cb  # noqa: E402

F = pd.read_parquet("/Users/alvinfung/apollo_data/qm_breakouts_1102/features_eraA.parquet", columns=["scan_date", "ticker", "rs_best", "raw_close"])
assert str(F.scan_date.max())[:10] <= "2022-03-31"
RS = {(t, str(d)[:10]): (r, rc) for t, d, r, rc in zip(F.ticker, F.scan_date, F.rs_best, F.raw_close)}
B = R.load()
BARS = [cb.daily_bars_from_arrays(b["dates"], b["o"], b["h"], b["l"], b["c"], b["v"]) for b in B]


def run(x):
    bv.LEVEL_WICK_MIN = x
    out = []
    for b, bars in zip(B, BARS):
        o = dict(listed=False, fired=False, detail=None)
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
            if g["ok"]:
                o["listed"] = True
                f = bv.breakout_triggered({"h": float(b["h"][t]), "v": float(b["v"][t])}, g)["fired"]
                if f and not o["fired"]:
                    o["detail"] = (b["dates"][t].isoformat(), g["level"], g["level5"], g["level_source"], g["wick_date"])
                o["fired"] |= f
        out.append(o)
    return out


def summ(r):
    return (sum(x["listed"] for x in r), sum(x["fired"] for x in r), sum(x["fired"] for x, b in zip(r, B) if b["row"].get("big_winner") == "1"))


off = run(None)
print("listed / fired / big winners fired (n = 757 / 757 / 26)")
print(f"  wick rule OFF (49bb0b27): {summ(off)}")
for x in (0.4, 0.5, 0.6, 0.7):
    r = run(x)
    lost = [(b["ticker"], b["hi"]) for b, a, n in zip(B, off, r) if a["fired"] and not n["fired"]]
    gained = [(b, n) for b, a, n in zip(B, off, r) if n["fired"] and not a["fired"]]
    print(f"  X = {x}: {summ(r)}   gained {len(gained)}, lost {len(lost)} {lost}")
    if x == 0.5:
        keep = (r, gained)
r, gained = keep
print("\nX = 0.5 — every buy that changes (not fired -> fired):")
for b, n in gained:
    d, lvl, l5, src, wd = n["detail"]
    print(f"  {b['set']:8s} {b['ticker']:6s} window {b['lo']}..{b['hi']} fires {d}: level {lvl:.4g} (5-day high {l5:.4g}, wick day {wd})  big winner {b['row'].get('big_winner', '')}")
apt = next((b, n) for b, n in zip(B, r) if b["ticker"] == "APT" and b["hi"] == "2020-02-21")
print("\nAPT 2020-02-21:", "FIRES" if apt[1]["fired"] else "does NOT fire", apt[1]["detail"])
bv.LEVEL_WICK_MIN = 0.5
