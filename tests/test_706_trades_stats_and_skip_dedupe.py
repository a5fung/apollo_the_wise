"""#706 — /trades position stats + one ORB skip line per (ticker, reason) per ET day.

His 2026-10-21 asks (display only; no order path, no sizing, no entry decision changes):
  * OPEN position  -> size as a % of the account's equity, and the stop % (what we lose, as a %
                      of the CURRENT price, if the stop is hit from here), side-aware.
  * CLOSED position-> % win/loss beside the R and the $ P&L.
  * the SPCX skip line arrived twice, 10 s apart (bar stream + 09:31 cron both run the monitor).

The numbers are fixtures, not real positions.
"""
from __future__ import annotations

import asyncio
import json
import math
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
    """Brief: long = (current - stop) / current. Price 100, stop 95 -> lose 5% -> -5.0."""
    assert ts.stop_move_pct("long", 100.0, 95.0) == pytest.approx(-5.0)
    assert (100.0 - 95.0) / 100.0 * 100 == pytest.approx(-ts.stop_move_pct("long", 100.0, 95.0))
    # the % is of the CURRENT price, not of entry: price ran to 120, stop still 95 -> -20.83%
    assert ts.stop_move_pct("long", 120.0, 95.0) == pytest.approx(-25 / 120 * 100)


def test_short_stop_sits_above_the_price_and_still_reads_as_a_loss():
    """Brief: a short's stop sits ABOVE the price. Price 100, stop 105 -> a 5% loss -> -5.0.
    The long formula on the same numbers would read +5.0 — the WOULD-FAIL-IF."""
    assert ts.stop_move_pct("short", 100.0, 105.0) == pytest.approx(-5.0)
    assert ts.stop_move_pct("long", 100.0, 105.0) == pytest.approx(+5.0)   # the wrong-side read


def test_a_stop_on_the_profit_side_of_the_price_reads_positive_not_hidden():
    assert ts.stop_move_pct("long", 100.0, 101.0) == pytest.approx(1.0)
    assert ts.stop_move_pct("short", 100.0, 99.0) == pytest.approx(1.0)


@pytest.mark.parametrize("side,cur,stop", [
    (None, 100, 95), ("flat", 100, 95), ("", 100, 95),   # unknown side -> no number
    ("long", None, 95), ("long", 100, None),             # a missing price
    ("long", 0, 95), ("long", 100, 0), ("long", -3, 95), ("long", 100, -1),
    ("long", float("nan"), 95),
])
def test_stop_pct_is_none_on_unknown_side_or_missing_price(side, cur, stop):
    assert ts.stop_move_pct(side, cur, stop) is None


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
    assert s == {"side": "long", "position_pct": pytest.approx(10.0), "stop_pct": pytest.approx(-5.0)}
    none = ts.open_position_stats(side=None, market_value=None, current_price=None,
                                  stop_price=95.0, equity=50_000)
    assert none == {"side": None, "position_pct": None, "stop_pct": None}


# ═══ 2. the render ═════════════════════════════════════════════════════════════════════════

def test_size_and_stop_lines_render_plain_text_with_no_table():
    stats = {"position_pct": 8.14, "stop_pct": -5.07}
    lines = ts.fmt_size_stop_lines(shares=19, market_value=4_210, stop_price=212.4, stats=stats)
    assert lines == ["      19 sh · $4,210 · 8.1% of equity",
                     "      Stop $212.40 · -5.1% if hit"]
    assert "|" not in "".join(lines)         # Telegram cannot render pipe tables


def test_missing_numbers_render_a_dash_never_a_zero():
    lines = ts.fmt_size_stop_lines(shares=19, market_value=0, stop_price=None,
                                   stats={"position_pct": None, "stop_pct": None})
    assert lines[0].endswith("— of equity") and "0.0%" not in lines[0]
    assert lines[1] == "      Stop ? · — if hit"


def test_the_lines_survive_the_telegram_html_conversion():
    from shared.telegram_format import md_to_html
    stats = {"position_pct": 8.14, "stop_pct": -5.07}
    body = "\n".join(["  🟢 *ABCD* · 2d"] + ts.fmt_size_stop_lines(
        shares=19, market_value=4_210, stop_price=212.4, stats=stats))
    html = md_to_html(body)
    assert "8.1% of equity" in html and "-5.1% if hit" in html and "<b>ABCD</b>" in html


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
    assert "Stop $95.00 · -5.0% if hit" in text
    # ONE read, from the LIVE account — the no-arg form resolves to the paper account
    get_account.assert_awaited_once_with(account_mode="live")


