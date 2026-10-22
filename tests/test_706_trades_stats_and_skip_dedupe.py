"""#706 — /trades position stats + one ORB skip line per (ticker, reason) per ET day.

His 2026-10-21 asks (display only; no order path, no sizing, no entry decision changes):
  * OPEN position  -> size as a % of the account's equity, and the stop % = (current - stop) /
                      current, the % of the CURRENT price we lose if the stop is hit (PLAN #706's
                      own formula: price 100, stop 95 -> +5.0), side-aware.
  * CLOSED position-> % win/loss beside the R and the $ P&L.
  * the SPCX skip line arrived twice, 10 s apart (bar stream + 09:31 cron both run the monitor).

The numbers are fixtures, not real positions.
"""
from __future__ import annotations

import asyncio
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence import trade_stats as ts
from agents.market_intelligence.closed_trade_line import fmt_closed_line
from agents.market_intelligence.broker import live_tracker as lt
from tests.conftest import make_mock_pool


# ═══ 1. the maths ══════════════════════════════════════════════════════════════════════════

def test_position_pct_is_market_value_over_account_equity():
    assert ts.position_pct_of_equity(5_000, 50_000) == pytest.approx(10.0)
    assert ts.position_pct_of_equity(1_234.5, 20_000) == pytest.approx(6.1725)


def test_a_short_positions_negative_market_value_is_a_positive_size():
    """Alpaca reports a short's market_value NEGATIVE — a -$5k short is a 10% position."""
    assert ts.position_pct_of_equity(-5_000, 50_000) == pytest.approx(10.0)


@pytest.mark.parametrize("mv,eq", [(None, 50_000), (5_000, None), (5_000, 0), (5_000, -1),
                                   ("x", 50_000), (float("nan"), 50_000), (5_000, float("inf"))])
def test_position_pct_is_none_when_an_input_is_missing_or_unusable(mv, eq):
    assert ts.position_pct_of_equity(mv, eq) is None


def test_long_stop_pct_is_the_loss_from_the_current_price():
    """PLAN #706 / the brief: long = (current - stop) / current. Price 100, stop 95 -> lose 5%
    -> +5.0 (POSITIVE: the % lost if stopped). Pinned against the literal formula."""
    assert ts.stop_loss_pct("long", 100.0, 95.0) == pytest.approx(5.0)
    assert ts.stop_loss_pct("long", 100.0, 95.0) == pytest.approx((100.0 - 95.0) / 100.0 * 100)
    # the % is of the CURRENT price, not of entry: price ran to 120, stop still 95 -> 20.83%
    assert ts.stop_loss_pct("long", 120.0, 95.0) == pytest.approx(25 / 120 * 100)


def test_short_stop_sits_above_the_price_and_still_reads_as_a_loss():
    """A short's stop sits ABOVE the price. Price 100, stop 105 -> a 5% loss -> +5.0, the same
    sign as a long's. The long formula on the same numbers would read -5.0 — the WOULD-FAIL-IF."""
    assert ts.stop_loss_pct("short", 100.0, 105.0) == pytest.approx(5.0)
    assert ts.stop_loss_pct("short", 100.0, 105.0) == pytest.approx((105.0 - 100.0) / 100.0 * 100)
    assert ts.stop_loss_pct("long", 100.0, 105.0) == pytest.approx(-5.0)   # the wrong-side read


def test_a_price_already_through_the_stop_reads_negative_not_hidden():
    assert ts.stop_loss_pct("long", 100.0, 101.0) == pytest.approx(-1.0)
    assert ts.stop_loss_pct("short", 100.0, 99.0) == pytest.approx(-1.0)


@pytest.mark.parametrize("side,cur,stop", [
    (None, 100, 95), ("flat", 100, 95), ("", 100, 95),   # unknown side -> no number
    ("long", None, 95), ("long", 100, None),             # a missing price
    ("long", 0, 95), ("long", 100, 0), ("long", -3, 95), ("long", 100, -1),
    ("long", float("nan"), 95),
])
def test_stop_pct_is_none_on_unknown_side_or_missing_price(side, cur, stop):
    assert ts.stop_loss_pct(side, cur, stop) is None


def test_side_accepts_the_brokers_value_in_any_spelling():
    assert ts.normalize_side("long") == "long"
    assert ts.normalize_side("PositionSide.SHORT") == "short"
    assert ts.normalize_side(" Short ") == "short"
    assert ts.normalize_side("buy") is None and ts.normalize_side(None) is None


def test_closed_pct_equals_exit_over_entry_on_a_single_exit_long():
    """VICR #400 (scripts/probes/_696/vicr_400_row.txt): 211.50 -> 287.23, 1 share, +$75.73.
    total_pnl / cost IS (exit - entry) / entry here."""
    t = {"entry_price": 211.5, "entry_shares": 1, "total_pnl": 75.73}
    assert ts.trade_return_pct(t) == pytest.approx((287.23 - 211.5) / 211.5 * 100, abs=1e-6)


def test_closed_pct_on_a_short_is_entry_minus_exit_over_entry():
    """Short: entry 100, covered at 90, 10 sh -> +$100 -> +10% == (entry - exit) / entry."""
    t = {"entry_price": 100.0, "entry_shares": 10, "total_pnl": 100.0}
    assert ts.trade_return_pct(t) == pytest.approx((100 - 90) / 100 * 100)
    losing = {"entry_price": 100.0, "entry_shares": 10, "total_pnl": -50.0}  # covered at 105
    assert ts.trade_return_pct(losing) == pytest.approx(-5.0)


