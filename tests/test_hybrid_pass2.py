"""#489 hybrid real-time Pass-2 — shadow-safety invariants.

The load-bearing guarantee: with the hybrid OFF (EP_RT_PASS2_ENABLED=false, the deploy default),
detection is byte-identical to today — Pass 1 uses the real MIN_GAP_PCT floor (9.0% since
2026-08-19, was 10.0%) and Pass 2 is a pure no-op.
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
    asyncio.run(ep_detector._rt_miss_watchdog([("AAA", 10.0)], set(), datetime(2026, 7, 20, 9, 35)))


def test_watchdog_noop_out_of_window(monkeypatch):
    # Outside the 9:31-9:44 ORB window -> no fetch (a later cross can't be entered anyway).
    monkeypatch.setattr(ep_detector, "EP_RT_MISS_WATCHDOG_ENABLED", True)
    monkeypatch.setattr(ep_detector, "EP_RT_PASS2_ENABLED", True)
    asyncio.run(ep_detector._rt_miss_watchdog([("AAA", 10.0)], set(), datetime(2026, 7, 20, 11, 0)))


def _wire_watchdog(monkeypatch, *, filters_pass: bool):
    """Common wiring: one 20% real-time crosser (AAA), extension query disabled, check_filters mocked.
    Returns the list of audit event_types the watchdog logged (audit-only since 7/21 — no Telegram)."""
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

    logged = []
    async def _log(event_type, *a, **k):
        logged.append(event_type)
    monkeypatch.setattr(ep_detector, "log_audit_event", _log)
    return logged


def test_watchdog_drops_crosser_failing_mechanical_gates(monkeypatch):
    # A 20% real-time crosser that FAILS check_filters (e.g. micro-cap) records NO miss (EP-shaped only).
    logged = _wire_watchdog(monkeypatch, filters_pass=False)
    asyncio.run(ep_detector._rt_miss_watchdog([("AAA", 10.0)], set(), datetime(2026, 7, 20, 9, 35)))
    assert "ep_rt_live_miss" not in logged


def test_watchdog_records_crosser_passing_mechanical_gates(monkeypatch):
    # Passes the gates + not in the caught superset -> records exactly one ep_rt_live_miss (audit-only
    # since 7/21; the morning digest sends the summary, not a per-ticker Telegram).
    logged = _wire_watchdog(monkeypatch, filters_pass=True)
    asyncio.run(ep_detector._rt_miss_watchdog([("AAA", 10.0)], set(), datetime(2026, 7, 20, 9, 35)))
    assert logged.count("ep_rt_live_miss") == 1


def test_watchdog_excludes_caught_superset(monkeypatch):
    # A crosser already in the PRE-Pass-2 superset (hybrid-catchable) is EXCLUDED -> no double-fire (AEHR 7/21).
    logged = _wire_watchdog(monkeypatch, filters_pass=True)
    asyncio.run(ep_detector._rt_miss_watchdog([("AAA", 10.0)], {"AAA"}, datetime(2026, 7, 20, 9, 35)))
    assert "ep_rt_live_miss" not in logged


def _mock_pool(monkeypatch, rows):
    class _C:
        async def fetch(self, q, *a):
            return rows
    class _A:
        async def __aenter__(self):
            return _C()
        async def __aexit__(self, *a):
            return False
    class _P:
        def acquire(self):
            return _A()
    async def _pool():
        return _P()
    monkeypatch.setattr(ep_detector, "get_pool", _pool)


def test_rt_miss_digest_summarizes_and_sends(monkeypatch):
    # #489 (7/21): one morning digest from today's ep_rt_live_miss audit rows.
    import json as _json
    rows = [{"detail": _json.dumps({"ticker": "AEHR", "rt_gap": 12.5, "tick_et": "09:31"})},
            {"detail": _json.dumps({"ticker": "HAS", "rt_gap": 10.9, "tick_et": "09:35"})}]
    _mock_pool(monkeypatch, rows)
    sent = []
    async def _tg(msg):
        sent.append(msg)
        return True
    monkeypatch.setattr(briefing, "send_telegram_message", _tg)
    n = asyncio.run(ep_detector.send_rt_miss_digest(run_date=datetime(2026, 7, 21).date()))
    assert n == 2 and len(sent) == 1 and "AEHR" in sent[0] and "HAS" in sent[0]


def test_rt_miss_digest_noop_when_empty(monkeypatch):
    _mock_pool(monkeypatch, [])
    sent = []
    async def _tg(msg):
        sent.append(msg)
        return True
    monkeypatch.setattr(briefing, "send_telegram_message", _tg)
    n = asyncio.run(ep_detector.send_rt_miss_digest(run_date=datetime(2026, 7, 21).date()))
    assert n == 0 and sent == []
