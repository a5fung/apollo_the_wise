#!/usr/bin/env python3
"""#717: HEAD TO HEAD on all 757 Qullamaggie buys — the 2026-11-02 rules (list + the 5-day level + 1.2 x the 10-day
volume) against the wired 2026-11-11 initial rule set (loosened list + range rule + the range high + the 20-session
volume + a close above). Per buy, on ANY session of its window: listed the night before, and fired on the daily bar.
FIX-UP (same day): the wired set is now the loosened list with NO range gate, the level = the LOWER of the range high
and the 5-day high, and his 1.2 x 10-day volume bar; `13_head_to_head.out` is the first wiring's record (range as a gate,
the 20-session bar, a close above), `13_head_to_head_fixup.out` this one. "Fired" is a daily-bar proxy of the buy, not the live intraday entry. Strength rank: buys.tsv (dated) / the era-A
parquet (widened; an unranked night fails the rank under BOTH rule sets).

    python3 scripts/probes/_717_qm_confidence_1111/13_head_to_head.py > scripts/probes/_717_qm_confidence_1111/13_head_to_head.out"""
import csv
import sys
from collections import Counter

import pandas as pd

sys.path.insert(0, ".")
sys.path.insert(0, "scripts/probes/_717_qm_confidence_1111")
import rating as R  # noqa: E402
from agents.market_intelligence import breakout_v1 as bv, consolidation_breakout as cb  # noqa: E402

F = pd.read_parquet("/Users/alvinfung/apollo_data/qm_breakouts_1102/features_eraA.parquet", columns=["scan_date", "ticker", "rs_best", "raw_close"])
assert str(F.scan_date.max())[:10] <= "2022-03-31"
RS = {(t, str(d)[:10]): (r, rc) for t, d, r, rc in zip(F.ticker, F.scan_date, F.rs_best, F.raw_close)}
TIER = {(r["set"], r["eid"]): r["tier"] for r in csv.DictReader(open("scripts/probes/_717_qm_confidence_1111/ratings.tsv"), delimiter="\t")}
NEW = {k: getattr(bv, k) for k in ("GATES", "PRIOR_MOVE_MIN", "BASE_DEPTH_ADR_MAX", "EMA21_ADR_MIN")}
OLD = dict(GATES=("history", "universe", "pinned", "adr", "rs", "prior_move", "base_depth", "ema21", "sma50"),
           PRIOR_MOVE_MIN=0.3213536987121892, BASE_DEPTH_ADR_MAX=8.979719460898997, EMA21_ADR_MIN=-0.6335)


def gates(bars, D, rs, raw, spec):
    for k, v in spec.items():
        setattr(bv, k, v)
    try:
        return bv.v1_gates(bars, D, rs_best=rs, raw_close=raw)
    except Exception:
        return None
    finally:
        for k, v in NEW.items():
            setattr(bv, k, v)


res = []
for b in R.load():
    bars = cb.daily_bars_from_arrays(b["dates"], b["o"], b["h"], b["l"], b["c"], b["v"])
    o = dict(set=b["set"], tier=TIER[(b["set"], b["eid"])], big=b["row"].get("big_winner") == "1", ol=False, of=False, nl=False, nf=False)
    for t in b["win"]:
        D = t - 1
        if b["set"] == "dated":
            rs, raw = float(b["row"]["rs_best"]), float(b["row"]["raw_close_D"])
        else:
            rs, raw = RS.get((b["ticker"], b["dates"][D].isoformat()), (None, None))
        g0, g1 = gates(bars, D, rs, raw, OLD), gates(bars, D, rs, raw, NEW)
        if g0 and g0["ok"]:
            o["ol"] = True
            o["of"] |= bool(b["h"][t] > g0["level5"] and b["v"][t] >= 1.2 * g0["vol10"])
        if g1 and g1["ok"]:
            o["nl"] = True
            o["nf"] |= bv.breakout_triggered({"h": float(b["h"][t]), "v": float(b["v"][t])}, g1)["fired"]
            o["nr"] = o.get("nr", False) or g1["level_source"] == "range"
            rl = g1["range"]["value"]["level"]
            o["rf"] = o.get("rf", False) or bool(b["h"][t] > (rl if rl is not None else g1["level5"]) and b["v"][t] >= g1["vol_bar"])
    res.append(o)

print(f"{'group':34s}{'n':>5s} | 11-02 rules: listed  fired | 11-11 wired: listed  fired | fired by both / only 11-02 / only 11-11")
def line(name, g):
    c = Counter((x["of"], x["nf"]) for x in g)
    print(f"{name:34s}{len(g):5d} | {sum(x['ol'] for x in g):19d} {sum(x['of'] for x in g):6d} | {sum(x['nl'] for x in g):19d} {sum(x['nf'] for x in g):6d} | "
          f"{c[(True, True)]:6d} / {c[(True, False)]:5d} / {c[(False, True)]:5d}")
line("ALL 757", res)
for s in ("dated", "widened"):
    line(f"{s} — all", [x for x in res if x["set"] == s])
    for t in R.TIERS:
        line(f"{s} — {t}", [x for x in res if x["set"] == s and x["tier"] == t])
print("wired (level = the LOWER of the range high and the 5-day high): listed buys whose level is the range high on some night:", sum(x.get("nr", False) for x in res), "of", sum(x["nl"] for x in res))
print("NOT WIRED, measured only — level = the range high wherever a range exists (else the 5-day high): fired", sum(x.get("rf", False) for x in res),
      "of 757; big winners", sum(x.get("rf", False) for x in res if x["big"]), "of 26; High", sum(x.get("rf", False) for x in res if x["tier"] == "High"),
      "of 84; fired under 11-02 and not under it:", sum(x["of"] and not x.get("rf", False) for x in res))
lost = [x for x in res if x["of"] and not x["nf"]]
print("fired under 11-02 and not under the wired set:", len(lost), dict(Counter((x["set"], x["tier"]) for x in lost)))
line("the 26 big winners (dated)", [x for x in res if x["big"]])