def test_closed_pct_stays_right_when_the_trade_exited_in_two_legs():
    """FIGS 08-07: +$6.90 partial on 20 sh @15.84, then -$13.74 on 41 sh @15.16, 61 sh entered at
    15.495. The LAST leg alone reads -2.2%; the trade's true result is -0.72% (-$6.84 on $945)."""
    t = {"entry_price": 15.495082, "entry_shares": 61, "total_pnl": 6.900359999999992 - 13.738361999999995}
    assert ts.trade_return_pct(t) == pytest.approx(-0.7236, abs=0.01)
    assert (15.16 - 15.495082) / 15.495082 * 100 < -2.0     # what an "(exit - entry) / entry" of the last leg says


def test_closed_pct_on_a_reentry_row_is_the_whole_rows_pnl_over_the_last_attempts_cost():
    """Documented limit (trade_stats docstring): a stop-out + re-entry keeps ONE row — total_pnl sums
    every attempt's exits, entry_price/shares are the LAST fill's. Attempt 1: 10 sh @100 stopped at
    95 (-$50). Attempt 2: 10 sh @98, sold at 108 (+$100). Row: pnl +$50 over 98 x 10 = +5.1%. The
    same frame the R uses, so the two agree; it is not (exit - entry)/entry of either leg."""
    t = {"entry_price": 98.0, "entry_shares": 10, "total_pnl": -50.0 + 100.0, "entry_attempt": 2}
    assert ts.trade_return_pct(t) == pytest.approx(50.0 / 980.0 * 100)
    assert "RE-ENTRY" in ts.__doc__


@pytest.mark.parametrize("bad", [
    {"entry_price": 100.0, "entry_shares": 10},                      # no pnl
    {"total_pnl": 5.0, "entry_shares": 10},                          # no entry
    {"total_pnl": 5.0, "entry_price": 100.0},                        # no shares
    {"total_pnl": 5.0, "entry_price": 100.0, "entry_shares": 0},
    {"total_pnl": 5.0, "entry_price": 0, "entry_shares": 10},
    {"total_pnl": float("nan"), "entry_price": 100.0, "entry_shares": 10},
    {},
])
def test_closed_pct_is_none_when_the_frame_is_missing(bad):
    assert ts.trade_return_pct(bad) is None


def test_fmt_pct():
    assert ts.fmt_pct(None) == "—" and ts.fmt_pct(None, signed=True) == "—"
    assert ts.fmt_pct(4.234) == "4.2%" and ts.fmt_pct(-5.04, signed=True) == "-5.0%"
    assert ts.fmt_pct(0.04, signed=True) == "+0.0%" and ts.fmt_pct(-0.04, signed=True) == "+0.0%"   # never "-0.0%"


def test_open_position_stats_bundle():
    s = ts.open_position_stats(side="long", market_value=5_000, current_price=100.0,
                               stop_price=95.0, equity=50_000)
    assert s == {"side": "long", "position_pct": pytest.approx(10.0), "stop_pct": pytest.approx(5.0)}
    none = ts.open_position_stats(side=None, market_value=None, current_price=None,
                                  stop_price=95.0, equity=50_000)
    assert none == {"side": None, "position_pct": None, "stop_pct": None}


# ═══ 2. the render ═════════════════════════════════════════════════════════════════════════

def test_size_and_stop_lines_render_plain_text_with_no_table():
    stats = {"position_pct": 8.14, "stop_pct": 5.07}
    lines = ts.fmt_size_stop_lines(shares=19, market_value=4_210, stop_price=212.4, stats=stats)
    assert lines == ["      19 sh · $4,210 · 8.1% of equity",
                     "      Stop $212.40 · 5.1% to stop"]
    assert "|" not in "".join(lines)         # Telegram cannot render pipe tables
    assert "\t" not in "".join(lines)        # nor tab-aligned columns: plain indented lines only


def test_missing_numbers_render_a_dash_never_a_zero():
    lines = ts.fmt_size_stop_lines(shares=19, market_value=0, stop_price=None,
                                   stats={"position_pct": None, "stop_pct": None})
    assert lines[0].endswith("— of equity") and "0.0%" not in lines[0]
    assert lines[1] == "      Stop ? · —"


def test_a_price_through_the_stop_is_said_in_words_not_as_a_bare_minus():
    assert ts.fmt_stop_pct(-1.04) == "through stop by 1.0%"
    assert ts.fmt_stop_pct(0.04) == "0.0% to stop" and ts.fmt_stop_pct(-0.04) == "0.0% to stop"
    assert ts.fmt_stop_pct(5.0) == "5.0% to stop" and ts.fmt_stop_pct(None) == "—"


def test_the_one_line_form_names_the_equity_it_used():
    line = ts.fmt_stat_line(stats={"position_pct": 8.14, "stop_pct": 5.07}, equity=50_000)
    assert line == "  8.1% of $50,000 equity · 5.1% to stop"
    assert ts.fmt_stat_line(stats={"position_pct": None, "stop_pct": None}, equity=None) == \
        "  — of — equity · —"


