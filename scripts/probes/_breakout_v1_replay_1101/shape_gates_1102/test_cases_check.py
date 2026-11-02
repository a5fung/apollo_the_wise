"""Runs every case in test_cases.md against gates_patch.py and asserts the expected verdict (exit 1 on any miss).
Synthetic bars are built here; MTW uses scripts/probes/_mtw_1102/mtw_bars.csv sliced to <= 2026-10-30."""
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(HERE))
from agents.market_intelligence import breakout_v1 as bv            # noqa: E402
from agents.market_intelligence import consolidation_breakout as cb  # noqa: E402
import gates_patch as G                                               # noqa: E402


def mk(closes, half_range=0.02, lows=None, highs=None):
    c = np.asarray(closes, float)
    h = c * (1 + half_range) if highs is None else np.asarray(highs, float)
    l = c * (1 - half_range) if lows is None else np.asarray(lows, float)
    d0 = date(2020, 1, 1)
    return cb.daily_bars_from_arrays([d0 + timedelta(days=i) for i in range(len(c))], c, h, l, c, np.full(len(c), 1e6))


def rng_of(b):
    return (b.h - b.l) / b.c


def run(b, D, P):
    return {"riding": G.riding_gate(b, rng_of(b), D)["pass"], "rising_lows": G.rising_lows_gate(b, D)["pass"],
            "no_failed_attempt": G.no_failed_attempt_gate(b, D, P)["pass"]}


cases, bad = [], 0
# 1. MTW 2026-10-30 — his "not a breakout": all three fail
df = pd.read_csv(REPO / "scripts/probes/_mtw_1102/mtw_bars.csv")
df = df[df.trade_date <= "2026-10-30"].reset_index(drop=True)
mtw = cb.daily_bars_from_arrays([date.fromisoformat(x) for x in df.trade_date], df.open_price, df.high_price,
                                df.low_price, df.close, df.volume)
D = len(mtw) - 1
P = bv.v1_gates(mtw, D, rs_best=99.0)["pole_idx"]
cases.append(("1 MTW 10-30", run(mtw, D, P), {"riding": False, "rising_lows": False, "no_failed_attempt": False}))

# 2. clean rider: +0.5% a day, 4% daily range -> the 10-day sits under every low; lows rise; close(D) above the ceiling
c = 10 * 1.005 ** np.arange(60)
b = mk(c); D = 59
cases.append(("2 clean rider", run(b, D, 30), {"riding": True, "rising_lows": True, "no_failed_attempt": True}))

# 3. chopper: flat at 10, closes alternating 10.3 / 9.7 -> closes under both averages
c = np.array([10.3 if i % 2 else 9.7 for i in range(60)])
b = mk(c); D = 59
cases.append(("3 chopper", run(b, D, 30), {"riding": False, "rising_lows": False, "no_failed_attempt": True}))

# 4. rising-lows base: three 5-session blocks with lows 9.0 / 9.3 / 9.6 (flat closes 10, highs 10.4)
c = np.full(60, 10.0)
lows = np.full(60, 9.0); lows[45:50] = 9.0; lows[50:55] = 9.3; lows[55:60] = 9.6
b = mk(c, lows=lows, highs=np.full(60, 10.4)); D = 59
cases.append(("4 rising-lows base", run(b, D, 30)["rising_lows"], True))
# 4b. the MTW shape: middle block undercuts (9.3 / 9.0 / 9.6) -> fails
lows2 = lows.copy(); lows2[45:50] = 9.3; lows2[50:55] = 9.0
b = mk(c, lows=lows2, highs=np.full(60, 10.4))
cases.append(("4b middle block undercut", run(b, D, 30)["rising_lows"], False))

# 5. failed-attempt retest: pole top at 30, base highs <= 11.0 (P+1 .. D-5), D-2 trades 11.3, close(D) 10.8 -> fails
c = np.full(60, 10.5); highs = np.full(60, 10.9); highs[40] = 11.0; highs[30] = 12.0
highs[57] = 11.3; c[59] = 10.8
b = mk(c, lows=c * 0.98, highs=np.maximum(highs, c)); D = 59
cases.append(("5 failed-attempt retest", run(b, D, 30)["no_failed_attempt"], False))
# 5b. the same push that HOLDS: close(D) 11.2 above the 11.0 ceiling -> passes
c2 = c.copy(); c2[59] = 11.2
b = mk(c2, lows=c2 * 0.98, highs=np.maximum(highs, c2 * 1.001))
cases.append(("5b attempt held above the ceiling", run(b, D, 30)["no_failed_attempt"], True))
# 5c. no attempt yet: the last 5 stay under the ceiling -> passes (a first breakout)
highs3 = highs.copy(); highs3[57] = 10.9; c3 = c.copy(); c3[59] = 10.6
b = mk(c3, lows=c3 * 0.98, highs=np.maximum(highs3, c3))
cases.append(("5c no attempt yet", run(b, D, 30)["no_failed_attempt"], True))

for name, got, want in cases:
    ok = got == want
    bad += not ok
    print(f"{'ok  ' if ok else 'MISS'} {name}: got {got} want {want}")
print(f"{len(cases) - bad}/{len(cases)} cases as expected")
sys.exit(1 if bad else 0)
