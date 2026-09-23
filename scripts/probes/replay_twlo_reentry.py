"""Replay TWLO 5/01 with extended window + Day-1 re-entry to current.

Original cancelled. Extended-window sim said: fills 5/01 13:03 at $179.475,
stops 5/01 13:51 at $177.28. User says re-entry would still be working —
verify by simulating Day-1 re-entry (Pradeep Bonde / Qullamaggie pattern):
after stop-out, re-arm at the day's high and re-enter on break, with stop
at the new entry-day low (or original stop, whichever tighter).
"""
from __future__ import annotations
import asyncio
import sys
from datetime import datetime as _dt, date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agents.market_intelligence.collector import get_minute_bars

_ET = ZoneInfo("America/New_York")
LIMIT = 179.475
ORIG_STOP = 177.28
SHARES = 108


async def fetch_day(d: str) -> list[tuple]:
    bars = await get_minute_bars("TWLO", d, d)
    out = []
    for b in bars:
        t = _dt.fromtimestamp(b["t"] / 1000, tz=_ET)
        out.append((t, float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])))
    return sorted(out)


async def main():
    days = ["2026-05-01", "2026-05-04"]
    by_day = {}
    for d in days:
        by_day[d] = await fetch_day(d)

    print(f"\nTWLO re-entry replay — limit ${LIMIT:.2f} stop ${ORIG_STOP:.2f}\n")

    # 5/01 trajectory
    d1 = by_day["2026-05-01"]
    rth1 = [b for b in d1 if 931 <= b[0].hour * 100 + b[0].minute <= 1600]
    if not rth1:
        print("no 5/01 RTH bars")
        return
    high1 = max(b[2] for b in rth1)
    low1 = min(b[3] for b in rth1)
    close1 = rth1[-1][4]
    print(f"5/01: open {rth1[0][1]:.2f}  high {high1:.2f}  low {low1:.2f}  close {close1:.2f}")
    print(f"  ORB high $179.475 first crossed at: ", end="")
    cross1 = next(((t, h) for t, _o, h, _l, _c in rth1 if h >= LIMIT), None)
    print(f"{cross1[0].strftime('%H:%M')} (h ${cross1[1]:.2f})" if cross1 else "never")

    # Stop-out time after fill at 13:03
    fill_t = _dt(2026, 5, 1, 13, 3, tzinfo=_ET)
    stop1_hit = next(((t, l) for t, _o, _h, l, _c in rth1
                      if t > fill_t and l <= ORIG_STOP), None)
    if stop1_hit:
        print(f"  stop ${ORIG_STOP:.2f} hit at {stop1_hit[0].strftime('%H:%M')} (l ${stop1_hit[1]:.2f})")

    # 5/04 (next session — 5/02 Sat / 5/03 Sun)
    d2 = by_day["2026-05-04"]
    rth2 = [b for b in d2 if 931 <= b[0].hour * 100 + b[0].minute <= 1600]
    if not rth2:
        print("no 5/04 RTH bars")
        return
    high2 = max(b[2] for b in rth2)
    low2 = min(b[3] for b in rth2)
    close2 = rth2[-1][4]
    print(f"\n5/04: open {rth2[0][1]:.2f}  high {high2:.2f}  low {low2:.2f}  close {close2:.2f}")

    # Day-1 re-entry: re-arm at PRIOR DAY HIGH (5/01 high). Test 3 stop
    # disciplines so we can see how the trade evolves under each.
    re_trigger = high1  # 5/01 RTH high becomes the new buy-stop
    print(f"\nRe-entry sim: trigger = 5/01 high ${re_trigger:.2f}")
    cross2 = next(((t, h) for t, _o, h, _l, _c in rth2 if h >= re_trigger), None)
    if not cross2:
        print(f"  5/04 never broke {re_trigger:.2f} — would not have re-entered")
        return
    re_entry_t, _ = cross2
    # Gap-open caveat: 5/04 opened $184.44 > re_trigger $184.13. Realistic
    # stop-buy fills at the OPEN print, not at re_trigger. Use opening bar
    # high as proxy.
    open_bar = rth2[0]
    if open_bar[1] >= re_trigger:
        re_entry_px = open_bar[1]
        re_entry_t = open_bar[0]
        print(f"  GAP OPEN above trigger — fill at 5/04 open ${re_entry_px:.2f}")
    else:
        re_entry_px = re_trigger

    # Three stop scenarios:
    stop_scenarios = {
        "tight (entry-bar low)": min(b[3] for b in rth2 if b[0] <= re_entry_t),
        "Day-1 stop preserved": ORIG_STOP,                # $177.28
        "Day-1 low": low1,                                # $171.01
    }

    print(f"\n  re-entry @ {re_entry_t.strftime('%H:%M')} ${re_entry_px:.2f} on 5/04")
    print(f"  current price 5/04 close: ${close2:.2f}")
    print()
    after = [b for b in rth2 if b[0] > re_entry_t]
    for label, stop in stop_scenarios.items():
        risk = re_entry_px - stop
        risk_pct = risk / re_entry_px * 100
        stopped = next(((t, l) for t, _o, _h, l, _c in after if l <= stop), None)
        if stopped:
            leg_pnl = (stop - re_entry_px) * SHARES
            outcome = (f"STOPPED 5/04 {stopped[0].strftime('%H:%M')} "
                       f"(l ${stopped[1]:.2f}) → P&L ${leg_pnl:+.2f}")
        else:
            unrl = (close2 - re_entry_px) * SHARES
            outcome = f"STILL OPEN at 5/04 close ${close2:.2f} → unrl ${unrl:+.2f}"
        # Original 5/01 stop-out leg counts only if extended-window path was taken
        leg1 = (ORIG_STOP - LIMIT) * SHARES
        net = leg1 + (((stop - re_entry_px) if stopped else (close2 - re_entry_px)) * SHARES)
        print(f"  [{label:<24}] stop ${stop:.2f} (risk ${risk:.2f}/{risk_pct:.1f}%)  "
              f"{outcome}  net w/ 5/01 leg ${net:+.2f}")


if __name__ == "__main__":
    asyncio.run(main())