def test_the_lines_survive_the_telegram_html_conversion():
    from shared.telegram_format import md_to_html
    stats = {"position_pct": 8.14, "stop_pct": 5.07}
    body = "\n".join(["  🟢 *ABCD* · 2d"] + ts.fmt_size_stop_lines(
        shares=19, market_value=4_210, stop_price=212.4, stats=stats))
    html = md_to_html(body)
    assert "8.1% of equity" in html and "5.1% to stop" in html and "<b>ABCD</b>" in html


_VICR_400 = {
    "id": 400, "ticker": "VICR", "entry_price": 211.5, "hard_stop": 201.13010000000003,
    "orb_low": 206.55, "entry_shares": 1, "total_pnl": 75.73000000000002, "hold_days": 19,
    "ep_score": 71, "closed_at": datetime(2026, 10, 7, 13, 30, tzinfo=timezone.utc),
    "exits": json.dumps([{"price": 287.23, "shares": 1, "pnl": 75.73, "reason": "stop_hit"}]),
}


def _parse(raw):
    return raw if isinstance(raw, list) else json.loads(raw or "[]")


def test_closed_line_shows_pct_beside_dollars_and_r():
    assert fmt_closed_line(_VICR_400, parse_exits=_parse)[0] == "  ✅ *VICR* $+76 · +7.3R · +35.8% (19d) · Oct 07"


def test_closed_line_loser_shows_a_negative_pct():
    loser = dict(_VICR_400, entry_price=100.0, hard_stop=95.0, entry_shares=10, total_pnl=-50.0)
    assert fmt_closed_line(loser, parse_exits=_parse)[0] == "  ❌ *VICR* $-50 · -1.0R · -5.0% (19d) · Oct 07"


def test_closed_line_without_a_pct_frame_omits_it_like_the_r():
    no_shares = dict(_VICR_400, entry_shares=None)
    assert fmt_closed_line(no_shares, parse_exits=_parse)[0] == "  ✅ *VICR* $+76 (19d) · Oct 07"
    no_stop = dict(_VICR_400, hard_stop=None, orb_low=None)   # no R frame, the % still computes
    assert fmt_closed_line(no_stop, parse_exits=_parse)[0] == "  ✅ *VICR* $+76 · +35.8% (19d) · Oct 07"


# ═══ 3. the real /trades handler, end to end ═══════════════════════════════════════════════

def _make_agent():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from shared.models import AgentName
    with patch("agents.base.get_secrets"), patch("shared.audit.log_action"):
        agent = MarketIntelligenceAgent.__new__(MarketIntelligenceAgent)
        agent.agent_name = AgentName.MARKET_INTELLIGENCE
    return agent


def _open_row(ticker, entry, stop, shares):
    return {"ticker": ticker, "alert_date": date(2026, 10, 20), "entry_price": entry,
            "remaining_shares": shares, "stop_price": stop, "hard_stop": stop, "total_pnl": 0,
            "hold_days": 1, "partial_taken": False, "breakeven_active": False, "ep_score": 70,
            "catalyst_quality": "strong", "exits": "[]", "stop_order_id": "abc"}


def _closed_row():
    return {k: _VICR_400[k] for k in ("ticker", "entry_price", "total_pnl", "hold_days", "exits",
                                      "ep_score", "closed_at", "hard_stop", "orb_low", "entry_shares")}


def _render_summary(open_rows, positions, *, account=None, account_raises=False, closed=None):
    """Drive the real _handle_trades_detail summary view. Returns (text, get_account mock)."""
    from agents.market_intelligence import agent as agent_mod
    from agents.market_intelligence import execution_client
    from shared.models import AgentRequest

    pool, conn = make_mock_pool()

    async def _fetch(sql, *a):
        if "GROUP BY ticker" in sql:
            return []
        if "status = 'filled' AND remaining_shares > 0" in sql:
            return open_rows
        if "order_placed" in sql:
            return []
        if "status = 'closed'" in sql:
            return closed or []
        return []

    conn.fetch = AsyncMock(side_effect=_fetch)
    conn.fetchrow = AsyncMock(return_value={"winners": 1, "losers": 0, "realized": 75.73})

    async def _pos(ticker, account_mode=None):
        return positions.get(ticker)

    get_account = AsyncMock(side_effect=RuntimeError("broker down")) if account_raises \
        else AsyncMock(return_value=account)

    async def run():
        with patch.object(agent_mod, "get_pool", new=AsyncMock(return_value=pool)), \
             patch.object(execution_client, "get_position", new=_pos), \
             patch.object(execution_client, "get_account", new=get_account):
            req = AgentRequest(task="/trades_detail summary 2026-10-21", user_id=1, conversation_id="t")
            return await _make_agent()._handle_trades_detail(req)

    resp = asyncio.run(run())
    assert resp.success
    return resp.result, get_account


def test_the_summary_shows_size_and_stop_on_a_long_position():
    text, get_account = _render_summary(
        [_open_row("ABCD", 100.0, 95.0, 50)],
        {"ABCD": {"current_price": 100.0, "unrealized_pl": 0.0, "market_value": 5_000.0, "side": "long"}},
        account={"equity": 50_000.0},
    )
    assert "equity $50,000" in text                     # the denominator is on the page
    assert "10.0% of equity" in text
    assert "Stop $95.00 · 5.0% to stop" in text
    # ONE read, from the LIVE account — the no-arg form resolves to the paper account
    get_account.assert_awaited_once_with(account_mode="live")