def test_the_summary_is_side_aware_for_a_short():
    text, _ = _render_summary(
        [_open_row("SHRT", 100.0, 105.0, 50)],
        {"SHRT": {"current_price": 100.0, "unrealized_pl": 0.0, "market_value": -5_000.0, "side": "short"}},
        account={"equity": 50_000.0},
    )
    assert "10.0% of equity" in text                   # |negative market value|
    assert "Stop $105.00 · -5.0% if hit" in text       # a loss, though the stop sits ABOVE the price
    assert "+5.0% if hit" not in text


def test_the_summary_shows_dashes_when_the_account_read_fails():
    text, _ = _render_summary(
        [_open_row("ABCD", 100.0, 95.0, 50)],
        {"ABCD": {"current_price": 100.0, "unrealized_pl": 0.0, "market_value": 5_000.0, "side": "long"}},
        account_raises=True,
    )
    assert "equity —" in text and "— of equity" in text
    assert "Stop $95.00 · -5.0% if hit" in text        # the stop % needs no equity


def test_a_position_the_broker_did_not_return_gets_dashes_not_zeros():
    text, _ = _render_summary([_open_row("GONE", 100.0, 95.0, 50)], {}, account={"equity": 50_000.0})
    assert "— of equity" in text and "Stop $95.00 · — if hit" in text
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


# ═══ 4. one skip line per (ticker, reason class) per ET day ════════════════════════════════

_TODAY = date(2026, 10, 21)


def _mk_alert(ticker, today):
    return {"ticker": ticker, "alert_date": today, "gap_pct": 12.0, "rel_volume": 6.0,
            "ep_score": 75, "score_tier": "HIGH", "catalyst": "earnings",
            "catalyst_quality": "strong", "vol_percentile": 92}


class _Monitor:
    """process_new_alerts_live with submit_trade_entry stubbed to a canned per-ticker result."""

    def __init__(self, monkeypatch):
        self.monkeypatch = monkeypatch
        self.canned: dict[str, dict] = {}
        self.sent: list[str] = []
        self.submit_calls: list[str] = []
        self.send_ok = True
        self.send_delay = False
        self.today = _TODAY
        pool, self.conn = make_mock_pool()
        self.conn.fetchrow = AsyncMock(return_value=None)
        self.conn.fetchval = AsyncMock(return_value=False)
        monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=pool))
        monkeypatch.setattr(lt, "LIVE_TRADING_ENABLED", True)
        import agents.market_intelligence.db as db
        monkeypatch.setattr(db, "log_audit_event", AsyncMock())
        monkeypatch.setattr(lt, "check_filters", AsyncMock(return_value=(True, None)))
        monkeypatch.setattr(lt, "compute_atr_14", AsyncMock(return_value=(1.0, 2.0)))

        async def _fake_submit(*, alert_context, **_kw):
            t = alert_context["ticker"]
            self.submit_calls.append(t)
            return {"ticker": t, **self.canned[t]}

        async def _capture(msg, *a, **k):
            if self.send_delay:
                await asyncio.sleep(0)
            if not self.send_ok:
                return False
            self.sent.append(msg)
            return True

        monkeypatch.setattr(lt, "submit_trade_entry", _fake_submit)
        monkeypatch.setattr(lt, "send_telegram_message", _capture)

    async def run(self, canned=None, *, today=None):
        if canned is not None:
            self.canned = canned
        day = today or self.today
        self.conn.fetch = AsyncMock(return_value=[_mk_alert(t, day) for t in self.canned])
        return await lt.process_new_alerts_live(today=day)

    def digests(self):
        return [m for m in self.sent if "ORB skips" in m]


_SPCX_SKIP = {"SPCX": {"action": lt.ACTION_SKIPPED, "reason": "setup:gap_below_floor: gap 8.1% < 9.0%"}}


@pytest.mark.asyncio
async def test_the_same_reason_twice_sends_one_line(monkeypatch):
    m = _Monitor(monkeypatch)
    await m.run(_SPCX_SKIP)            # bar stream
    await m.run()                      # 09:31 cron fallback, 10 s later
    assert len(m.digests()) == 1, m.sent
    assert "SPCX" in m.digests()[0] and ", 1)" in m.digests()[0]


@pytest.mark.asyncio
async def test_the_second_evaluation_still_runs_and_returns_the_same_results(monkeypatch):
    """Message-only: the skipped ticker is still evaluated on every call (a recovered gap can still
    enter) and the action results are identical with or without the held-back line."""
    m = _Monitor(monkeypatch)
    first = await m.run(_SPCX_SKIP)
    second = await m.run()
    assert m.submit_calls == ["SPCX", "SPCX"], "the second evaluation must still run the entry pipeline"
    assert first == second == [{"ticker": "SPCX", **_SPCX_SKIP["SPCX"]}]
    assert len(m.digests()) == 1


