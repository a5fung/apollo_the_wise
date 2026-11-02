"""His ruling 2026-11-02 ("yes to both"): breakout v1's list carries a DAILY-RANGE FLOOR, ADR20 >= 4.26% (his own
reverse-engineered stock pool). BWMN that morning — a $43 cash buyout pinned at $42.88-42.91 — was bought on a 7-cent
stop; a pinned deal target is not a breakout. These pin the gate: named in GATES, evaluated on every night, failing a
pinned series and passing a normal mover, and the threshold itself."""
from datetime import date, timedelta

import numpy as np

from agents.market_intelligence import breakout_v1 as bv1
from agents.market_intelligence import consolidation_breakout as cb


def _bars(n: int, daily_range_pct: float, close: float = 40.0) -> "cb.DailyBars":
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    c = np.full(n, close, dtype=float)
    half = close * daily_range_pct / 2.0
    return cb.DailyBars(dates=days, o=c.copy(), h=c + half, l=c - half, c=c, v=np.full(n, 1_000_000.0))


def test_the_floor_is_his_pool_value_and_a_named_gate():
    assert bv1.ADR_MIN == 0.0426
    assert "adr" in bv1.GATES and bv1.GATES.index("adr") == bv1.GATES.index("universe") + 1


def test_a_pinned_deal_target_fails_the_floor_and_a_normal_mover_passes():
    n = max(bv1.MIN_BARS, 300)
    pinned = bv1.v1_gates(_bars(n, 0.0025), n - 1, rs_best=99.0)        # ARX-like: 0.25% a day
    mover = bv1.v1_gates(_bars(n, 0.06), n - 1, rs_best=99.0)           # 6% a day
    assert pinned["gates"]["adr"]["pass"] is False and "adr" in pinned["failed"]
    assert abs(pinned["gates"]["adr"]["value"]["adr20"] - 0.0025) < 1e-9
    assert mover["gates"]["adr"]["pass"] is True and "adr" not in mover["failed"]
    above = bv1.v1_gates(_bars(n, 0.0427), n - 1, rs_best=99.0)         # just over the line passes
    below = bv1.v1_gates(_bars(n, 0.0425), n - 1, rs_best=99.0)         # just under fails
    assert above["gates"]["adr"]["pass"] is True and below["gates"]["adr"]["pass"] is False