def test_the_summary_is_side_aware_for_a_short():
    text, _ = _render_summary(
        [_open_row("SHRT", 100.0, 105.0, 50)],
        {"SHRT": {"current_price": 100.0, "unrealized_pl": 0.0, "market_value": -5_000.0, "side": "short"}},
        account={"equity": 50_000.0},
    )
    assert "10.0% of equity" in text                   # |negative market value|
    assert "Stop $105.00 · 5.0% to stop" in text       # a loss, though the stop sits ABOVE the price
    assert "-5.0%" not in text and "through stop" not in text


def test_the_summary_shows_dashes_when_the_account_read_fails():
    text, _ = _render_summary(
        [_open_row("ABCD", 100.0, 95.0, 50)],
        {"ABCD": {"current_price": 100.0, "unrealized_pl": 0.0, "market_value": 5_000.0, "side": "long"}},
        account_raises=True,
    )
    assert "equity —" in text and "— of equity" in text
    assert "Stop $95.00 · 5.0% to stop" in text        # the stop % needs no equity


def test_a_position_the_broker_did_not_return_gets_dashes_not_zeros():
    text, _ = _render_summary([_open_row("GONE", 100.0, 95.0, 50)], {}, account={"equity": 50_000.0})
    assert "— of equity" in text and "Stop $95.00 · —" in text and "to stop" not in text
    assert "0.0% of equity" not in text


def test_the_account_is_not_read_when_nothing_is_open():
    text, get_account = _render_summary([], {}, account={"equity": 50_000.0}, closed=[_closed_row()])
    get_account.assert_not_awaited()
    assert "+35.8%" in text                            # the closed line carries the % in the summary


def test_summary_text_has_no_pipe_table():
    text, _ = _render_summary(
        [_open_row("ABCD", 100.0, 95.0, 50)],
        {"ABCD": {"current_price": 100.0, "unrealized_pl": 0.0, "market_value": 5_000.0, "side": "long"}},
        account={"equity": 50_000.0}, closed=[_closed_row()],
    )
    assert "|" not in text


# ─── the per-ticker view (`/trades FIGS`) and the /trades/summary endpoint ───────────────────

def _acct_by_mode(equities: dict):
    """get_account mock: ONE equity per account mode, and a record of every mode asked for."""
    async def _acct(account_mode=None):
        if account_mode not in equities:
            raise AssertionError(f"get_account called with an unexpected mode {account_mode!r}")
        return {"equity": equities[account_mode]}
    return AsyncMock(side_effect=_acct)


def _pos_by_mode(positions: dict):
    """get_position mock keyed (ticker, account_mode); records every call. A None mode (the
    no-arg form) raises: no #706 read may use it for a row whose book is known."""
    async def _pos(ticker, account_mode=None):
        if account_mode is None:
            raise AssertionError(f"get_position({ticker!r}) used the no-arg (paper-resolving) form")
        return positions.get((ticker, account_mode))
    return AsyncMock(side_effect=_pos)


def _ticker_view_rows():
    base = {"alert_date": date(2026, 10, 20), "ep_score": 70, "gap_pct": 12.0,
            "catalyst_quality": "strong", "regime": "bull", "skip_reason": None, "orb_high": 100.0,
            "orb_low": 95.0, "hold_days": 2, "exits": "[]", "entries": None, "entry_attempt": 1}
    return [
        dict(base, ticker="FIGS", status="filled", account_mode="live", entry_price=100.0,
             stop_price=95.0, total_pnl=0.0, entry_shares=50),
        dict(base, ticker="FIGS", status="filled", account_mode="paper", entry_price=100.0,
             stop_price=90.0, total_pnl=0.0, entry_shares=20),
        dict(base, ticker="FIGS", status="closed", account_mode="live", entry_price=15.495082,
             stop_price=14.0, total_pnl=6.900359999999992 - 13.738361999999995, entry_shares=61,
             hold_days=5, exits=json.dumps([{"price": 15.84, "shares": 20, "pnl": 6.90, "reason": "partial"},
                                            {"price": 15.16, "shares": 41, "pnl": -13.74, "reason": "stop_hit"}])),
    ]


def _render_ticker_view(rows, *, get_account, get_position, ticker="FIGS"):
    # conftest STUBS backtester.tracker; the real row formatter is compiled from source, as
    # tests/test_trades_ticker_both_books.py does, so the lines under test are the shipped ones.
    from tests.test_trades_ticker_both_books import _real_formatter_module
    from agents.market_intelligence import agent as agent_mod
    from agents.market_intelligence import constants
    from agents.market_intelligence import execution_client
    from shared.models import AgentRequest

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=rows)
    conn.fetchrow = AsyncMock(return_value={"total": 3, "open_count": 2, "winners": 0, "losers": 1,
                                            "realized_pnl": -6.84, "filtered_count": 0})

    async def run():
        with patch.object(agent_mod, "get_pool", new=AsyncMock(return_value=pool)), \
             patch.object(constants, "LIVE_TRADING_ENABLED", True), \
             patch.object(execution_client, "get_position", new=get_position), \
             patch.object(execution_client, "get_account", new=get_account), \
             patch.dict(sys.modules, {"agents.market_intelligence.backtester.tracker": _real_formatter_module()}):
            req = AgentRequest(task=f"/trades {ticker}", user_id=1, conversation_id="t")
            return await _make_agent()._handle_trades_query(req, ticker=ticker)

    resp = asyncio.run(run())
    assert resp.success
    return resp.result


