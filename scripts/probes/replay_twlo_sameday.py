"""TWLO 5/01 SAME-DAY re-entry replay (the actual existing logic).

After 13:51 stop-out at $177.28, did price re-cross ORB high $179.475
later in the same RTH session? Simulate the second-attempt entry +
preserved stop, take it to EOD.
"""
from __future__ import annotations
import asyncio, sys
from datetime import datetime as _dt
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agents.market_intelligence.collector import get_minute_bars

_ET = ZoneInfo("America/New_York")
LIMIT = 179.475
ORIG_STOP = 177.28
SHARES = 108


async def main():
    bars = await get_minute_bars("TWLO", "2026-05-01", "2026-05-01")
    rth = []
    for b in bars:
        t = _dt.fromtimestamp(b["t"] / 1000, tz=_ET)
        hhmm = t.hour * 100 + t.minute
        if 931 <= hhmm <= 1600:
            rth.append((t, float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])))
    rth.sort()

    # Leg 1: extended-window fill at 13:03 → stop-out at 13:51
    leg1_fill = _dt(2026, 5, 1, 13, 3, tzinfo=_ET)
    leg1_stop = _dt(2026, 5, 1, 13, 51, tzinfo=_ET)
    leg1_pnl = (ORIG_STOP - LIMIT) * SHARES
    print(f"Leg 1: fill 13:03 ${LIMIT:.2f}, stop 13:51 ${ORIG_STOP:.2f}, "
          f"P&L ${leg1_pnl:+.2f}")

    # Leg 2 attempt: same-day re-entry. Find next bar after 13:51 where
    # high crosses LIMIT.
    after_stop = [b for b in rth if b[0] > leg1_stop]
    cross2 = next(((t, h) for t, _o, h, _l, _c in after_stop if h >= LIMIT), None)
    if not cross2:
        print(f"\nLeg 2: no second cross of ${LIMIT:.2f} after 13:51 — single attempt only")
        return
    re_t, re_h = cross2
    print(f"\nLeg 2: 2nd cross of ${LIMIT:.2f} at "
          f"{re_t.strftime('%H:%M')} (h ${re_h:.2f}) — re-entry fires")

    # Stop preserved at $177.28 (existing logic re-uses original stop).
    after_re = [b for b in rth if b[0] > re_t]
    re_stop_hit = next(((t, l) for t, _o, _h, l, _c in after_re if l <= ORIG_STOP), None)
    eod_close = rth[-1][4]

    if re_stop_hit:
        leg2_pnl = (ORIG_STOP - LIMIT) * SHARES
        print(f"  Leg 2 stopped at {re_stop_hit[0].strftime('%H:%M')} "
              f"(l ${re_stop_hit[1]:.2f}) → P&L ${leg2_pnl:+.2f}")
    else:
        leg2_pnl = (eod_close - LIMIT) * SHARES
        print(f"  Leg 2 STILL OPEN at EOD close ${eod_close:.2f} → "
              f"unrl ${leg2_pnl:+.2f}")

    print(f"\nNet 5/01 (extended window + same-day re-entry): "
          f"${leg1_pnl + leg2_pnl:+.2f}")

    # Forward to 5/04
    bars2 = await get_minute_bars("TWLO", "2026-05-04", "2026-05-04")
    rth2 = []
    for b in bars2:
        t = _dt.fromtimestamp(b["t"] / 1000, tz=_ET)
        hhmm = t.hour * 100 + t.minute
        if 931 <= hhmm <= 1600:
            rth2.append((t, float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])))
    rth2.sort()
    if not rth2 or re_stop_hit:
        return
    # Trade still open going into 5/04 — did stop ever hit?
    d2_stop_hit = next(((t, l) for t, _o, _h, l, _c in rth2 if l <= ORIG_STOP), None)
    d2_close = rth2[-1][4]
    if d2_stop_hit:
        leg2_pnl = (ORIG_STOP - LIMIT) * SHARES
        print(f"  Leg 2 stopped 5/04 {d2_stop_hit[0].strftime('%H:%M')} "
              f"→ ${leg2_pnl:+.2f}")
    else:
        leg2_pnl = (d2_close - LIMIT) * SHARES
        print(f"  Leg 2 STILL OPEN at 5/04 close ${d2_close:.2f} → unrl ${leg2_pnl:+.2f}")
    print(f"\nNet through 5/04: ${leg1_pnl + leg2_pnl:+.2f}")


if __name__ == "__main__":
    asyncio.run(main())
