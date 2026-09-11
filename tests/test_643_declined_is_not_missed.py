"""#643 — a deliberate decline must never be re-reported as a delay-missed EP.

The BGSI defect, 2026-09-11: `_apply_rt_universe_overlay` SAW BGSI at +10.2% real-time and
DECLINED it on the sustain rule (the level did not hold 3 consecutive bars) — the right call,
unchanged here. But `_rt_miss_watchdog` never consulted the overlay's own rejections, so the
SAME ticker at the SAME tick was re-reported as `ep_rt_live_miss` ("delay-missed EP"), a label
naming a cause (delayed-feed lag) that had nothing to do with it. All-time: 106 `ep_rt_live_miss`
rows over 27 days, 56 of them (53%) have a same-day guard rejection on the same ticker.

Fix: the overlay now fills a caller-supplied `declined_out` dict at every point it declines a
ticker that had already cleared `raw_gap >= MIN_GAP_PCT`; the watchdog excludes anything in that
dict from `ep_rt_live_miss` and instead emits ONE `ep_rt_declined_not_missed` row naming the
ticker, its rt gap, the tick, and the guard reason. The digest renders both lines and never omits
the miss line silently. THE LINE: no admission/rejection/sizing/threshold changes anywhere in
this file — reporting and classification only.
"""
import asyncio
import json as _json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from agents.market_intelligence import briefing, collector, ep_detector as ep

_ET = ZoneInfo("America/New_York")
_PREV = date(2026, 9, 10)
PC = 100.0   # prev close


def _now(h=9, m=35):
    return datetime(2026, 9, 11, h, m, 0, tzinfo=_ET)


def _bar_ts(d: date):
    return datetime(d.year, d.month, d.day, 0, 0, tzinfo=_ET)


def _sn(now, pc, *, price=110.2, price_age=5.0, bid=110.15, ask=110.25, quote_age=10.0,
        minute_close=110.0, minute_vol=50_000, minute_age=60.0,
        daily_close=None, daily_date=_PREV):
    """A guard-passing rt snapshot (Q1-Q4 + prev_close cross-check all clean) at a +10.2% gap —
    the BGSI shape. Mirrors tests/test_490_rt_universe.py::_sn, rescaled from PC=10 to PC=100."""
    return {
        "price": price,
        "price_ts": now - timedelta(seconds=price_age) if price_age is not None else None,
        "bid": bid, "ask": ask, "bid_size": 1, "ask_size": 1,
        "quote_ts": now - timedelta(seconds=quote_age) if quote_age is not None else None,
        "minute_close": minute_close, "minute_volume": minute_vol,
        "minute_ts": now - timedelta(seconds=minute_age) if minute_age is not None else None,
        "day_volume": None,
        "daily_bar_close": pc if daily_close is None else daily_close,
        "daily_bar_ts": _bar_ts(daily_date) if daily_date else None,
        "prev_close": None,
        "prev_daily_bar_ts": None,
    }


def _wire_overlay(monkeypatch, snaps, *, sustain_on=True, closes=None):
    """Wire `_apply_rt_universe_overlay` for a single BGSI-shaped tick with the sustain rule ON
    and REJECTING (one bar under the floor). Returns the list of logged (event_type, summary,
    detail) tuples."""
    monkeypatch.setattr(ep, "EP_RT_UNIVERSE_ENABLED", True)
    monkeypatch.setattr(ep, "EP_RT_PASS2_ENABLED", True)

    async def _toggle(name, env, default=True):
        if name == "ep_rt_sustain_enabled":
            return sustain_on
        if name == "ep_rt_universe_authoritative":
            return False   # shadow — irrelevant to whether the decline fires
        return default
    monkeypatch.setattr(ep, "get_runtime_toggle", _toggle)

    async def _snaps_fn(tickers, timeout_s=4.0, concurrency=1, stats=None):
        if stats is not None:
            stats.update({"batches_total": 1, "batches_failed": 0})
        return snaps
    monkeypatch.setattr(collector, "get_alpaca_snapshots_batch", _snaps_fn)

    async def _closes_fn(tickers, now_et, lookback_min=15):
        return closes or {}
    monkeypatch.setattr(collector, "get_alpaca_minute_closes", _closes_fn)

    async def _holds(today):
        return set()
    monkeypatch.setattr(ep, "_corp_action_holds_today", _holds)
    monkeypatch.setattr(ep, "_audit_dedupe_check", lambda *a, **k: True)
    monkeypatch.setattr(ep, "_rt_fresh_seen", set())
    monkeypatch.setattr(ep, "_rt_fresh_seen_date", None)

    logged = []

    async def _log(event_type, summary, detail=""):
        logged.append((event_type, summary, detail))
    monkeypatch.setattr(ep, "log_audit_event", _log)
    return logged