def test_the_ticker_view_shows_both_stats_on_open_rows_and_the_pct_on_closed_rows():
    """DoD: the per-ticker view (`/trades FIGS`) carries the stats too — each row measured against
    ITS OWN book (the live row against the live equity, the paper-lane row against the paper's)."""
    get_account = _acct_by_mode({"live": 50_000.0, "paper": 100_000.0})
    get_position = _pos_by_mode({
        ("FIGS", "live"): {"current_price": 100.0, "market_value": 5_000.0, "side": "long", "unrealized_pl": 0.0},
        ("FIGS", "paper"): {"current_price": 100.0, "market_value": 2_000.0, "side": "long", "unrealized_pl": 0.0},
    })
    text = _render_ticker_view(_ticker_view_rows(), get_account=get_account, get_position=get_position)
    assert "  10.0% of $50,000 equity · 5.0% to stop" in text      # live row: 5000 / 50000, stop 95
    assert "  2.0% of $100,000 equity · 10.0% to stop" in text     # paper row: 2000 / 100000, stop 90
    assert "Total P&L: $-6.84* · -0.7% (5d)" in text               # closed: the trade's whole % (two exits)
    assert sorted(c.kwargs["account_mode"] for c in get_account.await_args_list) == ["live", "paper"]  # one per mode
    assert sorted((c.args[0], c.kwargs["account_mode"]) for c in get_position.await_args_list) == \
        [("FIGS", "live"), ("FIGS", "paper")]
    assert "|" not in text


def test_the_ticker_view_shows_dashes_when_the_broker_reads_fail():
    get_account = AsyncMock(side_effect=RuntimeError("broker down"))
    get_position = AsyncMock(side_effect=RuntimeError("broker down"))
    text = _render_ticker_view(_ticker_view_rows(), get_account=get_account, get_position=get_position)
    assert "  — of — equity · —" in text
    assert "0.0% of" not in text


def test_the_ticker_view_reads_no_broker_when_nothing_is_open():
    get_account, get_position = AsyncMock(), AsyncMock()
    text = _render_ticker_view(_ticker_view_rows()[2:], get_account=get_account, get_position=get_position)
    get_account.assert_not_awaited()
    get_position.assert_not_awaited()
    assert "-0.7%" in text


def _call_trades_summary_endpoint(open_rows, *, get_account, get_position, legacy_equity=777.0):
    """Drive the real /trades/summary route function (registered by _register_extra_routes)."""
    from fastapi import FastAPI
    from agents.market_intelligence import db as db_mod       # the route imports get_pool locally
    from agents.market_intelligence import execution_client

    agent = _make_agent()
    agent.app = FastAPI()
    agent._register_extra_routes()
    endpoint = next(r.endpoint for r in agent.app.routes if getattr(r, "path", None) == "/trades/summary")

    pool, conn = make_mock_pool()

    async def _fetch(sql, *a):
        if "remaining_shares > 0" in sql:
            return open_rows
        return []

    conn.fetch = AsyncMock(side_effect=_fetch)
    conn.fetchrow = AsyncMock(return_value={"total": 2, "open_count": len(open_rows), "winners": 0,
                                            "losers": 0, "realized_pnl": 0})
    legacy = {"called": 0}

    async def _acct(account_mode=None):
        if account_mode is None:
            legacy["called"] += 1
            return {"equity": legacy_equity}
        return await get_account(account_mode=account_mode)

    async def run():
        with patch.object(db_mod, "get_pool", new=AsyncMock(return_value=pool)), \
             patch.object(execution_client, "get_position", new=get_position), \
             patch.object(execution_client, "get_account", new=AsyncMock(side_effect=_acct)), \
             patch("agents.market_intelligence.backtester.tracker.get_paper_trading_summary",
                   new=AsyncMock(return_value={}), create=True):   # conftest stubs the tracker module
            return await endpoint(_="x")

    return asyncio.run(run()), legacy


def test_the_summary_endpoint_measures_each_position_against_its_own_account():
    """The table holds BOTH books; the no-arg reads resolve to the legacy global mode (paper on
    prod). A live row must be read from, and divided by, the LIVE account — never the paper one."""
    def row(ticker, mode, stop):
        return {"id": 1, "ticker": ticker, "alert_date": date(2026, 10, 20), "ep_score": 70,
                "entry_price": 100.0, "remaining_shares": 50, "stop_price": stop, "hard_stop": stop,
                "hold_days": 1, "position_size": 5000, "risk_dollars": 250, "total_pnl": 0,
                "partial_taken": False, "breakeven_active": False, "catalyst_quality": "strong",
                "account_mode": mode}

    get_account = _acct_by_mode({"live": 50_000.0, "paper": 100_000.0})
    get_position = _pos_by_mode({
        ("AAA", "live"): {"current_price": 100.0, "market_value": 5_000.0, "side": "long", "unrealized_pl": 12.0},
        ("BBB", "paper"): {"current_price": 100.0, "market_value": -2_000.0, "side": "short", "unrealized_pl": -3.0},
        # the SAME ticker held in the paper book too: a no-arg/paper read of AAA must not leak in
        ("AAA", "paper"): {"current_price": 50.0, "market_value": 999_999.0, "side": "long", "unrealized_pl": 1.0},
    })
    out, legacy = _call_trades_summary_endpoint(
        [row("AAA", "live", 95.0), row("BBB", "paper", 105.0)],
        get_account=get_account, get_position=get_position)
    live = out["live"]
    by = {p["ticker"]: p for p in live["open_positions"]}
    assert by["AAA"]["position_pct_of_equity"] == pytest.approx(10.0)   # 5000 / LIVE 50000
    assert by["AAA"]["stop_pct"] == pytest.approx(5.0) and by["AAA"]["side"] == "long"
    assert by["BBB"]["position_pct_of_equity"] == pytest.approx(2.0)    # |-2000| / PAPER 100000
    assert by["BBB"]["stop_pct"] == pytest.approx(5.0) and by["BBB"]["side"] == "short"   # stop above
    assert by["AAA"]["unrealized_pnl"] == 12.0 and by["AAA"]["market_value"] == 5_000.0
    assert live["equity_by_mode"] == {"live": 50_000.0, "paper": 100_000.0}
    assert live["equity"] == 777.0 and legacy["called"] == 1             # the legacy field's meaning is unchanged
    assert sorted(c.kwargs["account_mode"] for c in get_account.await_args_list) == ["live", "paper"]