@pytest.mark.asyncio
async def test_a_recovered_gap_enters_on_the_second_evaluation(monkeypatch):
    m = _Monitor(monkeypatch)
    await m.run(_SPCX_SKIP)
    results = await m.run({"SPCX": {"action": lt.ACTION_AUTO_ENTERED, "reason": None}})
    assert results[0]["action"] == lt.ACTION_AUTO_ENTERED
    assert len(m.digests()) == 1                       # no skip line for an entry, and none re-sent


@pytest.mark.asyncio
async def test_a_changed_detail_on_the_same_reason_does_not_resend(monkeypatch):
    m = _Monitor(monkeypatch)
    await m.run({"SPCX": {"action": lt.ACTION_SKIPPED, "reason": "setup:stop_too_wide: ORB $1.24 vs $0.83"}})
    await m.run({"SPCX": {"action": lt.ACTION_SKIPPED, "reason": "setup:stop_too_wide: ORB $1.31 vs $0.85"}})
    assert len(m.digests()) == 1


@pytest.mark.asyncio
async def test_a_changed_reason_sends_a_second_line(monkeypatch):
    m = _Monitor(monkeypatch)
    await m.run({"SPCX": {"action": lt.ACTION_SKIPPED, "reason": "filter:atr_too_high"}})
    await m.run({"SPCX": {"action": lt.ACTION_SKIPPED, "reason": "block:max_positions: 5/5 (mode=live)"}})
    assert len(m.digests()) == 2
    assert "Volatility too high" in m.digests()[0] and "Max open positions" in m.digests()[1]


@pytest.mark.asyncio
async def test_the_next_et_day_sends_the_line_again(monkeypatch):
    m = _Monitor(monkeypatch)
    await m.run(_SPCX_SKIP)
    await m.run()
    assert len(m.digests()) == 1
    await m.run(today=_TODAY + timedelta(days=1))
    assert len(m.digests()) == 2
    await m.run(today=_TODAY + timedelta(days=1))
    assert len(m.digests()) == 2
    assert all(k[0] == _TODAY + timedelta(days=1) for k in lt._skip_digest_sent), "yesterday's keys must be dropped"


@pytest.mark.asyncio
async def test_only_the_new_ticker_is_listed_in_a_later_digest(monkeypatch):
    m = _Monitor(monkeypatch)
    await m.run(_SPCX_SKIP)
    await m.run({**_SPCX_SKIP, "NEWB": {"action": lt.ACTION_SKIPPED, "reason": "filter:adv_too_low"}})
    assert len(m.digests()) == 2
    assert "NEWB" in m.digests()[1] and "SPCX" not in m.digests()[1] and ", 1)" in m.digests()[1]


@pytest.mark.asyncio
async def test_two_overlapping_evaluations_send_one_line(monkeypatch):
    """The bar stream and the cron can overlap: the claim is taken before the send's first await."""
    m = _Monitor(monkeypatch)
    m.send_delay = True
    m.canned = _SPCX_SKIP
    m.conn.fetch = AsyncMock(return_value=[_mk_alert("SPCX", _TODAY)])
    await asyncio.gather(lt.process_new_alerts_live(today=_TODAY),
                         lt.process_new_alerts_live(today=_TODAY))
    assert len(m.digests()) == 1, m.sent


@pytest.mark.asyncio
async def test_a_failed_send_is_retried_by_the_next_evaluation(monkeypatch):
    m = _Monitor(monkeypatch)
    m.send_ok = False
    await m.run(_SPCX_SKIP)
    assert m.digests() == []
    m.send_ok = True
    await m.run()
    assert len(m.digests()) == 1, "a line that never went out must not be swallowed for the day"


@pytest.mark.asyncio
async def test_a_container_restart_may_repeat_a_line_once(monkeypatch):
    """The set is process memory. After a restart the day's already-sent lines can show again —
    the accepted failure direction (a repeat, never a lost first line)."""
    m = _Monitor(monkeypatch)
    await m.run(_SPCX_SKIP)
    lt._reset_skip_digest_dedupe()           # what a restart does
    await m.run()
    assert len(m.digests()) == 2


@pytest.mark.asyncio
async def test_window_duplicates_stay_out_of_the_digest_as_before(monkeypatch):
    m = _Monitor(monkeypatch)
    await m.run({"DUPE": {"action": lt.ACTION_SKIPPED, "reason": "window:duplicate"}})
    assert m.digests() == []
    assert lt._skip_digest_sent == set(), "a duplicate must not claim a key"


def test_skip_reason_class_is_the_vocabulary_aggregation_key():
    c = lt._skip_reason_class
    assert c("setup:stop_too_wide: ORB $1.24 vs 1.5x ATR $0.83") == "setup:stop_too_wide"
    assert c("filter:atr_too_high") == "filter:atr_too_high"
    assert c("block:max_positions: 5/5 (mode=live)") == "block:max_positions"
    assert c("free text no colon") == "free text no colon"
    assert c(None) == c("") == c("  ") == "no_reason"
