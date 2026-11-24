"""/trades by STRATEGY (operator 2026-11-24) — display only.

Level 1 (a book with several strategies / any retired one): one line per ACTIVE strategy + one folded
retired line. Level 2: a strategy's page with Closed / Skipped / Scanned scoped to it. Skip rule: one
active strategy and no retired ones -> level 2 straight away (live today). Active vs retired is DERIVED
from the registry (enabled + phase -> account mode), never a typed list.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.market_intelligence import trades_by_strategy as tbs
from channels import telegram as tg
from channels.telegram import TelegramChannel, _trades_keyboard
from tests.conftest import fake_httpx_client, make_mock_pool

PAPER_CHAT = -5382801675
MAIN_CHAT = 111222333


# ── fixtures: a registry + per-signal_type stats, served by a SQL-dispatching fake conn ──────────

REGISTRY_PAPER_MIXED = [
    {"strategy_id": "magna53", "signal_type": "magna53", "name": "MAGNA53 EP", "phase": "live", "enabled": True},
    {"strategy_id": "breakout_v1", "signal_type": "breakout_v1", "name": "Breakout v1 (paper)", "phase": "paper", "enabled": True},
    {"strategy_id": "9m_day2", "signal_type": "9m_day2", "name": "9M day 2", "phase": "deprecated", "enabled": False},
    {"strategy_id": "magna53_lowcap", "signal_type": "magna53_lowcap", "name": "lowcap lane", "phase": "paper", "enabled": True},
]


def _stat(sig, first, last, closed, wins, realized, avg_r, open_n=0, open_realized=0.0):
    return {"sig": sig, "first_trade": first, "last_trade": last, "closed_n": closed, "wins": wins,
            "realized": realized, "avg_r": avg_r, "open_n": open_n, "open_realized": open_realized}


PAPER_STATS = [
    _stat("breakout_v1", date(2026, 11, 2), date(2026, 11, 23), 22, 6, -9553.0, -0.42, 5, 365.0),
    _stat("magna53", date(2026, 4, 6), date(2026, 6, 12), 28, 9, -9377.0, -0.31),
    _stat("9m_day2", date(2026, 5, 4), date(2026, 6, 20), 6, 1, -1293.0, -0.5),
    _stat("magna53_lowcap", None, None, 0, 0, 0.0, None),       # registry-active but never traded: no line
]
LIVE_STATS = [_stat("magna53", date(2026, 7, 1), date(2026, 11, 20), 12, 7, 2210.0, 0.6, 1, 120.0)]


class FakeConn:
    def __init__(self, registry, stats_by_book):
        self.registry, self.stats_by_book, self.calls = registry, stats_by_book, []

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        if "FROM mi_strategies" in sql:
            return self.registry
        if "GROUP BY 1" in sql:                       # the by-strategy stats read
            return self.stats_by_book[args[0]]
        return []

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        return {"winners": 0, "losers": 0, "realized": 0}


_TOGGLES = {}   # runtime toggle name -> on/off for the fake read (absent = on)


@pytest.fixture(autouse=True)
def _runtime_toggles():
    _TOGGLES.clear()

    async def fake(name, env_var, default=True):
        return _TOGGLES.get(name, default)
    with patch("agents.market_intelligence.db.get_runtime_toggle", new=fake):
        yield


def _agent():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from shared.models import AgentName
    with patch("agents.base.get_secrets"), patch("shared.audit.log_action"):
        a = MarketIntelligenceAgent.__new__(MarketIntelligenceAgent)
        a.agent_name = AgentName.MARKET_INTELLIGENCE
    return a


def _detail(task, registry=REGISTRY_PAPER_MIXED, stats=None, scanned_text="SCAN BODY"):
    """Drive the real `_handle_trades_detail`. Returns (text, conn)."""
    from agents.market_intelligence import agent as agent_mod
    from agents.market_intelligence import execution_client
    from shared.models import AgentRequest

    conn = FakeConn(registry, stats or {"paper": PAPER_STATS, "live": LIVE_STATS})
    pool, _ = make_mock_pool()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

    async def go():
        with patch.object(agent_mod, "get_pool", new=AsyncMock(return_value=pool)), \
             patch.object(execution_client, "get_position", new=AsyncMock(return_value=None)), \
             patch.object(execution_client, "get_account", new=AsyncMock(return_value={"equity": 100000})), \
             patch("agents.market_intelligence.db.get_ep_scanned_day", new=AsyncMock(return_value={})), \
             patch("agents.market_intelligence.scanned_report.render_scanned_day", new=lambda d, data: scanned_text):
            return await _agent()._handle_trades_detail(
                AgentRequest(task=task, user_id=1, conversation_id="t"))

    resp = asyncio.run(go())
    assert resp.success
    return resp.result, conn


# ── level 1 ──────────────────────────────────────────────────────────────────────────────────────

def test_level1_paper_mixed_strategies():
    text, _ = _detail("/trades_detail summary 2026-11-24 paper")
    assert "`breakout_v1` (since Nov 2)" in text
    assert "22 closed -$9,553 · win 27% · avg -0.4R" in text
    assert "5 open +$365" in text
    # ONE folded retired line: both retired names, combined closed count and $, the date span
    assert "retired: `magna53`, `9m_day2` · 34 closed -$10,670 (Apr–Jun)" in text or \
           "retired: `9m_day2`, `magna53` · 34 closed -$10,670 (Apr–Jun)" in text
    assert text.count("retired:") == 1
    assert "bear-market regime" in text                      # the one regime note
    # an active-by-registry strategy with no trades yet does not clutter the board
    assert "magna53_lowcap" not in text
    assert "PAPER" in text


def test_active_vs_retired_is_derived_from_the_registry_not_a_typed_list():
    # magna53 re-routed to paper (phase paper) and breakout disabled -> they swap places on their own
    registry = [
        {**REGISTRY_PAPER_MIXED[0], "phase": "paper"},
        {**REGISTRY_PAPER_MIXED[1], "enabled": False},
        REGISTRY_PAPER_MIXED[2],
    ]
    text, _ = _detail("/trades_detail summary 2026-11-24 paper", registry=registry)
    assert "`magna53` (since Apr 6)" in text and "retired:" in text and "`breakout_v1`" in text.split("retired:")[1]


def test_a_new_paper_strategy_appears_from_its_first_trade():
    registry = REGISTRY_PAPER_MIXED + [{"strategy_id": "flagship", "signal_type": "flagship", "name": "n",
                                        "phase": "paper", "enabled": True}]
    stats = {"paper": PAPER_STATS + [_stat("flagship", date(2026, 11, 20), date(2026, 11, 23), 1, 1, 50.0, 1.2)]}
    text, _ = _detail("/trades_detail summary 2026-11-24 paper", registry=registry, stats=stats)
    assert "`flagship` (since Nov 20)" in text and "avg +1.2R" in text
    assert text.index("`flagship`") < text.index("`breakout_v1`")      # newest on top


# ── skip rule ────────────────────────────────────────────────────────────────────────────────────

def test_skip_rule_live_one_strategy_shows_the_page_plus_its_line():
    text, _ = _detail("/trades_detail summary 2026-11-24")
    assert "LIVE" in text and "Strategies —" not in text            # not level 1
    assert "`magna53` (since Jul 1)" in text and "12 closed +$2,210" in text
    assert "No open positions" in text                              # the legacy page is still there


def test_nav_payload_for_each_book():
    for book, skip in (("paper", None), ("live", "magna53")):
        out, _ = _detail(f"/trades_detail nav -{' paper' if book == 'paper' else ''}")
        d = json.loads(out)
        assert d["skip"] == skip
    d = json.loads(_detail("/trades_detail nav - paper")[0])
    assert d["strategies"] == ["breakout_v1"] and d["retired"] is True and d["match"] is None


# ── typed arg resolution ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("arg,want", [("breakout", "breakout_v1"), ("breakout_v1", "breakout_v1"),
                                      ("ep", "magna53"), ("retired", "retired"), ("magna53", "magna53"),
                                      ("figs", None), ("break", None), ("brk", None)])
def test_resolve_arg(arg, want):
    bs = asyncio.run(tbs.load_book_strategies(FakeConn(REGISTRY_PAPER_MIXED, {"paper": PAPER_STATS}), "paper"))
    assert tbs.resolve_arg(bs, arg) == want


def test_resolve_arg_retired_needs_a_retired_strategy():
    bs = asyncio.run(tbs.load_book_strategies(FakeConn(REGISTRY_PAPER_MIXED, {"live": LIVE_STATS}), "live"))
    assert tbs.resolve_arg(bs, "retired") is None


# ── scoped views ─────────────────────────────────────────────────────────────────────────────────

def _scope_args(conn, needle):
    return [a for s, a in conn.calls if needle in s and "mi_live_trades" in s and "GROUP BY 1" not in s]


def test_scoped_closed_and_skipped_bind_the_book_and_the_strategy():
    for view, needle in (("closed", "status = 'closed'"), ("skipped", "'skipped'")):
        text, conn = _detail(f"/trades_detail strat breakout_v1 {view} 2026-11-24 paper")
        calls = _scope_args(conn, needle)
        assert calls and all(a[0] == "paper" and a[1] == ["breakout_v1"] for a in calls), calls
        assert "= ANY($2::text[])" in [s for s, _ in conn.calls if needle in s and "GROUP BY 1" not in s][0]
        assert "`breakout_v1`" in text


def test_scoped_retired_covers_every_retired_strategy():
    _, conn = _detail("/trades_detail strat retired closed 2026-11-24 paper")
    (args,) = _scope_args(conn, "status = 'closed'")
    assert args[0] == "paper" and sorted(args[1]) == ["9m_day2", "magna53"]


def test_scoped_scanned_says_it_is_the_ep_scan_not_breakouts():
    text, _ = _detail("/trades_detail strat breakout_v1 scanned 2026-11-24 paper")
    assert text.startswith("_This is the EP gap scan — breakout_v1 candidates are not in it._")
    assert "SCAN BODY" in text and "whole day" not in text


def test_magna53_scanned_is_unlabelled():
    text, _ = _detail("/trades_detail strat magna53 scanned 2026-11-24 paper")
    assert text == "SCAN BODY"


def test_typed_uppercase_NAV_ticker_is_not_the_internal_nav_view():
    text, _ = _detail("/trades_detail NAV 2026-11-24")
    assert not text.startswith("{")        # the ticker path, never the JSON payload
    text, _ = _detail("/trades_detail nav - paper")
    assert text.startswith("{")


def test_runtime_toggle_off_retires_a_strategy_into_the_retired_line():
    _TOGGLES["breakout_v1_paper"] = False
    text, _ = _detail("/trades_detail summary 2026-11-24 paper")
    assert "retired:" in text and "`breakout_v1`" in text.split("retired:")[1]


def test_back_button_in_skip_book_points_at_the_skip_strategy_not_the_typed_scope():
    nav = {**NAV_LIVE, "skip": "magna53"}
    d = _data(_trades_keyboard("2026-11-24", "live", nav=nav, scope="breakout_v1"))
    assert d[-1] == "trades:st:magna53"


def test_level2_summary_scopes_every_query_and_shows_the_strategy_line():
    text, conn = _detail("/trades_detail strat breakout_v1 summary 2026-11-24 paper")
    assert "`breakout_v1` (since Nov 2)" in text and "PAPER" in text
    for sql, args in conn.calls:
        if "mi_live_trades" in sql and "GROUP BY 1" not in sql:
            assert "account_mode" in sql and "paper" in args, sql        # dual-account invariant
            assert "ANY($" in sql
    retired, _ = _detail("/trades_detail strat retired summary 2026-11-24 paper")
    assert "Retired strategies" in retired and "34 closed" in retired


def test_unscoped_old_views_are_unchanged():
    _, conn = _detail("/trades_detail closed 2026-11-24 paper")
    (args,) = _scope_args(conn, "status = 'closed'")
    assert args == ("paper",)
    _, conn = _detail("/trades_detail skipped")
    (args,) = _scope_args(conn, "'skipped'")
    assert args == ("live",)


def test_registry_failure_falls_back_to_the_legacy_page():
    from agents.market_intelligence import agent as agent_mod
    from agents.market_intelligence import execution_client
    from shared.models import AgentRequest
    conn = MagicMock()
    conn.fetch = AsyncMock(side_effect=lambda sql, *a: (_ for _ in ()).throw(RuntimeError("db")) if "mi_strategies" in sql else [])
    conn.fetchrow = AsyncMock(return_value={"winners": 0, "losers": 0, "realized": 0})
    pool, _ = make_mock_pool()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)

    async def go():
        with patch.object(agent_mod, "get_pool", new=AsyncMock(return_value=pool)), \
             patch.object(execution_client, "get_position", new=AsyncMock(return_value=None)):
            return await _agent()._handle_trades_detail(
                AgentRequest(task="/trades_detail summary 2026-11-24 paper", user_id=1, conversation_id="t"))
    assert "No paper positions." in asyncio.run(go()).result


# ── telegram layer ───────────────────────────────────────────────────────────────────────────────

NAV_PAPER = {"strategies": ["breakout_v1"], "retired": True, "skip": None, "match": None}
NAV_LIVE = {"strategies": ["magna53"], "retired": False, "skip": "magna53", "match": None}


def _data(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def test_level1_keyboard_one_button_per_strategy_plus_retired():
    d = _data(_trades_keyboard("2026-11-24", "paper", nav=NAV_PAPER))
    assert d == ["trades:st:breakout_v1:paper", "trades:st:retired:paper"]


def test_level2_keyboard_is_scoped_with_a_back_button():
    d = _data(_trades_keyboard("2026-11-24", "paper", nav=NAV_PAPER, scope="breakout_v1"))
    assert d == ["trades:sc:breakout_v1:2026-11-24:paper", "trades:ss:breakout_v1:paper",
                 "trades:sn:breakout_v1:2026-11-24:paper", "trades:summary:paper"]


def test_skip_rule_keyboard_goes_straight_to_level2_and_back_stays_on_the_page():
    d = _data(_trades_keyboard("2026-11-24", "live", nav=NAV_LIVE))
    assert d[0] == "trades:sc:magna53:2026-11-24" and d[-1] == "trades:st:magna53"
    assert not any("paper" in x for x in d)


def test_every_new_callback_data_fits_telegram_64_bytes():
    nav = {"strategies": ["magna53_lowcap", "breakout_v1", "x" * 80], "retired": True, "skip": None}
    for scope in (None, "retired", "magna53_lowcap", "x" * 80):
        for book in ("paper", "live"):
            for with_summary in (False, True):
                for n in (nav, None):
                    for d in _data(_trades_keyboard("2026-11-24", book, with_summary, nav=n, scope=scope)):
                        assert len(d.encode()) <= 64, d


def test_no_nav_gives_the_legacy_keyboard_byte_for_byte():
    assert _data(_trades_keyboard("2026-11-24", "paper")) == [
        "trades:closed:2026-11-24:paper", "trades:skipped:paper", "trades:scanned:2026-11-24:paper"]
    assert _data(_trades_keyboard("2026-11-24", "live", with_summary=True))[-1] == "trades:summary"


def _channel(nav):
    ch = TelegramChannel.__new__(TelegramChannel)
    ch._secrets = SimpleNamespace(telegram_allowed_user_ids=[42], internal_api_secret="s")
    sent = []

    async def post(task, user_id, *a, **k):
        sent.append(task)
        if task.startswith("/trades_detail nav "):
            arg = task.split()[2]
            return json.dumps({**nav, "match": {"breakout": "breakout_v1", "breakout_v1": "breakout_v1",
                                                "ep": "magna53", "retired": "retired"}.get(arg)}) if nav else "x"
        return "BODY"
    ch._post_market_task = post
    ch._reply_with_fallback = AsyncMock()
    ch.sent = sent
    return ch


def _update(chat):
    msg = MagicMock()
    msg.reply_text = AsyncMock()
    return SimpleNamespace(effective_user=SimpleNamespace(id=42), effective_chat=SimpleNamespace(id=chat), message=msg)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_PAPER_CHAT_ID", str(PAPER_CHAT))


@pytest.mark.asyncio
async def test_plain_trades_in_paper_chat_sends_level1_with_strategy_buttons():
    ch = _channel(NAV_PAPER)
    await ch._handle_trades_command(_update(PAPER_CHAT), SimpleNamespace(args=[]))
    assert ch.sent[-1].startswith("/trades_detail summary ") and ch.sent[-1].endswith(" paper")
    assert _data(ch._reply_with_fallback.await_args.kwargs["reply_markup"]) == [
        "trades:st:breakout_v1:paper", "trades:st:retired:paper"]


@pytest.mark.asyncio
@pytest.mark.parametrize("arg,sid", [("breakout", "breakout_v1"), ("breakout_v1", "breakout_v1"),
                                     ("EP", "magna53"), ("retired", "retired")])
async def test_typed_strategy_jumps_to_level2_before_the_ticker_path(arg, sid):
    ch = _channel(NAV_PAPER)
    await ch._handle_trades_command(_update(PAPER_CHAT), SimpleNamespace(args=[arg]))
    assert ch.sent[-1] == f"/trades_detail strat {sid} summary {ch.sent[-1].split()[4]} paper"
    d = _data(ch._reply_with_fallback.await_args.kwargs["reply_markup"])
    assert d[0].startswith(f"trades:sc:{sid}:") and d[-1] == "trades:summary:paper"


@pytest.mark.asyncio
async def test_ticker_still_works_when_it_names_no_strategy():
    ch = _channel(NAV_PAPER)
    await ch._handle_trades_command(_update(PAPER_CHAT), SimpleNamespace(args=["figs"]))
    assert " FIGS " in ch.sent[-1] and ch.sent[-1].endswith(" paper")
    assert "reply_markup" not in ch._reply_with_fallback.await_args.kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize("arg", ["2026-11-20", "x", "toolongticker", "12"])
async def test_a_non_ticker_argument_still_gets_the_summary(arg):
    """#549: a date, a single letter or junk must not fall into the ticker branch and lose the board."""
    ch = _channel(NAV_PAPER)
    await ch._handle_trades_command(_update(PAPER_CHAT), SimpleNamespace(args=[arg]))
    assert ch.sent[-1].startswith("/trades_detail summary ") and ch.sent[-1].endswith(" paper")


