"""#489 hybrid real-time Pass-2 — shadow-safety invariants.

The load-bearing guarantee: with the hybrid OFF (EP_RT_PASS2_ENABLED=false, the deploy default),
detection is byte-identical to today — Pass 1 uses the real 10% floor and Pass 2 is a pure no-op.
"""
import asyncio
from datetime import datetime

from agents.market_intelligence import briefing, collector, ep_detector


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


def _wire_watchdog(monkeypatch, *, filters_pass: bool):
    """Common wiring: one 20% real-time crosser (AAA), extension query disabled, check_filters mocked."""
    monkeypatch.setattr(ep_detector, "EP_RT_MISS_WATCHDOG_ENABLED", True)
    monkeypatch.setattr(ep_detector, "EP_RT_PASS2_ENABLED", True)

    async def _snaps(tickers, timeout_s=4.0):
        return {"AAA": {"price": 12.0}}          # 12 vs prev_close 10 -> +20% rt
    monkeypatch.setattr(collector, "get_alpaca_snapshots_batch", _snaps)

    async def _pool():                            # -> ext_low stays empty, extension gate skipped
        raise RuntimeError("no db in test")
    monkeypatch.setattr(ep_detector, "get_pool", _pool)

    async def _filters(ticker, alert_date, skip_mcap=False):
        return (filters_pass, None if filters_pass else "market cap too low")
    monkeypatch.setattr(ep_detector, "check_filters", _filters)
    monkeypatch.setattr(ep_detector, "_audit_dedupe_check", lambda *a, **k: True)

    async def _log(*a, **k):
        return None
    monkeypatch.setattr(ep_detector, "log_audit_event", _log)

    sent = []
    async def _tg(msg):
        sent.append(msg)
        return True
    monkeypatch.setattr(briefing, "send_telegram_message", _tg)
    return sent


def test_watchdog_drops_crosser_failing_mechanical_gates(monkeypatch):
    # A 20% real-time crosser that FAILS check_filters (e.g. micro-cap) must NOT alert (A: EP-shaped only).
    sent = _wire_watchdog(monkeypatch, filters_pass=False)
    asyncio.run(ep_detector._rt_miss_watchdog([("AAA", 10.0)], [], datetime(2026, 7, 20, 9, 35)))
    assert sent == []


def test_watchdog_alerts_crosser_passing_mechanical_gates(monkeypatch):
    # A 20% real-time crosser that PASSES the mechanical EP gates must alert exactly once.
    sent = _wire_watchdog(monkeypatch, filters_pass=True)
    asyncio.run(ep_detector._rt_miss_watchdog([("AAA", 10.0)], [], datetime(2026, 7, 20, 9, 35)))
    assert len(sent) == 1 and "AAA" in sent[0]