def test_the_summary_endpoint_gives_none_not_a_wrong_number_when_a_read_fails():
    get_account = AsyncMock(side_effect=RuntimeError("down"))
    get_position = AsyncMock(return_value=None)
    row = {"id": 1, "ticker": "AAA", "alert_date": date(2026, 10, 20), "ep_score": 70,
           "entry_price": 100.0, "remaining_shares": 50, "stop_price": 95.0, "hard_stop": 95.0,
           "hold_days": 1, "position_size": 5000, "risk_dollars": 250, "total_pnl": 0,
           "partial_taken": False, "breakeven_active": False, "catalyst_quality": "strong",
           "account_mode": "live"}
    out, _ = _call_trades_summary_endpoint([row], get_account=get_account, get_position=get_position)
    p = out["live"]["open_positions"][0]
    assert p["position_pct_of_equity"] is None and p["stop_pct"] is None and p["side"] is None
    assert p["current_price"] is None and p["unrealized_pnl"] == 0 and p["market_value"] == 0


# ═══ 4. one skip line per (ticker, reason class) per ET day ════════════════════════════════
#
# ⚠ THE PRODUCTION CALL SHAPE (what these tests model — review of 2026-10-21): the per-ticker
# existence check at the top of `_process_alert` returns None for ANY row today, skipped rows
# included, and every skip path writes one. So a LATER, non-overlapping evaluation never reaches
# the digest for a ticker that was already skipped; duplicates come only from evaluations that
# OVERLAP (both pass the check before either has written its row — the SPCX case). The monitor
# below therefore makes a row visible to the check only AFTER the evaluation(s) that wrote it
# finish, and the process-level dedupe tests drive OVERLAPPING calls (asyncio.gather). The pure
# claim bookkeeping (reason class, ET day, new-ticker-only, restart) is tested on the helper.

_TODAY = date(2026, 10, 21)


def _mk_alert(ticker, today):
    return {"ticker": ticker, "alert_date": today, "gap_pct": 12.0, "rel_volume": 6.0,
            "ep_score": 75, "score_tier": "HIGH", "catalyst": "earnings",
            "catalyst_quality": "strong", "vol_percentile": 92}


class _Monitor:
    """process_new_alerts_live with submit_trade_entry stubbed to a canned result, and the
    per-ticker existence check modelled on the real rule (a row written by an evaluation is visible
    to the NEXT evaluation, not to one already past the check)."""

    def __init__(self, monkeypatch):
        self.monkeypatch = monkeypatch
        self.canned: dict = {}               # ticker -> one result dict, or a list consumed per evaluation
        self.sent: list[str] = []
        self.submit_calls: list[str] = []
        self.send_ok = True
        self.send_script: list[bool] = []    # per-send outcomes, consumed in order (then send_ok)
        self.send_delay = False
        self.today = _TODAY
        self.rows: set = set()               # (ticker, day) rows the existence check can see
        self._written: set = set()
        pool, self.conn = make_mock_pool()
        self.conn.fetchrow = AsyncMock(return_value=None)

        async def _exists(sql, ticker, day, *rest):
            return (ticker, day) in self.rows

        self.conn.fetchval = AsyncMock(side_effect=_exists)
        monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=pool))
        monkeypatch.setattr(lt, "LIVE_TRADING_ENABLED", True)
        import agents.market_intelligence.db as db
        monkeypatch.setattr(db, "log_audit_event", AsyncMock())
        monkeypatch.setattr(lt, "check_filters", AsyncMock(return_value=(True, None)))
        monkeypatch.setattr(lt, "compute_atr_14", AsyncMock(return_value=(1.0, 2.0)))

        async def _fake_submit(*, alert_context, **_kw):
            t = alert_context["ticker"]
            self.submit_calls.append(t)
            c = self.canned[t]
            res = c.pop(0) if isinstance(c, list) else c
            self._written.add((t, alert_context["alert_date"]))   # the pipeline's skip/trade row
            return {"ticker": t, **res}

        async def _capture(msg, *a, **k):
            if self.send_delay:
                await asyncio.sleep(0)
            ok = self.send_script.pop(0) if self.send_script else self.send_ok
            if not ok:
                return False
            self.sent.append(msg)
            return True

        monkeypatch.setattr(lt, "submit_trade_entry", _fake_submit)
        monkeypatch.setattr(lt, "send_telegram_message", _capture)

    def _prime(self, canned, day):
        if canned is not None:
            self.canned = canned
        self.conn.fetch = AsyncMock(return_value=[_mk_alert(t, day) for t in self.canned])

    def _commit_rows(self):
        self.rows |= self._written

    async def run(self, canned=None, *, today=None):
        """ONE evaluation; its rows are visible to the next one."""
        day = today or self.today
        self._prime(canned, day)
        out = await lt.process_new_alerts_live(today=day)
        self._commit_rows()
        return out

    async def run_overlapping(self, canned=None, *, n=2, today=None):
        """n evaluations IN FLIGHT TOGETHER (bar stream + 09:31 cron): all pass the existence
        check before any row is visible — the SPCX 2026-10-21 shape."""
        day = today or self.today
        self._prime(canned, day)
        out = await asyncio.gather(*(lt.process_new_alerts_live(today=day) for _ in range(n)))
        self._commit_rows()
        return out

    def digests(self):
        return [m for m in self.sent if "ORB skips" in m]


