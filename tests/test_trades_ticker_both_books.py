"""#624 display gap — `/trades TICKER` must show the ticker's rows from BOTH books, tagged.

THE GAP (10-12 graduation-checklist review): the low-cap paper lane (`magna53_smallcap`, paper since
10-11) writes its positions to `mi_live_trades` with `account_mode='paper'`. `_handle_trades_query`
filtered that table to `account_mode='live'` unconditionally, so `/trades WETO` for a paper-lane
position answered "No paper trades found".

THE FIX, and what stays exactly as it was:
  - a TICKER query drops the book filter FOR THAT TICKER (an explicit `IN ('live', 'paper')`, not
    an absent condition) and tags every row with the existing mode-prefix (`mode_prefix`);
  - the no-ticker LIST and the TOTALS footer stay live-only and byte-identical to before. The
    golden below is the pre-change output of the same fixture, captured from the unmodified handler.
"""
import asyncio
import datetime as dt
import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.market_intelligence.constants import is_paper_message, mode_prefix  # noqa: E402
from tests.test_partial_visible_in_trades_549 import _extract  # noqa: E402

LIVE_TAG = mode_prefix("live")
PAPER_TAG = mode_prefix("paper")

# conftest STUBS `backtester.tracker` (it drags in heavy deps the suite deliberately mocks) and the
# module cannot be exec'd standalone, so a plain import hands the handler a MagicMock and every
# assertion would pass without one line of the real row formatter running. Same technique as
# tests/test_partial_visible_in_trades_549.py (whose `_extract` this reuses): compile just the
# functions the handler imports, from the real source, so this cannot drift from what ships.
_TRACKER_FNS = ("parse_json_list", "format_trade_attempts", "format_trade_attempts_live",
                "_attempt_count")


def _real_formatter_module() -> types.ModuleType:
    from shared.dates import et_hhmm
    ns: dict = {"json": json, "datetime": datetime, "timezone": timezone, "et_hhmm": et_hhmm}
    for fn in _TRACKER_FNS:
        exec(_extract(fn), ns)  # noqa: S102 - real source, not a fixture
    mod = types.ModuleType("agents.market_intelligence.backtester.tracker")
    for fn in _TRACKER_FNS:
        setattr(mod, fn, ns[fn])
    return mod


def _row(ticker, account_mode, *, status, alert_date, pnl, hold, exits, price, stop,
         shares=100, score=80.0, gap=22.5):
    return {
        "ticker": ticker, "account_mode": account_mode, "alert_date": alert_date,
        "ep_score": score, "gap_pct": gap, "catalyst_quality": "strong", "regime": "bull",
        "status": status, "skip_reason": None, "entry_price": price, "orb_high": price,
        "orb_low": price - 1.0, "stop_price": stop, "total_pnl": pnl, "hold_days": hold,
        "exits": exits, "entries": None, "entry_attempt": 1, "entry_shares": shares,
    }


_STOP_EXIT = [{"attempt": 1, "time": "2026-10-08T14:20:00+00:00", "reason": "stop_hit",
               "shares": 100, "price": 8.0, "pnl": -200.0}]

# Newest first, as the query's ORDER BY returns them.
FIXTURE_ROWS = [
    _row("ZZPP", "paper", status="filled", alert_date=dt.date(2026, 10, 14), pnl=0.0, hold=1,
         exits=[], price=5.0, stop=4.0, shares=200, score=70.0, gap=31.0),
    _row("ZZBO", "paper", status="filled", alert_date=dt.date(2026, 10, 13), pnl=0.0, hold=2,
         exits=[], price=7.0, stop=6.0, shares=150, score=66.0, gap=19.0),
    _row("ZZLV", "live", status="closed", alert_date=dt.date(2026, 10, 9), pnl=-200.0, hold=1,
         exits=_STOP_EXIT, price=10.0, stop=8.0),
    _row("ZZBO", "live", status="closed", alert_date=dt.date(2026, 10, 2), pnl=-200.0, hold=1,
         exits=_STOP_EXIT, price=10.0, stop=8.0, score=88.0, gap=15.5),
    _row("ZZOP", "live", status="filled", alert_date=dt.date(2026, 10, 1), pnl=0.0, hold=5,
         exits=[], price=20.0, stop=18.0, shares=50),
]

