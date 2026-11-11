#!/usr/bin/env python3
"""#717: his ruling 2026-11-11 "drop it" — volume is no longer a buy condition. Head to head on all 757 Qullamaggie
buys (any window session, daily bar, listed the night before): the wired set WITH the volume bar (1.2x the last 10
sessions; commit 92da87f7) against the price break alone. Names every buy gained.

    python3 scripts/probes/_717_qm_confidence_1111/16_no_volume_gate.py > scripts/probes/_717_qm_confidence_1111/16_no_volume_gate.out"""
import sys

import pandas as pd

sys.path.insert(0, ".")
sys.path.insert(0, "scripts/probes/_717_qm_confidence_1111")
import rating as R  # noqa: E402
from agents.market_intelligence import breakout_v1 as bv, consolidation_breakout as cb  # noqa: E402

F = pd.read_parquet("/Users/alvinfung/apollo_data/qm_breakouts_1102/features_eraA.parquet", columns=["scan_date", "ticker", "rs_best", "raw_close"])
assert str(F.scan_date.max())[:10] <= "2022-03-31"
RS = {(t, str(d)[:10]): (r, rc) for t, d, r, rc in zip(F.ticker, F.scan_date, F.rs_best, F.raw_close)}
res = []
for b in R.load():
    bars = cb.daily_bars_from_arrays(b["dates"], b["o"], b["h"], b["l"], b["c"], b["v"])
    o = dict(b=b, listed=False, with_vol=False, price=False, day=None, ratio=None)
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
        o["listed"] = True
        tr = bv.breakout_triggered({"h": float(b["h"][t]), "v": float(b["v"][t])}, g)
        o["with_vol"] |= tr["level_pass"] and tr["volume_pass"]
        if tr["fired"] and not o["price"]:
            o.update(price=True, day=b["dates"][t].isoformat(), ratio=float(b["v"][t]) / g["vol10"])
    res.append(o)
big = lambda x: x["b"]["row"].get("big_winner") == "1"  # noqa: E731
print("listed / fired / big winners fired (n = 757 / 757 / 26)")
print(f"  with the volume bar (92da87f7): {sum(x['listed'] for x in res)} / {sum(x['with_vol'] for x in res)} / {sum(x['with_vol'] for x in res if big(x))}")
print(f"  the price break alone:          {sum(x['listed'] for x in res)} / {sum(x['price'] for x in res)} / {sum(x['price'] for x in res if big(x))}")
print(f"  lost: {sum(x['with_vol'] and not x['price'] for x in res)}")
print(f"  big winners listed {sum(x['listed'] for x in res if big(x))} of 26; not fired: "
      + (", ".join(f"{x['b']['ticker']} {x['b']['hi']}" for x in res if big(x) and not x["price"]) or "none"))
gained = [x for x in res if x["price"] and not x["with_vol"]]
print(f"\ngained {len(gained)} (day volume / the 10-day average in brackets); big winners first:")
for x in sorted(gained, key=lambda x: (not big(x), x["b"]["set"], x["day"])):
    print(f"  {'BIG ' if big(x) else '    '}{x['b']['set']:8s} {x['b']['ticker']:6s} {x['day']} ({x['ratio']:.2f}x)")