_SPCX_SKIP = {"SPCX": {"action": lt.ACTION_SKIPPED, "reason": "setup:gap_below_floor: gap 8.1% < 9.0%"}}


def _spcx(reason):
    return {"action": lt.ACTION_SKIPPED, "reason": reason}


@pytest.mark.asyncio
async def test_two_overlapping_evaluations_with_the_same_reason_send_one_line(monkeypatch):
    """The 2026-10-21 SPCX case: the bar stream and the 09:31 cron both evaluate and both skip."""
    m = _Monitor(monkeypatch)
    m.send_delay = True                       # the first send is still in flight when the second arrives
    await m.run_overlapping(_SPCX_SKIP)
    assert len(m.digests()) == 1, m.sent
    assert "SPCX" in m.digests()[0] and ", 1)" in m.digests()[0]


@pytest.mark.asyncio
async def test_the_second_overlapping_evaluation_still_runs_and_returns_the_same_results(monkeypatch):
    """Message-only: BOTH overlapping evaluations run the entry pipeline and return identical
    action results; only the digest line is held back."""
    m = _Monitor(monkeypatch)
    first, second = await m.run_overlapping(_SPCX_SKIP)
    assert m.submit_calls == ["SPCX", "SPCX"], "the second evaluation must still run the entry pipeline"
    assert first == second == [{"ticker": "SPCX", **_SPCX_SKIP["SPCX"]}]
    assert len(m.digests()) == 1


@pytest.mark.asyncio
async def test_a_recovered_gap_still_enters_on_the_overlapping_evaluation(monkeypatch):
    """One evaluation sees the gap below the floor, the other sees it recovered and ENTERS: the
    entry is untouched, and only the skip line goes out (once)."""
    m = _Monitor(monkeypatch)
    skipped, entered = await m.run_overlapping(
        {"SPCX": [_spcx("setup:gap_below_floor: gap 8.1% < 9.0%"),
                  {"action": lt.ACTION_AUTO_ENTERED, "reason": None}]})
    assert skipped[0]["action"] == lt.ACTION_SKIPPED and entered[0]["action"] == lt.ACTION_AUTO_ENTERED
    assert len(m.digests()) == 1


@pytest.mark.asyncio
async def test_a_later_sequential_evaluation_never_reaches_the_digest_for_a_ticker_with_a_row(monkeypatch):
    """Pins the truth the earlier tests hid: once the first evaluation has written today's skip
    row, a later call returns None for that ticker at the existence check — it does not re-run
    the pipeline and cannot add a digest line (so a 'recovered gap enters on a later call' is only
    possible while the calls overlap)."""
    m = _Monitor(monkeypatch)
    await m.run(_SPCX_SKIP)
    second = await m.run()
    assert second == [] and m.submit_calls == ["SPCX"]
    assert len(m.digests()) == 1


@pytest.mark.asyncio
async def test_a_changed_detail_on_the_same_reason_does_not_resend(monkeypatch):
    m = _Monitor(monkeypatch)
    await m.run_overlapping({"SPCX": [_spcx("setup:stop_too_wide: ORB $1.24 vs $0.83"),
                                      _spcx("setup:stop_too_wide: ORB $1.31 vs $0.85")]})
    assert len(m.digests()) == 1


@pytest.mark.asyncio
async def test_a_changed_reason_sends_a_second_line(monkeypatch):
    m = _Monitor(monkeypatch)
    await m.run_overlapping({"SPCX": [_spcx("filter:atr_too_high"),
                                      _spcx("block:max_positions: 5/5 (mode=live)")]})
    assert len(m.digests()) == 2
    texts = " ".join(m.digests())
    assert "Volatility too high" in texts and "Max open positions" in texts


@pytest.mark.asyncio
async def test_the_next_et_day_sends_the_line_again(monkeypatch):
    m = _Monitor(monkeypatch)
    await m.run_overlapping(_SPCX_SKIP)
    assert len(m.digests()) == 1
    nxt = _TODAY + timedelta(days=1)
    await m.run_overlapping(_SPCX_SKIP, today=nxt)
    assert len(m.digests()) == 2
    await m.run_overlapping(_SPCX_SKIP, today=nxt)        # same day again: held back
    assert len(m.digests()) == 2
    assert all(k[0] == nxt for k in lt._skip_digest_sent), "yesterday's keys must be dropped"