TOTALS = {"total": 41, "open_count": 2, "winners": 12, "losers": 24,
          "realized_pnl": 1234.5, "filtered_count": 9}


def _fake_db(rows=FIXTURE_ROWS):
    """A fetch/fetchrow pair that applies the book + ticker filters the SQL asks for, so the test
    exercises the handler's real WHERE clause (a handler that kept `account_mode = 'live'` would get
    the live rows only, exactly like the database would give it)."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    seen_sql: list[str] = []

    async def fetch(sql, *params):
        seen_sql.append(sql)
        out = list(rows)
        if "account_mode = 'live'" in sql:
            out = [r for r in out if r["account_mode"] == "live"]
        elif "account_mode IN ('live', 'paper')" in sql:
            out = [r for r in out if r["account_mode"] in ("live", "paper")]
        else:
            raise AssertionError(f"trade query with NO explicit account_mode condition:\n{sql}")
        if "ticker = $1" in sql:
            out = [r for r in out if r["ticker"] == params[0]]
        return out[:20]

    async def fetchrow(sql, *params):
        seen_sql.append(sql)
        assert "account_mode = 'live'" in sql, f"totals query is not live-only:\n{sql}"
        return TOTALS

    conn.fetch = AsyncMock(side_effect=fetch)
    conn.fetchrow = AsyncMock(side_effect=fetchrow)
    return pool, seen_sql


def _make_agent():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from shared.models import AgentName
    with patch("agents.base.get_secrets"), patch("shared.audit.log_action"):
        agent = MarketIntelligenceAgent.__new__(MarketIntelligenceAgent)
        agent.agent_name = AgentName.MARKET_INTELLIGENCE
    return agent


def _run(task, ticker=None):
    from agents.market_intelligence import agent as agent_mod
    from agents.market_intelligence import constants
    from agents.market_intelligence import execution_client
    from shared.models import AgentRequest
    pool, seen_sql = _fake_db()

    # #706: the open rows now read the broker (position + account equity, per row's own book).
    # Hermetic: one live position for ZZOP (50 sh @ $20 = $1,000 of a $100,000 account); the paper
    # rows get no position, so their stats print as dashes. NEVER the real broker.
    async def _get_position(ticker, account_mode=None):
        if (ticker, account_mode) == ("ZZOP", "live"):
            return {"current_price": 20.0, "market_value": 1_000.0, "side": "long", "unrealized_pl": 0.0}
        return None

    async def _get_account(account_mode=None):
        return {"equity": 100_000.0}

    async def go():
        with patch.object(agent_mod, "get_pool", new=AsyncMock(return_value=pool)), \
             patch.object(constants, "LIVE_TRADING_ENABLED", True), \
             patch.object(execution_client, "get_position", new=_get_position), \
             patch.object(execution_client, "get_account", new=_get_account), \
             patch.dict(sys.modules, {
                 "agents.market_intelligence.backtester.tracker": _real_formatter_module()}):
            req = AgentRequest(task=task, user_id=1, conversation_id="t")
            return await _make_agent()._handle_trades_query(req, ticker=ticker)

    resp = asyncio.run(go())
    assert resp.success
    return resp.result, seen_sql


# The pre-change output of `_run("my trades")` on this fixture, captured from the unmodified handler
# (main @ 182d21b7) BEFORE the edit. The no-ticker list must never drift from it — EXCEPT the two
# deliberate #706 additions: the closed rows' % win/loss and the open row's size/stop line.
GOLDEN_NO_TICKER_LIST = '''*Live Trade History (Alpaca · real money)*

❌ *ZZLV* Oct 09 gap=22.5% score=80
  ORB entry=$10.00 stop=$8.00 ×100
  10:20 (stop_hit) 100sh @$8.00 P&L $-200
  *Total P&L: $-200.00* · -20.0% (1d)
❌ *ZZBO* Oct 02 gap=15.5% score=88
  ORB entry=$10.00 stop=$8.00 ×100
  10:20 (stop_hit) 100sh @$8.00 P&L $-200
  *Total P&L: $-200.00* · -20.0% (1d)
🟡 *ZZOP* Oct 01 gap=22.5% score=80
  ORB entry=$20.00 stop=$18.00 ×50
  ↗ open
  Open — 5d  Stop: $18.00
  1.0% of $100,000 equity · 10.0% to stop

*Totals:* 41 traded · 2 open · 36 closed (33% win) · P&L $+1,234.50 · 9 filtered'''


def test_no_ticker_list_and_totals_are_byte_identical_to_before():
    text, seen_sql = _run("my trades")
    assert text == GOLDEN_NO_TICKER_LIST
    # live-only: the paper rows of the fixture never reach the list, and no tag leaks in
    assert "ZZPP" not in text
    assert PAPER_TAG not in text and LIVE_TAG not in text
    # and every query it ran stayed live-only
    assert seen_sql and all("account_mode = 'live'" in s for s in seen_sql)


def test_ticker_view_tags_a_paper_row_paper():
    """The gap itself: a paper-lane position used to answer 'No paper trades found'."""
    text, _ = _run("/trades_detail zzpp", ticker="ZZPP")
    assert "No paper trades found" not in text and "No trades found" not in text
    assert "ZZPP" in text
    row_header = next(ln for ln in text.splitlines() if "ZZPP" in ln)
    assert PAPER_TAG in row_header and LIVE_TAG not in row_header
    # the paper tag must not become the START of the message: the sender routes a message that
    # starts with it to the paper chat, and an interactive reply has to stay where he asked
    assert not is_paper_message(text)


def test_ticker_view_tags_a_live_row_live_and_keeps_totals_live():
    text, seen_sql = _run("/trades_detail zzlv", ticker="ZZLV")
    row_header = next(ln for ln in text.splitlines() if "ZZLV" in ln)
    assert LIVE_TAG in row_header and PAPER_TAG not in row_header
    # the TOTALS footer is the live-book total, unchanged, and says so in a ticker view
    assert "41 traded" in text and "P&L $+1,234.50" in text
    assert [s for s in seen_sql if "COUNT(*)" in s and "account_mode = 'live'" in s]


def test_ticker_with_rows_in_both_books_shows_each_with_its_own_tag():
    text, _ = _run("/trades_detail zzbo", ticker="ZZBO")
    headers = [ln for ln in text.splitlines() if "ZZBO" in ln]
    assert len(headers) == 2
    assert PAPER_TAG in headers[0] and LIVE_TAG not in headers[0]    # newest first: the paper row
    assert LIVE_TAG in headers[1] and PAPER_TAG not in headers[1]


def test_ticker_with_no_rows_in_either_book_says_so_without_calling_it_paper():
    text, _ = _run("/trades_detail nope", ticker="NOPE")
    assert "NOPE" in text and "live or paper" in text


def test_every_ticker_query_names_its_books_explicitly():
    _, seen_sql = _run("/trades_detail zzpp", ticker="ZZPP")
    trade_sql = [s for s in seen_sql if "FROM mi_live_trades" in s and "SELECT ticker" in s]
    assert trade_sql and all("account_mode IN ('live', 'paper')" in s for s in trade_sql)
    # the tag needs the column: asyncpg raises KeyError on a missing one, the fake never would
    assert all("account_mode" in s.split("FROM mi_live_trades")[0] for s in trade_sql)


@pytest.mark.parametrize("task", ["open trades", "closed trades", "paper p&l"])
def test_list_variants_stay_live_only(task):
    text, seen_sql = _run(task)
    assert "ZZPP" not in text and PAPER_TAG not in text
    assert all("account_mode = 'live'" in s for s in seen_sql)
