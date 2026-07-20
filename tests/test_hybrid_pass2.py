"""#489 hybrid real-time Pass-2 — shadow-safety invariants.

The load-bearing guarantee: with the hybrid OFF (EP_RT_PASS2_ENABLED=false, the deploy default),
detection is byte-identical to today — Pass 1 uses the real 10% floor and Pass 2 is a pure no-op.
"""
import asyncio
from datetime import datetime

from agents.market_intelligence import ep_detector


def test_pass1_floor_is_min_gap_when_hybrid_off(monkeypatch):
    monkeypatch.setattr(ep_detector, "EP_RT_PASS2_ENABLED", False)
    assert ep_detector._pass1_gap_floor() == ep_detector.MIN_GAP_PCT


def test_pass1_floor_is_superset_when_hybrid_on(monkeypatch):
    monkeypatch.setattr(ep_detector, "EP_RT_PASS2_ENABLED", True)
    monkeypatch.setattr(ep_detector, "EP_PASS1_SUPERSET_GAP_PCT", 5.0)
    assert ep_detector._pass1_gap_floor() == 5.0


def test_pass2_is_noop_when_disabled(monkeypatch):
    # Off -> candidates returned unchanged (same object), no Alpaca call, no floor re-apply.
    monkeypatch.setattr(ep_detector, "EP_RT_PASS2_ENABLED", False)
    cands = [{"ticker": "AAA", "gap_pct": 12.0, "prev_close": 10.0, "gap_pct_delayed": 12.0}]
    out = asyncio.run(ep_detector._apply_realtime_pass2(cands, datetime(2026, 7, 20, 9, 35)))
    assert out is cands


def test_watchdog_noop_when_disabled(monkeypatch):
    # #489 miss watchdog OFF -> early return, no fetch/alert, no error.
    monkeypatch.setattr(ep_detector, "EP_RT_MISS_WATCHDOG_ENABLED", False)
    asyncio.run(ep_detector._rt_miss_watchdog([("AAA", 10.0)], [], datetime(2026, 7, 20, 9, 35)))


def test_watchdog_noop_out_of_window(monkeypatch):
    # Outside the 9:31-9:44 ORB window -> no fetch (a later cross can't be entered anyway).
    monkeypatch.setattr(ep_detector, "EP_RT_MISS_WATCHDOG_ENABLED", True)
    monkeypatch.setattr(ep_detector, "EP_RT_PASS2_ENABLED", True)
    asyncio.run(ep_detector._rt_miss_watchdog([("AAA", 10.0)], [], datetime(2026, 7, 20, 11, 0)))
