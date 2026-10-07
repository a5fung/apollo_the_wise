"""#624 backfill — W5 (look-ahead): every pre-open term must end at D-1. A synthetic daily series whose D row (and
every later row) carries absurd values must leave history, ADV$, ATR (stamp and ORB-validation), extension and the
walker's prior closes unchanged."""
from datetime import date, timedelta

import lib624 as L
import walk624 as W
from agents.market_intelligence.alert_rank_shadow import compute_atr14_prior


def series(d0: date, poison: bool) -> dict:
    rows, x, i = {}, d0 - timedelta(days=200), 0
    while x <= d0 + timedelta(days=60):
        if x.weekday() < 5:
            i += 1
            v = {"o": 10 + i * 0.01, "h": 10.5 + i * 0.01, "l": 9.5 + i * 0.01, "c": 10 + i * 0.01, "v": 100000 + i}
            if poison and x >= d0:
                v = {"o": 1e6, "h": 1e7, "l": 1e-3, "c": 5e6, "v": 9e12}
            rows[x] = v
        x += timedelta(days=1)
    return {"rows": rows, "dates": sorted(rows)}


def terms(dl, d):
    pc = dl["rows"][[x for x in dl["dates"] if x < d][-1]]["c"]
    _, hlc, closes = W._prior(dl, d)
    return (L.vol_history(dl, d), L.adv_dollar(dl, d), L.atr_pct_stamp(dl, d), L.extension_pct(dl, d, pc),
            compute_atr14_prior(hlc), closes)


ok = True
for d in (date(2024, 3, 6), date(2025, 7, 15), date(2026, 6, 1)):
    a, b = terms(series(d, False), d), terms(series(d, True), d)
    same = a == b
    ok &= same
    print(d, "pre-open terms identical with D and later rows poisoned:", same)
print("W5 PASS" if ok else "W5 FAIL")
raise SystemExit(0 if ok else 1)
