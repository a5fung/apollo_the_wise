"""#598 follow-up (2026-10-04) — the flag scan's M&A / deal-pin screen covers TIGHTENING.

WHY. A buyout-pinned stock reads as a perfect TIGHTENING base (range collapses, volume bleeds
out), and the screen only ran on COILED + TRIGGERED — so it reached /flags and the 17:25 NEW
TODAY block. Same rule the coil board got on 2026-10-03: the news NOMINATES (is_likely_ma), the
scan date's own-day range DECIDES (<= 2.0% = pinned); plus the price-only Layer-2/3 backstop.

PINNED: a nominated + pinned TIGHTENING name is downgraded and announced nowhere; a nominated
but moving one stays; the price-only backstop covers TIGHTENING; WATCH is still unscreened; the
/flags header no longer calls a stage a setup.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import briefing, db, ma_filter
from agents.market_intelligence import flag_detector as fd
from tests.conftest import make_mock_pool

D1 = date(2026, 10, 2)


def _row(ticker, stage):
    return {
        "ticker": ticker, "stage": stage, "runup_pct": 1.30, "pivot_high_price": 49.76,
        "range_contraction_ratio": 0.5, "vol_contraction_ratio": 0.4, "base_age": 10,
        "fresh_tight_fires": False, "reason": None,
    }


def _bar(high, low, close):
    return {"trade_date": D1, "open_price": close, "high_price": high, "low_price": low,
            "close": close, "volume": 1000}


class _World:
    def __init__(self):
        self.sent = []
        self.audit = []
        self.inserted = []
        self.ma_asked = []


@pytest.fixture
def world(monkeypatch):
    w = _World()

    async def _send(text, chat_id=None, parse_mode=None, reply_markup=None):
        w.sent.append(text)
        return True

    async def _audit(event_type, summary, detail="", *, conn=None):
        w.audit.append((event_type, summary, detail))

    async def _insert(r):
        w.inserted.append((r["ticker"], r["stage"], r.get("reason")))

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])

    monkeypatch.setattr(briefing, "send_telegram_message", _send)
    monkeypatch.setattr(db, "log_audit_event", _audit)
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(db, "insert_flag_candidate", _insert)
    monkeypatch.setattr(db, "get_yesterday_flag_stages", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_recent_flag_stages", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_rs_for_tickers", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_sectors_batch", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_yesterday_flag_pivots", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_flag_failure_carry", AsyncMock(return_value={}))
    monkeypatch.setattr(fd, "reconcile_flag_state_post_eod", AsyncMock())
    monkeypatch.setattr(ma_filter, "should_log_mna_filter_fired", AsyncMock(return_value=True))
    return w


def _install(monkeypatch, w, stages, *, bars, nominated, pin_sigs=None):
    """stages: {ticker: scored stage}; bars: {ticker: today's own-day bar}; nominated: tickers the
    news nominates. The fake is_likely_ma mirrors production: a nominated name BLOCKS only when the
    scan's own pin_reader reports the own-day range pinned."""
    monkeypatch.setattr(db, "get_flag_universe",
                        AsyncMock(return_value={t: ["rs_top200"] for t in stages}))

    async def _history(ticker, n, end_date=None):
        if n == 5:
            return [bars[ticker]] if ticker in bars else []
        return [{}] * 80          # scoring history (compute_flag_metrics is stubbed)
    monkeypatch.setattr(db, "get_recent_daily_history", _history)

    monkeypatch.setattr(fd, "compute_flag_metrics",
                        lambda history, ticker=None, **kw: _row(ticker, stages[ticker]))
    monkeypatch.setattr(fd, "_check_deal_pin_signatures_batch",
                        AsyncMock(return_value=pin_sigs or {}))

    async def _is_ma(ticker, *, pin_reader=None, **kw):
        w.ma_asked.append(ticker)
        if ticker not in nominated:
            return False, {}
        reading = await pin_reader()
        return bool(reading.pinned), {"source": "polygon_headline_model"}
    monkeypatch.setattr(ma_filter, "is_likely_ma", _is_ma)


@pytest.mark.asyncio
async def test_a_nominated_and_pinned_tightening_name_is_downgraded_and_announced_nowhere(world, monkeypatch):
    # DEAL: news nominates, own-day range 0.2% (pinned). MOVE: news nominates, own-day range 6%.
    _install(monkeypatch, world, {"DEAL": "TIGHTENING", "MOVE": "TIGHTENING"},
             bars={"DEAL": _bar(10.02, 10.00, 10.01), "MOVE": _bar(10.6, 10.0, 10.0)},
             nominated={"DEAL", "MOVE"})
    by_stage = await fd.run_flag_scan(D1)

    assert [r["ticker"] for r in by_stage["unqualified"]] == ["DEAL"]
    assert by_stage["unqualified"][0]["reason"] == "mna_filter:polygon_headline_model"
    assert by_stage["unqualified"][0]["original_stage"] == "TIGHTENING"
    assert [r["ticker"] for r in by_stage["TIGHTENING"]] == ["MOVE"]      # price moves -> stays
    # persisted flip (what /flags reads), so the board cannot show it
    assert ("DEAL", "unqualified", "mna_filter:polygon_headline_model") in world.inserted
    # the usual announcement row, original stage preserved
    fired = [a for a in world.audit if a[0] == "mna_filter_fired"]
    assert len(fired) == 1 and "DEAL" in fired[0][1] and "'stage': 'TIGHTENING'" in fired[0][2]
    assert "'detector': 'flag'" in fired[0][2]
    # NEW TODAY names only the mover; the deal-pinned name appears nowhere in the message
    assert len(world.sent) == 1
    text = world.sent[0]
    assert "NEW TODAY" in text and "<code>MOVE</code>" in text
    assert "DEAL" not in text
    assert [a[1] for a in world.audit if a[0] == "flag_stage_transition"] == [
        "MOVE entered TIGHTENING 2026-10-02"]


@pytest.mark.asyncio
async def test_the_price_only_backstop_covers_tightening(world, monkeypatch):
    # No news at all (KALV shape): the Layer-2 mature-pin signature alone must downgrade it.
    sig = {"is_pin": True, "is_fresh_pin": False, "median_range_pct": 0.002,
           "sub_threshold_days": 8, "total_days": 9}
    _install(monkeypatch, world, {"KALV": "TIGHTENING", "FREE": "TIGHTENING"},
             bars={}, nominated=set(), pin_sigs={"KALV": sig})
    by_stage = await fd.run_flag_scan(D1)

    assert [r["ticker"] for r in by_stage["unqualified"]] == ["KALV"]
    assert by_stage["unqualified"][0]["reason"] == "mna_filter:deal_pin_signature"
    assert [r["ticker"] for r in by_stage["TIGHTENING"]] == ["FREE"]
    assert ("KALV", "unqualified", "mna_filter:deal_pin_signature") in world.inserted
    assert "KALV" not in world.sent[0]
    assert any(a[0] == "mna_filter_fired" and "KALV" in a[1] for a in world.audit)


@pytest.mark.asyncio
async def test_watch_is_still_not_screened(world, monkeypatch):
    _install(monkeypatch, world, {"WWW": "WATCH", "TTT": "TIGHTENING"}, bars={}, nominated=set())
    await fd.run_flag_scan(D1)
    assert world.ma_asked == ["TTT"]          # WATCH never costs a lookup (40-50 names a day)


def test_the_flags_header_no_longer_calls_a_stage_a_setup(monkeypatch):
    import asyncio
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from agents.market_intelligence.collector import et_today
    from shared.models import AgentRequest

    async def _window(query_date, stages=None):
        return [{"ticker": "COIL", "stage": "COILED", "base_age": 9,
                 "range_contraction_ratio": 0.5, "vol_contraction_ratio": 0.4}]

    class _Conn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def fetchval(self, *a, **kw):
            return et_today()

    class _Pool:
        def acquire(self):
            return _Conn()

    monkeypatch.setattr("agents.market_intelligence.db.get_flag_candidates_window", _window)
    monkeypatch.setattr("agents.market_intelligence.db.get_pool", AsyncMock(return_value=_Pool()))
    monkeypatch.setattr("agents.market_intelligence.db.get_htf_breakout_shadow_summary",
                        AsyncMock(return_value={}))
    res = asyncio.run(MarketIntelligenceAgent()._handle_flag_query(
        AgentRequest(task="/flags", user_id=1, conversation_id="t")))
    text = res.result or ""
    assert "🌀 *COILED — tightest bases, watch only (1)*" in text
    assert "actionable" not in text.lower() and "setup" not in text.lower()
