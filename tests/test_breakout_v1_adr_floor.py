"""Breakout v1's DAILY-RANGE FLOOR and its named PINNED-DEAL gate.

History: his 2026-11-02 morning "yes to both" put a 4.26% floor (his reverse-engineered pool) and a named 1% pinned-deal
gate on the list after BWMN — a $43 cash buyout pinned at $42.88-42.91 — was bought on a 7-cent stop. His spec sign-off
the same day (`docs/analysis/cb_rebuild_from_qm_trades_2026-11-02.md` rule 3, "signd off") REPLACED the 4.26% floor with
2.1%: his good EW (2.11%) and LMT (2.6%) setups sit under 4.26%. The 1% pinned gate stays (his "both" named it; it is
inside 2.1%, kept so the per-gate counts say WHY a deal target is out). These pin both gates: named in GATES in order,
evaluated every night, failing a pinned series, passing a normal mover, and the thresholds themselves."""
from datetime import date, timedelta

import numpy as np

from agents.market_intelligence import breakout_v1 as bv1
from agents.market_intelligence import consolidation_breakout as cb


def _bars(n: int, daily_range_pct: float, close: float = 40.0) -> "cb.DailyBars":
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    c = np.full(n, close, dtype=float)
    half = close * daily_range_pct / 2.0
    return cb.DailyBars(dates=days, o=c.copy(), h=c + half, l=c - half, c=c, v=np.full(n, 1_000_000.0))


def test_the_floor_is_the_rebuilt_2_1_pct_and_both_gates_are_named_in_order():
    assert bv1.ADR_MIN == 0.021
    assert bv1.PINNED_ADR_MAX == 0.01
    assert bv1.GATES.index("pinned") == bv1.GATES.index("universe") + 1 and bv1.GATES.index("adr") == bv1.GATES.index("pinned") + 1


def test_a_pinned_deal_target_fails_both_a_slow_mover_fails_the_floor_and_a_normal_mover_passes():
    n = max(bv1.MIN_BARS, 300)
    pinned = bv1.v1_gates(_bars(n, 0.0025), n - 1, rs_best=99.0)        # ARX-like: 0.25% a day
    mover = bv1.v1_gates(_bars(n, 0.03), n - 1, rs_best=99.0)           # 3% a day: under the old 4.26%, over 2.1%
    assert pinned["gates"]["adr"]["pass"] is False and "adr" in pinned["failed"]
    assert abs(pinned["gates"]["adr"]["value"]["adr20"] - 0.0025) < 1e-9
    assert pinned["gates"]["pinned"]["pass"] is False and "pinned" in pinned["failed"]
    assert mover["gates"]["adr"]["pass"] is True and "adr" not in mover["failed"]
    assert mover["gates"]["pinned"]["pass"] is True
    slow = bv1.v1_gates(_bars(n, 0.015), n - 1, rs_best=99.0)           # 1.5%: not pinned, under the floor
    assert slow["gates"]["pinned"]["pass"] is True and slow["gates"]["adr"]["pass"] is False
    ew = bv1.v1_gates(_bars(n, 0.0211), n - 1, rs_best=99.0)            # his good EW sat at 2.11%: kept
    below = bv1.v1_gates(_bars(n, 0.0209), n - 1, rs_best=99.0)         # just under 2.1% fails
    assert ew["gates"]["adr"]["pass"] is True and below["gates"]["adr"]["pass"] is False