def _wire_watchdog(monkeypatch, *, filters_pass=True):
    monkeypatch.setattr(ep, "EP_RT_MISS_WATCHDOG_ENABLED", True)
    monkeypatch.setattr(ep, "EP_RT_PASS2_ENABLED", True)

    async def _filters(ticker, alert_date, skip_mcap=False):
        return filters_pass, None if filters_pass else "market cap too low"
    monkeypatch.setattr(ep, "check_filters", _filters)

    async def _pool():   # -> ext_low stays empty, extension gate skipped
        raise RuntimeError("no db in test")
    monkeypatch.setattr(ep, "get_pool", _pool)
    monkeypatch.setattr(ep, "_audit_dedupe_check", lambda *a, **k: True)

    logged = []

    async def _log(event_type, summary, detail=""):
        logged.append((event_type, summary, detail))
    monkeypatch.setattr(ep, "log_audit_event", _log)
    return logged


# ── the BGSI case: declined on sustain_reject -> no live_miss, DOES get declined_not_missed ──

def test_sustain_rejected_ticker_is_declined_not_missed(monkeypatch):
    now = _now()
    rt_snap = {"BGSI": _sn(now, PC)}   # +10.2% raw, Q1-Q4 all clean -> reaches the sustain gate
    # One bar (09:33) dips under the floor -> the level did NOT hold 3 consecutive bars.
    closes = {"BGSI": [("09:31", 111.0), ("09:33", 108.5), ("09:35", 110.2)]}
    overlay_logged = _wire_overlay(monkeypatch, rt_snap, sustain_on=True, closes=closes)
    poly_snap = {"BGSI": {"min": {"c": 102.1}, "prevDay": {"c": PC, "v": 1_000_000}}}

    declined: dict = {}
    out, rt_snaps = asyncio.run(ep._apply_rt_universe_overlay(
        [], [("BGSI", PC)], poly_snap, {}, None, now, _PREV, declined_out=declined))

    # The overlay declined it (not admitted, not a shadow catch) and named the guard.
    assert out == []
    assert declined == {"BGSI": "ep_rt_sustain_reject"}
    assert any(e[0] == "ep_rt_sustain_reject" for e in overlay_logged)
    assert "ep_rt_universe_catch" not in [e[0] for e in overlay_logged]

    # Same tick, same snaps, same declined dict -> the watchdog.
    watchdog_logged = _wire_watchdog(monkeypatch, filters_pass=True)
    asyncio.run(ep._rt_miss_watchdog(
        [("BGSI", PC)], set(), now, snaps=rt_snaps, declined=declined))

    types = [e[0] for e in watchdog_logged]
    assert "ep_rt_live_miss" not in types, "a deliberate decline must never read as a miss"
    assert types.count("ep_rt_declined_not_missed") == 1
    _, summary, detail = next(e for e in watchdog_logged if e[0] == "ep_rt_declined_not_missed")
    assert "BGSI" in summary and "ep_rt_sustain_reject" in summary and "10.2" in summary
    d = _json.loads(detail)
    assert d["ticker"] == "BGSI" and d["declined_reason"] == "ep_rt_sustain_reject"
    assert d["tick_et"] == "09:35"


# ── a genuine miss (never seen by the overlay) must still fire — the alarm still works ───────

def test_genuine_miss_with_empty_declined_map_still_fires(monkeypatch):
    now = _now()
    logged = _wire_watchdog(monkeypatch, filters_pass=True)

    async def _snaps(tickers, timeout_s=4.0):
        return {"AAA": {"price": 12.0}}   # 12 vs prev_close 10 -> +20% rt, never seen by the overlay
    monkeypatch.setattr(collector, "get_alpaca_snapshots_batch", _snaps)

    asyncio.run(ep._rt_miss_watchdog([("AAA", 10.0)], set(), now, declined={}))
    types = [e[0] for e in logged]
    assert types.count("ep_rt_live_miss") == 1
    assert "ep_rt_declined_not_missed" not in types


def test_genuine_miss_with_declined_none_still_fires(monkeypatch):
    """`declined=None` (the default, unwired callers) must behave exactly as before #643."""
    now = _now()
    logged = _wire_watchdog(monkeypatch, filters_pass=True)

    async def _snaps(tickers, timeout_s=4.0):
        return {"AAA": {"price": 12.0}}
    monkeypatch.setattr(collector, "get_alpaca_snapshots_batch", _snaps)

    asyncio.run(ep._rt_miss_watchdog([("AAA", 10.0)], set(), now))
    assert [e[0] for e in logged].count("ep_rt_live_miss") == 1