@pytest.mark.asyncio
async def test_a_failed_send_is_retried_by_the_overlapping_evaluation_waiting_on_it(monkeypatch):
    """REVIEW FINDING (major): evaluation A claims the key and its send FAILS while B — overlapping,
    having passed over A's claim — is already at the digest. Before the lock, A released the key and
    NOBODY sent the line. Now B waits for A's result, finds the key released, and sends it:
    exactly one digest is delivered."""
    m = _Monitor(monkeypatch)
    m.send_delay = True
    m.send_script = [False, True]                          # A's send fails, B's succeeds
    await m.run_overlapping(_SPCX_SKIP)
    assert len(m.digests()) == 1, m.sent
    assert "SPCX" in m.digests()[0]
    assert len(lt._skip_digest_sent) == 1, "the delivered line holds its claim for the day"


@pytest.mark.asyncio
async def test_when_every_send_fails_the_claim_is_released_and_nothing_is_swallowed(monkeypatch):
    m = _Monitor(monkeypatch)
    m.send_delay = True
    m.send_ok = False
    await m.run_overlapping(_SPCX_SKIP)
    assert m.digests() == [] and lt._skip_digest_sent == set()


@pytest.mark.asyncio
async def test_a_failed_send_with_nothing_overlapping_is_not_retried_as_before(monkeypatch):
    """The honest limit (docs/architecture/entry_pipeline.md): the release only helps an
    overlapping evaluation. A LATER call is stopped by today's skip row, so a send that failed with
    no overlap is not re-sent — exactly the pre-#706 behaviour (the failure is on telegram_send_failed)."""
    m = _Monitor(monkeypatch)
    m.send_ok = False
    await m.run(_SPCX_SKIP)
    m.send_ok = True
    await m.run()
    assert m.digests() == [] and m.submit_calls == ["SPCX"]


@pytest.mark.asyncio
async def test_an_overlapping_pair_with_two_tickers_sends_each_once(monkeypatch):
    m = _Monitor(monkeypatch)
    m.send_delay = True
    await m.run_overlapping({**_SPCX_SKIP, "NEWB": _spcx("filter:adv_too_low")})
    body = "\n".join(m.digests())
    assert body.count("SPCX") == 1 and body.count("NEWB") == 1 and len(m.digests()) == 1


@pytest.mark.asyncio
async def test_window_duplicates_stay_out_of_the_digest_as_before(monkeypatch):
    m = _Monitor(monkeypatch)
    await m.run({"DUPE": {"action": lt.ACTION_SKIPPED, "reason": "window:duplicate"}})
    assert m.digests() == []
    assert lt._skip_digest_sent == set(), "a duplicate must not claim a key"


@pytest.mark.asyncio
async def test_a_failure_inside_the_digest_never_stops_the_results_reaching_the_caller(monkeypatch):
    """The digest runs after the orders were submitted: whatever it raises, the caller still gets
    the action results (message-only means it can never take the order path down with it)."""
    m = _Monitor(monkeypatch)

    def _boom(*a, **k):
        raise RuntimeError("claim exploded")

    monkeypatch.setattr(lt, "_claim_unsent_skips", _boom)
    out = await m.run(_SPCX_SKIP)
    assert out == [{"ticker": "SPCX", **_SPCX_SKIP["SPCX"]}]


def test_claim_is_per_ticker_and_reason_class_and_only_the_new_ones_are_fresh():
    def res(t, reason):
        return {"ticker": t, "action": lt.ACTION_SKIPPED, "reason": reason}

    fresh, claimed = lt._claim_unsent_skips([res("SPCX", "filter:atr_too_high")], _TODAY)
    assert [r["ticker"] for r in fresh] == ["SPCX"] and len(claimed) == 1
    fresh, _ = lt._claim_unsent_skips(
        [res("SPCX", "filter:atr_too_high: 9 vs 5"), res("NEWB", "filter:adv_too_low")], _TODAY)
    assert [r["ticker"] for r in fresh] == ["NEWB"]           # the SPCX line was already announced
    fresh, _ = lt._claim_unsent_skips([res("SPCX", "block:max_positions")], _TODAY)
    assert [r["ticker"] for r in fresh] == ["SPCX"]           # a changed reason class is new


def test_a_restart_forgets_the_set_so_a_line_may_repeat_once():
    """The set is process memory. After a restart the day's keys are gone and the same line can be
    claimed again — the accepted failure direction (a repeat, never a lost first line). In
    production this needs a skip path that wrote no row: the existence check stops every other
    re-evaluation."""
    r = {"ticker": "SPCX", "action": lt.ACTION_SKIPPED, "reason": "filter:atr_too_high"}
    assert lt._claim_unsent_skips([r], _TODAY)[0] == [r]
    assert lt._claim_unsent_skips([r], _TODAY)[0] == []
    lt._reset_skip_digest_dedupe()                           # what a restart does
    assert lt._claim_unsent_skips([r], _TODAY)[0] == [r]


def test_skip_reason_class_is_the_vocabulary_aggregation_key():
    c = lt._skip_reason_class
    assert c("setup:stop_too_wide: ORB $1.24 vs 1.5x ATR $0.83") == "setup:stop_too_wide"
    assert c("filter:atr_too_high") == "filter:atr_too_high"
    assert c("block:max_positions: 5/5 (mode=live)") == "block:max_positions"
    assert c("free text no colon") == "free text no colon"
    assert c(None) == c("") == c("  ") == "no_reason"