@pytest.mark.asyncio
async def test_live_chat_skip_rule_lands_on_level2_buttons():
    ch = _channel(NAV_LIVE)
    await ch._handle_trades_command(_update(MAIN_CHAT), SimpleNamespace(args=[]))
    assert "paper" not in ch.sent[-1]
    d = _data(ch._reply_with_fallback.await_args.kwargs["reply_markup"])
    assert d[0].startswith("trades:sc:magna53:") and not any("paper" in x for x in d)


# ── callbacks ────────────────────────────────────────────────────────────────────────────────────

async def _press(monkeypatch, data, chat, nav=NAV_PAPER):
    import httpx
    ch = _channel(nav)
    fake = fake_httpx_client(json_body={"result": "ok"})
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    monkeypatch.setattr("shared.registry.get_agent_url", lambda name: "http://market")
    q = MagicMock()
    q.from_user = SimpleNamespace(id=42)
    q.message = SimpleNamespace(chat_id=chat)
    q.edit_message_text = AsyncMock()
    await ch._handle_drill_down_callback(q, data)
    return (fake.last_post["kwargs"]["json"]["task"],
            _data(q.edit_message_text.await_args.kwargs["reply_markup"]))


@pytest.mark.asyncio
@pytest.mark.parametrize("data,task", [
    ("trades:st:breakout_v1:paper", "/trades_detail strat breakout_v1 summary {d} paper"),
    ("trades:st:retired:paper", "/trades_detail strat retired summary {d} paper"),
    ("trades:sc:breakout_v1:2026-11-20:paper", "/trades_detail strat breakout_v1 closed 2026-11-20 paper"),
    ("trades:ss:breakout_v1:paper", "/trades_detail strat breakout_v1 skipped {d} paper"),
    ("trades:sn:breakout_v1:2026-11-20:paper", "/trades_detail strat breakout_v1 scanned 2026-11-20 paper"),
])
async def test_new_strategy_buttons_route_to_scoped_views_and_keep_scope(monkeypatch, data, task):
    from shared.dates import last_trading_day
    sent, buttons = await _press(monkeypatch, data, PAPER_CHAT)
    assert sent == task.format(d=last_trading_day().isoformat())
    sid = data.split(":")[2]
    assert buttons[0].startswith(f"trades:sc:{sid}:") and buttons[-1] == "trades:summary:paper"
    assert all(len(b.encode()) <= 64 for b in buttons)