def test_a_different_ticker_in_the_declined_map_does_not_shield_a_real_miss(monkeypatch):
    now = _now()
    logged = _wire_watchdog(monkeypatch, filters_pass=True)

    async def _snaps(tickers, timeout_s=4.0):
        return {"AAA": {"price": 12.0}}
    monkeypatch.setattr(collector, "get_alpaca_snapshots_batch", _snaps)

    asyncio.run(ep._rt_miss_watchdog(
        [("AAA", 10.0)], set(), now, declined={"ZZZ": "ep_rt_halt_suspect"}))
    types = [e[0] for e in logged]
    assert types.count("ep_rt_live_miss") == 1
    assert "ep_rt_declined_not_missed" not in types


# ── the digest: both lines render, and the miss line never vanishes silently ─────────────────

def _digest_pool(monkeypatch, miss_rows, catch_rows, declined_rows):
    class _C:
        async def fetch(self, q, *a):
            if "ep_rt_live_miss" in q:
                rows = miss_rows
            elif "ep_rt_declined_not_missed" in q:
                rows = declined_rows
            else:
                rows = catch_rows
            return [{"detail": _json.dumps(r)} for r in rows]

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
    monkeypatch.setattr(ep, "get_pool", _pool)


def test_digest_renders_declined_line_and_zero_miss_line_when_no_genuine_misses(monkeypatch):
    """The exact BGSI morning: zero genuine misses, one declined-not-missed. The miss line must
    still appear and say so — an omitted line is indistinguishable from a job that never ran."""
    _digest_pool(
        monkeypatch, miss_rows=[], catch_rows=[],
        declined_rows=[{"ticker": "BGSI", "rt_gap": 10.2, "tick_et": "09:35",
                        "declined_reason": "ep_rt_sustain_reject"}])
    sent = []

    async def _tg(msg):
        sent.append(msg)
        return True
    monkeypatch.setattr(briefing, "send_telegram_message", _tg)

    n = asyncio.run(ep.send_rt_miss_digest(run_date=date(2026, 9, 11)))
    assert len(sent) == 1
    msg = sent[0]
    assert "Real-time EP misses" in msg and "0" in msg   # the miss line is PRESENT, says zero
    assert "Declined, not missed" in msg
    assert "BGSI" in msg and "ep_rt_sustain_reject" in msg
    assert n >= 1


def test_digest_renders_both_lines_when_a_genuine_miss_also_exists(monkeypatch):
    _digest_pool(
        monkeypatch,
        miss_rows=[{"ticker": "AAA", "rt_gap": 15.0, "tick_et": "09:32"}],
        catch_rows=[],
        declined_rows=[{"ticker": "BGSI", "rt_gap": 10.2, "tick_et": "09:35",
                        "declined_reason": "ep_rt_sustain_reject"}])
    sent = []

    async def _tg(msg):
        sent.append(msg)
        return True
    monkeypatch.setattr(briefing, "send_telegram_message", _tg)

    n = asyncio.run(ep.send_rt_miss_digest(run_date=date(2026, 9, 11)))
    assert len(sent) == 1
    msg = sent[0]
    assert "AAA" in msg and "1 residual" in msg
    assert "BGSI" in msg and "Declined, not missed" in msg


def test_digest_still_noop_when_nothing_happened(monkeypatch):
    _digest_pool(monkeypatch, miss_rows=[], catch_rows=[], declined_rows=[])
    sent = []

    async def _tg(msg):
        sent.append(msg)
        return True
    monkeypatch.setattr(briefing, "send_telegram_message", _tg)

    n = asyncio.run(ep.send_rt_miss_digest(run_date=date(2026, 9, 11)))
    assert n == 0 and sent == []


# ── pin the wiring: the call site must thread the SAME dict into overlay and watchdog ────────

def test_call_site_wires_one_declined_dict_into_both_functions():
    """A future refactor that gives the overlay and the watchdog their own separate dicts (or
    forgets to pass one) would silently resurrect the BGSI defect with no test failure anywhere
    else — this pins the call site itself, not just the two functions in isolation."""
    src = open("agents/market_intelligence/ep_detector.py").read()
    assert "_declined_this_tick: dict = {}" in src
    overlay_call = src.index("await _apply_rt_universe_overlay(")
    watchdog_call = src.index("_rt_miss_watchdog(", overlay_call)
    overlay_kw = src.index("declined_out=_declined_this_tick", overlay_call)
    watchdog_kw = src.index("declined=_declined_this_tick", watchdog_call)
    assert overlay_call < overlay_kw < watchdog_call < watchdog_kw
