"""2026-11-10 (ZYME, a breakout v1 PAPER position): the naked-position L1 paged his MAIN chat saying
"real $ exposure". Four defects, each pinned here:

1. the broker read asked the DEFAULT account, so a paper position was judged on the live book's orders;
2. the text said "real $" and carried no paper tag, so `send_telegram_message` (#699) sent it to the
   main chat instead of the paper group;
3. a position whose every share is held by a QUEUED SALE (the #687 ruling-(3) market sale placed after
   the close) has no stop by design and was called naked;
4. the once-a-day dedupe was shared by both books, so that paper page spent the day's only slot and a
   LIVE naked position later the same day would never have paged.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence import system_audit
from agents.market_intelligence.audit_invariants import INV_NAKED_POSITION, classify_naked_positions
from agents.market_intelligence.broker import alpaca_client
from agents.market_intelligence.constants import mode_prefix


def _row(ticker, mode, held=565):
    return {"id": 1, "ticker": ticker, "alert_date": "2026-11-10", "status": "filled",
            "stop_order_id": None, "filled_at": None, "account_mode": mode, "remaining_shares": held}


@pytest.mark.asyncio
async def test_the_broker_read_asks_the_rows_own_account():
    seen = []

    async def oo(ticker=None, account_mode=None, raise_on_error=False):
        seen.append((ticker, account_mode))
        return []
    with patch.object(alpaca_client, "get_open_orders", new=oo):
        await classify_naked_positions({"offending_rows": [_row("ZYME", "paper"), _row("AAPL", "live"),
                                                           _row("OLD", None)]})
    assert seen == [("ZYME", "paper"), ("AAPL", "live"), ("OLD", "live")]


@pytest.mark.asyncio
async def test_a_queued_sale_for_every_share_is_covered_not_naked():
    sale = [{"side": "sell", "type": "market", "qty": 565.0, "stop_price": None}]
    with patch.object(alpaca_client, "get_open_orders", new=AsyncMock(return_value=sale)):
        out = await classify_naked_positions({"offending_rows": [_row("ZYME", "paper")]})
    assert [r["ticker"] for r in out["covered_by_exit"]] == ["ZYME"] and out["real_naked"] == []
    part = [{"side": "sell", "type": "market", "qty": 100.0, "stop_price": None}]
    with patch.object(alpaca_client, "get_open_orders", new=AsyncMock(return_value=part)):
        out = await classify_naked_positions({"offending_rows": [_row("ZYME", "paper")]})
    assert [r["ticker"] for r in out["real_naked"]] == ["ZYME"]          # 465 shares still bare
    limit = [{"side": "sell", "type": "limit", "qty": 565.0, "stop_price": None, "limit_price": 40.0}]
    with patch.object(alpaca_client, "get_open_orders", new=AsyncMock(return_value=limit)):
        out = await classify_naked_positions({"offending_rows": [_row("AAPL", "live")]})
    assert [r["ticker"] for r in out["real_naked"]] == ["AAPL"]          # a profit-take limit is not cover


def test_the_paper_form_is_tagged_and_never_says_real_money():
    body = {"real_naked": [_row("ZYME", "paper")], "db_drift": [], "drill_sql": "x"}
    paper = system_audit._format_naked_position_alert(body, account_mode="paper")
    assert paper.startswith(mode_prefix("paper")) and "real $" not in paper and "no real money" in paper
    live = system_audit._format_naked_position_alert({**body, "real_naked": [_row("AAPL", "live")]})
    assert "real $ exposure" in live and not live.startswith(mode_prefix("paper"))


async def _run_emit(rows, orders_by_ticker, paged_already=(), rows_today=0):
    sent, written = [], []

    async def oo(ticker=None, account_mode=None, raise_on_error=False):
        return orders_by_ticker.get(ticker, [])

    async def log(event, summary=None, detail=None, **kw):
        written.append(json.loads(detail))
    with patch.object(alpaca_client, "get_open_orders", new=oo), \
         patch.object(system_audit, "count_today_anomalies", new=AsyncMock(return_value=rows_today)), \
         patch.object(system_audit, "_naked_books_paged_today", new=AsyncMock(return_value=set(paged_already))), \
         patch.object(system_audit, "log_audit_event", new=log), \
         patch("agents.market_intelligence.briefing.send_telegram_message",
               new=AsyncMock(side_effect=lambda text, **kw: sent.append(text) or True)):
        await system_audit._emit_l1(INV_NAKED_POSITION, {"offending_rows": rows, "drill_sql": "x"})
    return sent, written


@pytest.mark.asyncio
async def test_a_paper_row_pages_paper_tagged_and_a_live_row_its_own_message():
    sent, written = await _run_emit([_row("ZYME", "paper"), _row("AAPL", "live")], {})
    assert len(sent) == 2
    assert any(t.startswith(mode_prefix("paper")) and "ZYME" in t and "real $" not in t for t in sent)
    assert any("AAPL" in t and "real $ exposure" in t and not t.startswith(mode_prefix("paper")) for t in sent)
    assert written[0]["paged_books"] == ["live", "paper"]


@pytest.mark.asyncio
async def test_a_paper_page_earlier_today_does_not_silence_a_live_naked_position():
    sent, written = await _run_emit([_row("AAPL", "live")], {}, paged_already={"paper"}, rows_today=1)
    assert len(sent) == 1 and "AAPL" in sent[0] and written[0]["paged_books"] == ["live"]
    # and the same book is still deduped once a day
    sent, written = await _run_emit([_row("AAPL", "live")], {}, paged_already={"live"}, rows_today=1)
    assert sent == [] and written == []


@pytest.mark.asyncio
async def test_a_position_held_by_a_queued_sale_pages_nobody_but_is_recorded():
    sale = {"ZYME": [{"side": "sell", "type": "market", "qty": 565.0, "stop_price": None}]}
    sent, written = await _run_emit([_row("ZYME", "paper")], sale)
    assert sent == []
    assert [r["ticker"] for r in written[0]["covered_by_exit"]] == ["ZYME"] and written[0]["paged_books"] == []
