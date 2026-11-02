"""Drop-in sketch for `agents/market_intelligence/breakout_v1.py` — three shape gates from his MTW read (2026-11-02).

NOT applied to the live module (paper rules are his call). Definitions + why each constant: DEFINITIONS.md (same folder).
The backtest (shape_gates_effect.py) imports THESE functions, so what was tested is what this sketch holds.

To apply: paste the constants and the three functions into breakout_v1.py, put the GATES tuple below in place of the
current one, and add the three `g[...]` lines (bottom of this file) inside `v1_gates` after the tightening block (P, rng
are already computed there). Tested as ADDITIONS: surf and higher_lows stay (see DEFINITIONS.md, "Tested as ADDITIONS").
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from agents.market_intelligence import consolidation_breakout as cb

RECENT = 5                       # v1's existing 5-session unit
ADR_WINDOW = 20

RIDE_SESSIONS = 2 * RECENT       # 10: the span v1's tightening already reads (D-9 .. D)
RIDE_SMAS = (10, 20)
RIDE_LOW_TOL_ADR = 0.5           # THE G1 constant: a low may sit at most 0.5 x ADR20 x close under the ridden average
RISING_BLOCKS = 3                # THE G2 constant: 3 blocks of 5 sessions, each block's lowest low strictly higher
ATTEMPT_SESSIONS = RECENT        # THE G3 constant: the window that sets the buy level = "the attempt"

GATES = ("history", "universe", "pinned", "adr", "rs", "prior_move", "higher_lows", "rising_lows", "surf", "riding",
         "tightening", "breakdown", "no_failed_attempt")


def _adr20(rng: np.ndarray, s: int) -> Optional[float]:
    if s - ADR_WINDOW + 1 < 0:
        return None
    return float(rng[s - ADR_WINDOW + 1:s + 1].mean())


def riding_gate(bars: "cb.DailyBars", rng: np.ndarray, D: int) -> dict:
    """G1. For n in (10, 20): every session s in D-9..D has close(s) >= SMA_n(s) and
    low(s) >= SMA_n(s) - 0.5 x ADR20(s) x close(s). Pass = holds for the 10-day OR the 20-day."""
    per = {}
    for n in RIDE_SMAS:
        ok, closes_under, lows_under, worst_low = True, 0, 0, None
        for s in range(D - RIDE_SESSIONS + 1, D + 1):
            sma = cb._sma_at(bars, s, n)
            adr = _adr20(rng, s)
            if s < 0 or sma is None or adr is None or not (math.isfinite(sma) and math.isfinite(adr)):
                ok = False
                closes_under = lows_under = None
                break
            c, lo = float(bars.c[s]), float(bars.l[s])
            depth = (sma - lo) / (adr * c) if adr * c > 0 else math.inf     # in ADRs under the line (negative = above)
            worst_low = depth if worst_low is None else max(worst_low, depth)
            if c < sma:
                closes_under += 1
                ok = False
            if depth > RIDE_LOW_TOL_ADR:
                lows_under += 1
                ok = False
        per[f"sma{n}"] = {"pass": ok, "closes_under": closes_under, "lows_too_deep": lows_under,
                          "worst_low_adr_under": None if worst_low is None else round(worst_low, 3)}
    return {"pass": bool(any(v["pass"] for v in per.values())), "value": per}


def rising_lows_gate(bars: "cb.DailyBars", D: int) -> dict:
    """G2. Blocks D-14..D-10, D-9..D-5, D-4..D: each block's lowest low strictly above the block before's."""
    lo0 = D - RISING_BLOCKS * RECENT + 1
    if lo0 < 0:
        return {"pass": False, "value": {"block_lows": None}}
    lows = [float(bars.l[lo0 + k * RECENT: lo0 + (k + 1) * RECENT].min()) for k in range(RISING_BLOCKS)]
    ok = all(lows[k + 1] > lows[k] for k in range(RISING_BLOCKS - 1))
    return {"pass": bool(ok), "value": {"block_lows": lows}}


def no_failed_attempt_gate(bars: "cb.DailyBars", D: int, P: int) -> dict:
    """G3. CEIL = the highest high of P+1 .. D-5. Failed attempt = max high(D-4..D) > CEIL and close(D) < CEIL.
    Pass = no failed attempt. (v1's base is >= 10 sessions, so P+1 .. D-5 always holds >= 5 sessions.)"""
    a, b = P + 1, D - ATTEMPT_SESSIONS + 1          # [a, b) = P+1 .. D-5
    if b <= a:
        return {"pass": True, "value": {"ceiling": None, "note": "no base before the attempt window"}}
    ceil = float(bars.h[a:b].max())
    recent_high = float(bars.h[b:D + 1].max())
    close_d = float(bars.c[D])
    attempted = recent_high > ceil
    failed = attempted and close_d < ceil
    return {"pass": bool(not failed), "value": {"ceiling": ceil, "recent_high": recent_high, "close": close_d,
                                                "attempted": attempted, "failed_attempt": failed}}


# ── inside v1_gates, after the tightening block (P and rng already exist there) ──
#     g["riding"] = riding_gate(bars, rng, D)
#     g["rising_lows"] = rising_lows_gate(bars, D)
#     g["no_failed_attempt"] = no_failed_attempt_gate(bars, D, P)
# and the module's GATES tuple becomes the one above (the `failed` list and the `ok` verdict follow it).