@pytest.mark.asyncio
async def test_old_callback_data_still_answers_unscoped(monkeypatch):
    for data, sent_prefix in (("trades:closed:2026-11-19:paper", "/trades_detail closed 2026-11-19 paper"),
                              ("trades:skipped:paper", "/trades_detail skipped "),
                              ("trades:scanned:2026-11-19:paper", "/trades_detail scanned 2026-11-19 paper"),
                              ("trades:summary:paper", "/trades_detail summary "),
                              ):
        sent, buttons = await _press(monkeypatch, data, PAPER_CHAT)
        assert sent.startswith(sent_prefix), (data, sent)
        assert all(len(b.encode()) <= 64 for b in buttons)
    # an old unscoped press keeps the OLD keyboard (pinned messages behave as before)
    _, buttons = await _press(monkeypatch, "trades:closed:2026-11-19:paper", PAPER_CHAT)
    assert [b.split(":")[1] for b in buttons] == ["closed", "skipped", "scanned", "summary"]
    # the old summary press now lands on the by-strategy board
    _, buttons = await _press(monkeypatch, "trades:summary:paper", PAPER_CHAT)
    assert buttons == ["trades:st:breakout_v1:paper", "trades:st:retired:paper"]
    # `trades:paper` (the retired legacy button) still answers — it always read as the paper summary
    sent, _ = await _press(monkeypatch, "trades:paper", MAIN_CHAT, nav=NAV_LIVE)
    assert sent.startswith("/trades_detail summary ") and sent.endswith(" paper")
    # live, unsuffixed, main chat: still the live book
    sent, _ = await _press(monkeypatch, "trades:closed:2026-11-19", MAIN_CHAT, nav=NAV_LIVE)
    assert sent == "/trades_detail closed 2026-11-19"
