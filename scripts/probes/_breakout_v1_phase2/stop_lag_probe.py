"""Breakout v1 PAPER review (2026-10-30, finding 2): how far the protective stop a RESTING buy carries can sit from his
rule's stop ("the day's low AT the fill") — offline, $0, synthetic minute paths.

The resting order carries the stop of the last tick, which reads through the last COMPLETED minute: through F-1 when the
break comes after the tick at second 10 of the fill minute F, through F-2 when it comes in F's first ~10-20 s. A low
printed inside the fill minute itself is never seen, and after the fill nothing revisits the stop. This compares, on the
same random paths as tests/test_breakout_v1_entry.py's parity test (seeded), `breakout_v1_entry.evaluate` read through
F-1 and F-2 against `consolidation_breakout._entry_one('orh5')` (the reference, through F):
  * how often the stop differs, and by how much as a share of the reference risk (fill - stop);
  * how often the reference ABSTAINS too-wide while the live order would still have filled (the width judged through
    F-1 / F-2 passes).
Run:  .venv/bin/python scripts/probes/_breakout_v1_phase2/stop_lag_probe.py > scripts/probes/_breakout_v1_phase2/stop_lag_probe.out
"""
from __future__ import annotations

import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from agents.market_intelligence import consolidation_breakout as cb  # noqa: E402
from agents.market_intelligence.broker import breakout_v1_entry as be  # noqa: E402

_ET = ZoneInfo("America/New_York")
D = date(2026, 11, 2)


def _bar(m, o, h, l, c, v):
    return {"t_et": datetime(D.year, D.month, D.day, 9, 30, tzinfo=_ET) + timedelta(minutes=m),
            "open": o, "high": h, "low": l, "close": c, "volume": v}


def main(n_paths: int = 20000, seed: int = 1030) -> None:
    rng = random.Random(seed)
    fills = 0
    stats = {lag: {"stop_differs": 0, "gap_r": [], "wide_ref_filled_live": 0} for lag in (1, 2)}
    ref_wide = 0
    for _ in range(n_paths):
        px = rng.uniform(5, 50)
        mins, o, h, l, c, v = [], [], [], [], [], []
        for m in range(90):
            if rng.random() < 0.1:
                continue
            op = round(px, 2)
            px = max(1.0, px * (1 + rng.gauss(0.0005, 0.006)))
            hi = round(max(op, px) * (1 + abs(rng.gauss(0, 0.002))), 2)
            lo = round(min(op, px) * (1 - abs(rng.gauss(0, 0.002))), 2)
            mins.append(m); o.append(op); h.append(hi); l.append(lo); c.append(round(px, 2)); v.append(1000.0)
        if not mins:
            continue
        pivot = round(rng.uniform(0.97, 1.03) * h[0], 2)
        adr20 = rng.uniform(0.01, 0.08)
        ref = cb._entry_one(cb.minute_bars_from_lists(mins, o, h, l, c, v), "orh5", pivot, adr20, 0.0)
        fm = ref.get("fill_minute")
        if fm is None or fm < 7 or ref["reason"] == "no_opening_range_minutes":
            continue
        if o[mins.index(fm)] > ref["level"]:
            continue                                   # gapped through: the #500 path, excluded as in the parity test
        bars = [_bar(m, o[i], h[i], l[i], c[i], v[i]) for i, m in enumerate(mins)]
        is_wide = ref["reason"] == "too_wide"
        fills += 1
        ref_wide += is_wide
        for lag in (1, 2):
            st = be.evaluate(be.bars_by_minute(bars, D, fm - lag), list_level=pivot, adr20=adr20, vol_bar=1,
                             last_completed=fm - lag)
            live_ok = st["status"] == "ok"
            if is_wide:
                if live_ok:
                    stats[lag]["wide_ref_filled_live"] += 1
                continue
            if not live_ok:
                continue
            if abs(st["stop"] - ref["stop"]) > 1e-9:
                stats[lag]["stop_differs"] += 1
                stats[lag]["gap_r"].append((st["stop"] - ref["stop"]) / (ref["level"] - ref["stop"]))
    print(f"synthetic paths {n_paths} (seed {seed}); reference fills at the level (fill minute >= 7, no gap): {fills}; "
          f"of which the reference abstains too-wide: {ref_wide}")
    for lag in (1, 2):
        s = stats[lag]
        g = sorted(s["gap_r"])
        q = (lambda p: g[min(len(g) - 1, int(p * len(g)))] if g else 0.0)
        n_ok = fills - ref_wide
        print(f"stop read through F-{lag}: stop differs on {s['stop_differs']} of {n_ok} non-wide fills "
              f"({s['stop_differs'] / max(1, n_ok):.1%}); when it differs the live stop is TIGHTER by "
              f"median {q(0.5):.1%} / p90 {q(0.9):.1%} / max {q(1.0) if g else 0:.1%} of the reference risk; "
              f"too-wide days the live order would still fill: {s['wide_ref_filled_live']} of {ref_wide}")
    print("Synthetic paths (a gaussian minute walk), NOT real tape: the rates show the mechanism and its order of "
          "magnitude, not the live frequency.")


if __name__ == "__main__":
    main()
