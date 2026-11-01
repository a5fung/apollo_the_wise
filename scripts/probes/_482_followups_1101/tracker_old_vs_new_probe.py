"""OLD-vs-NEW proof harness for the #482 follow-up (3) cleanups (shadow_orb_tracker / hour_bar_walk /
book_geometry_arms). Drives the same synthetic scenarios the two test suites use and prints every write
(INSERT / UPDATE payload), every count and every audit event as one JSON document; `fetches` (the exit
pass's daily-bar fetch count per scenario) is reported under its own key because the fetch-skip cleanup
is MEANT to lower it — payload equality is the proof, the fetch delta is the stated intent.

    REPO=<tree> python3 tracker_old_vs_new_probe.py > <file>.json
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock

REPO = os.environ["REPO"]
sys.path.insert(0, REPO)
os.chdir(REPO)

import pytest  # noqa: E402

from tests import test_482_shadow_hour_lane as H  # noqa: E402
from tests import test_book_geometry_arms_482 as B  # noqa: E402
from tests import test_live_fill_counterfactuals as base  # noqa: E402
from agents.market_intelligence import book_geometry_arms as bga  # noqa: E402
from agents.market_intelligence.broker import shadow_orb_tracker as sot  # noqa: E402

DAY, HALF_DAY, ET = H.DAY, H.HALF_DAY, H.ET
OUT: dict = {"hour": {}, "five": {}, "exit": {}, "replay": {}, "book": {}, "fetches": {}}


def _j(v):
    return H._jsonable(v) if not isinstance(v, (date, datetime, time)) else v.isoformat()


async def hour(name, cands, bars, *, today=DAY, daily_high=None):
    mp = pytest.MonkeyPatch()
    try:
        counts, cap = await H._drive_hour(mp, cands, bars, today=today, daily_high=daily_high)
        OUT["hour"][name] = {"counts": counts, **cap.payloads(), "audit": cap.audit}
    finally:
        mp.undo()


async def hour_hist(name, alert, today, history_rows, *, minutes=None):
    """A late-fill scenario: `history_rows` = [(date, low, close)] served by get_index_history."""
    mp = pytest.MonkeyPatch()
    try:
        calls = []

        async def _daily(ticker, a, b):
            calls.append((a, b))
            return [{"o": c, "h": c, "l": l, "c": c, "t": H._ms(d)} for d, (l, c) in history_rows
                    if a <= d.isoformat() <= b]
        cap = H._Captured()
        H._patch_common(mp, cap, minute_bars=(minutes or (lambda t, d, s, e: H._hour_day(alert, cross=(10, 45)))),
                        daily_bars=_daily)
        mp.setattr(sot, "_fetch_hour_lane_candidates", AsyncMock(return_value=[H._five_row("AAA", alert)]))
        counts = await sot.run_shadow_hour_pass(today)
        OUT["hour"][name] = {"counts": counts, **cap.payloads(), "audit": cap.audit, "history_calls": calls}
    finally:
        mp.undo()


async def five():
    mp = pytest.MonkeyPatch()
    try:
        OUT["five"]["lane"] = await H._drive_5m_lane(mp)
    finally:
        mp.undo()


async def exit_pass(name, rows, today, daily):
    mp = pytest.MonkeyPatch()
    try:
        fetches = []

        async def _daily(t, a, b):
            fetches.append((t, a, b))
            r = daily(t, a, b)
            if isinstance(r, Exception):
                raise r
            return r
        cap = H._Captured()
        H._patch_common(mp, cap, minute_bars=lambda *a: [], daily_bars=_daily)

        async def _open(bar_size_minutes=None):
            return list(rows)
        mp.setattr(sot, "get_open_shadow_trades", _open)
        counts = await sot.update_shadow_positions(today)
        OUT["exit"][name] = {"counts": counts, **cap.payloads(), "audit": cap.audit}
        OUT["fetches"][name] = fetches
    finally:
        mp.undo()


async def replay(name, row, as_of, bars):
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(sot, "get_index_history", AsyncMock(return_value=bars))
        res = await sot.replay_stale_open_row(row, as_of)
        res = {k: ("<datetime>" if isinstance(v, datetime) else v) for k, v in res.items()}
        OUT["replay"][name] = H._jsonable(res)
    finally:
        mp.undo()


async def book(name, *, today=None, now=None, **wire):
    mp = pytest.MonkeyPatch()
    try:
        _, inserts, audits, _ = B._wire_book(mp, **wire)
        out = await B._run(*(a for a in (today, now) if a is not None)) if today else await B._run()
        OUT["book"][name] = {"out": out, "rows": base_jsonable(inserts), "audit": audits}
    finally:
        mp.undo()


def base_jsonable(v):
    from tests._lfc_equality_scenarios import to_jsonable
    return to_jsonable(v)


async def main():
    # ── the hour lane (every scenario the suite drives) ──
    await hour("enters_1045", [H._five_row("AAA")], {"AAA": H._hour_day(DAY, cross=(10, 45))})
    await hour("inside_first_hour", [H._five_row("AAA")], {"AAA": H._hour_day(DAY, cross=(10, 15), cross_high=11.5)})
    await hour("touch_1030", [H._five_row("AAA")], {"AAA": H._hour_day(DAY, cross=(10, 30))})
    await hour("half_day_late", [H._five_row("AAA", HALF_DAY)], {"AAA": H._hour_day(HALF_DAY, cross=(13, 5), end=time(16, 0))}, today=HALF_DAY)
    await hour("half_day_early", [H._five_row("AAA", HALF_DAY)], {"AAA": H._hour_day(HALF_DAY, cross=(12, 55), end=time(16, 0))}, today=HALF_DAY)
    gappy = H._hour_day(DAY, skip={(11, 0), (11, 1), (14, 30)})
    await hour("gap_daily_below", [H._five_row("AAA")], {"AAA": gappy}, daily_high={"AAA": 10.95})
    await hour("gap_daily_equal", [H._five_row("AAA")], {"AAA": gappy}, daily_high={"AAA": 11.0})
    await hour("gap_daily_above_young", [H._five_row("AAA")], {"AAA": gappy}, daily_high={"AAA": 11.4})
    await hour("gap_daily_above_stale", [H._five_row("AAA")], {"AAA": gappy}, today=DAY + timedelta(days=7), daily_high={"AAA": 11.4})
    await hour("gap_no_daily_bar", [H._five_row("AAA")], {"AAA": H._hour_day(DAY, skip={(11, 0)})})
    await hour("gap_no_daily_bar_stale", [H._five_row("AAA")], {"AAA": H._hour_day(DAY, skip={(11, 0)})}, today=DAY + timedelta(days=7))
    thin = H._hour_day(DAY, cross=(10, 45), skip={(9, m) for m in range(35, 60)})
    await hour("thin_young", [H._five_row("AAA")], {"AAA": thin})
    await hour("thin_stale", [H._five_row("AAA")], {"AAA": thin}, today=DAY + timedelta(days=7))
    await hour("no_minutes_young", [H._five_row("AAA")], {"AAA": []})
    await hour("no_minutes_stale", [H._five_row("AAA")], {"AAA": []}, today=DAY + timedelta(days=7))
    await hour("nonpositive_stop", [H._five_row("AAA")], {"AAA": H._hour_day(DAY, hi=11.0, lo=5.0, cross=(10, 45))})
    await hour("two_tickers", [H._five_row("AAA"), H._five_row("BBB"), H._five_row("AAA")],
               {"AAA": H._hour_day(DAY, cross=(10, 45)), "BBB": H._hour_day(DAY, cross=(10, 15), cross_high=11.5)})
    # late fills
    alert = date(2026, 10, 20)
    hist = [(date(2026, 10, 21), (10.8, 10.9)), (date(2026, 10, 22), (10.6, 11.1)), (date(2026, 10, 23), (10.9, 11.3)),
            (date(2026, 10, 26), (11.0, 11.4)), (date(2026, 10, 27), (11.2, 11.6))]
    await hour_hist("late_walked", alert, date(2026, 10, 27), hist)
    await hour_hist("late_stopped", alert, date(2026, 10, 27), [(date(2026, 10, 21), (7.5, 8.0))])
    for a, t in ((DAY, DAY), (DAY - timedelta(days=1), DAY), (date(2026, 10, 23), date(2026, 10, 26))):
        await hour_hist(f"no_missed_{a}_{t}", a, t, [], minutes=lambda tk, d, s, e, a=a: H._hour_day(a, cross=(10, 45)))
    await hour_hist("late_no_history_young", alert, date(2026, 10, 23), [])
    await hour_hist("late_no_history_stale", alert, date(2026, 10, 27), [])
    await hour_hist("late_partial_1026", alert, date(2026, 10, 26), [(date(2026, 10, 21), (10.8, 11.0))])
    await hour_hist("late_partial_1027", alert, date(2026, 10, 27), [(d, (10.8, 11.0)) for d in (date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23))])
    # ── the 5-minute lane end to end ──
    await five()
    # ── the exit pass ──
    bar = lambda t, a, b: [{"o": 11, "h": 11.5, "l": 7.9, "c": 8.5, "t": 0}]
    hour_row = H._open_5m_row("AAA", DAY, id=7, bar_size_minutes=60, remaining_shares=1.0, entry_shares=1.0,
                              entry_price=11.0, hard_stop=8.0, stop_price=8.0)
    await exit_pass("hour_row_closed", [hour_row], DAY + timedelta(days=1), bar)
    await exit_pass("day0_skip", [H._open_5m_row("AAA", DAY, id=7, bar_size_minutes=60)], DAY, bar)
    mixed = [H._open_5m_row("AAA", DAY, id=1), H._open_5m_row("AAA", DAY, id=2, bar_size_minutes=60, remaining_shares=1.0,
                                                                 entry_shares=1.0, entry_price=11.0, hard_stop=8.0),
             H._open_5m_row("CCC", DAY, id=3, entry_price=10.0, hard_stop=9.0),
             H._open_5m_row("DDD", DAY + timedelta(days=1), id=4),                       # pre-alert on the step day
             H._open_5m_row("EEE", DAY - timedelta(days=10), id=5, hold_days=1),          # stale → quarantined
             H._open_5m_row("FFF", DAY, id=6, remaining_shares=0.0)]                      # nothing left
    gentle = lambda t, a, b: [{"o": 10.4, "h": 10.9, "l": 9.4 if t == "AAA" else 10.1, "c": 10.2, "t": 0}]
    await exit_pass("mixed", mixed, DAY + timedelta(days=1), gentle)
    await exit_pass("fetch_raises", [H._open_5m_row("AAA", DAY, id=1), H._open_5m_row("AAA", DAY, id=2, bar_size_minutes=60)],
                    DAY + timedelta(days=1), lambda t, a, b: RuntimeError("feed down"))
    await exit_pass("no_bar", [H._open_5m_row("AAA", DAY, id=1)], DAY + timedelta(days=1), lambda t, a, b: [])
    # ── the one-time replay ──
    row = H._open_5m_row("AAA", date(2026, 4, 30), id=9, hold_days=80, running_closes=[10.5],
                         exits=[], total_pnl=0.0, stop_price=9.5)
    bars = [{"o": 10.4, "h": 10.9, "l": 9.6, "c": 10.2 + 0.1 * i, "t": H._ms(date(2026, 5, 1) + timedelta(days=i))}
            for i in range(0, 12) if (date(2026, 5, 1) + timedelta(days=i)).weekday() < 5]
    await replay("replayed", row, date(2026, 5, 15), bars)
    await replay("no_bars", row, date(2026, 5, 15), [])
    # ── the book arms ──
    await book("std")
    await book("open_tape", sessions=B.SESS_OPEN, day0_high=12.9)
    never = B._day({(9, 30): (9.6, 10.0, 9.5, 9.9), (9, 31): (9.95, 10.05, 9.9, 10.02), (10, 10): (10.3, 10.6, 10.25, 10.3)},
                   filler=(10.0, 10.2, 9.9, 10.0))
    await book("never_retaken", minutes=never)
    holes = [b for b in never if not (time(12, 0) <= b["m"].time() < time(12, 10))]
    await book("holes_daily_below", minutes=holes, day0_high=10.59)
    young = datetime(2026, 8, 24, 18, 4, tzinfo=base._ET)
    await book("holes_daily_above_young", minutes=holes, day0_high=10.9, today=young.date(), now=young)
    await book("holes_daily_above_stale", minutes=holes, day0_high=10.9)
    await book("holes_no_daily_bar", minutes=holes)
    thin_b = [b for b in B.STD if not (time(9, 40) <= b["m"].time() < time(10, 10))]
    await book("thin_young", minutes=thin_b, today=young.date(), now=young)
    await book("thin_stale", minutes=thin_b)
    wide = B._day({(9, 30): (9.6, 10.0, 9.5, 9.9), (9, 31): (9.95, 10.05, 9.9, 10.02), (10, 10): (10.3, 21.0, 10.25, 10.3),
                   (10, 45): (21.0, 21.2, 20.9, 21.0)})
    await book("nonpositive_hour_stop", minutes=wide)
    print(json.dumps(OUT, indent=1, sort_keys=True, default=str))


asyncio.run(main())
