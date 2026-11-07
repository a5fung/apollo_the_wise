"""#312 — the ladder's ACT step is HIS press (ADR 0022 §1 as ruled 2026-11-04).

The DoD, verbatim: "the shadow→paper→live ladder is CODE where a breach sends him ONE Telegram
with the strategy's stats (each limit's value against its bar, closed trades, cumulative R, open
positions) and two buttons — Demote moves it one rung down through `update_strategy` with a
`strategy_phase_change` row; No action writes an audit row and moves nothing — proven by a forced
breach in a test producing that page, and each button's effect. WOULD-FAIL-IF: a breach produces
no page (he would have to notice it himself), or any path moves a phase without his press."

Sections:
  A. the nightly page — one page per strategy per breach EPISODE, every stat, both buttons, the
     cadence (no re-page on a second breach night; a NEWLY breached limit re-pages; a clear night
     closes the episode; a recovery re-run never pages; a failed send leaves the episode unpaged);
  B. the press — Demote moves exactly one rung through the one phase writer (compare-and-set on
     the phase the page showed, in one transaction) and writes `strategy_phase_change`; a double
     press moves one rung TOTAL; a stale press refuses; No action moves nothing and audits; an
     unauthorized press is refused at the channel gate AND by the market agent;
  C. an open LIVE position keeps its exit and stop management on the LIVE account after the
     demote — the trade row's `account_mode` decides, never the strategy's phase (invariant pin:
     it passes on today's code; it reds if either path read the mode from the registry);
  D. structure — no path but the operator's three (typed promote, typed demote, the Demote
     button) calls `update_strategy` with a phase; the §2 allocator-zeroing invariant is vacuous
     until the L3 proposal store exists, and this file fails the day it does.

The DB is `tests/_ladder_fake_db.LadderFakeDb`, which interprets the ladder's OWN SQL (shared with
`tests/test_ladder_watchdog.py`). Every test here was run against the pre-build code first and
failed (recorded in the #312 commit).
"""
from __future__ import annotations

import ast
import asyncio
import datetime as dt
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from agents.market_intelligence import ladder_watchdog as lw
from agents.market_intelligence.strategies import registry
from tests._ladder_fake_db import LadderFakeDb, strategy_row

REPO = Path(__file__).resolve().parents[1]
_NIGHT1 = dt.date(2026, 10, 15)
_NIGHT2 = dt.date(2026, 10, 16)
_NIGHT3 = dt.date(2026, 10, 19)
OPERATOR = 42


def _rs(value, n):
    return [value] * n


def _one_row(r, *, id, alert_date, exit_rule=None):
    return {"id": id, "total_pnl": 100.0 * r, "risk_dollars_actual": None, "entry_shares": 1.0,
            "entry_price": 101.0, "hard_stop": 1.0, "alert_date": alert_date,
            "closed_on_et": alert_date, "signal_type": "magna53", "exit_rule": exit_rule}


def _closed_rows(rs, *, first_id=1):
    base = dt.date(2026, 7, 1)
    return [_one_row(r, id=first_id + i, alert_date=base + dt.timedelta(days=i)) for i, r in enumerate(rs)]


STREAK_BREACH = _rs(2.0, 20) + _rs(-1.0, 6)                 # streak 6 · last-20 +1.10R · dd −6.00R
TRIPLE_BREACH = _rs(2.0, 10) + [-1.0, 0.5] * 20 + _rs(-1.0, 6)   # streak 6 · last-20 −0.475R · dd −16R
CLEAR = [1.5, -1.0, 2.0, -1.0, -1.0, 3.0] * 5


@pytest.fixture(autouse=True)
def _operator_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", str(OPERATOR))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.delenv("TELEGRAM_PAPER_CHAT_ID", raising=False)


def _db(monkeypatch, *, live_series=STREAK_BREACH, phase="live", open_positions=("AEHR", "FN")):
    db = LadderFakeDb(
        strategies=[strategy_row("magna53", phase, live_real=True), strategy_row("magna53_smallcap", "paper")],
        closed_rows={("magna53", "live" if phase == "live" else "paper"): _closed_rows(live_series),
                     ("magna53_smallcap", "paper"): _closed_rows(CLEAR)},
        open_positions={("magna53", "live"): list(open_positions)},
    ).wire(monkeypatch)
    # The act step must never reach a phase writer from the NIGHTLY pass.
    monkeypatch.setattr(registry, "update_strategy",
                        AsyncMock(side_effect=AssertionError("the watchdog reached update_strategy")))
    return db


def _run(today=_NIGHT1):
    return asyncio.run(lw.run_ladder_watchdog(today=today))


def _buttons(send):
    rows = send["reply_markup"]["inline_keyboard"]
    return [btn for row in rows for btn in row]


def _press(action, page_id, user_id=OPERATOR):
    from agents.market_intelligence.ladder_press import handle_ladder_press
    return asyncio.run(handle_ladder_press(action, page_id, user_id=user_id))


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# A — the nightly page
# ═══════════════════════════════════════════════════════════════════════════════════════════════


def test_a_forced_breach_sends_exactly_one_page_with_every_stat_and_both_buttons(monkeypatch):
    """THE DoD's page. A six-loss streak on the live book → ONE Telegram naming the strategy and
    its rung, every limit's value against its bar, closed trades, cumulative R, open positions
    (count + tickers), and the two buttons; monospace block, no pipe table."""
    db = _db(monkeypatch)
    detail = _run()

    assert len(db.sends) == 1, "a breach must produce exactly one page"
    send = db.sends[0]
    text = send["text"]
    assert send["parse_mode"] == "HTML"
    assert "<pre>" in text and not any(line.lstrip().startswith("|") for line in text.splitlines())
    assert "magna53" in text and "live" in text
    # each limit: plain-word label, value, bar
    assert "losing streak" in text and "6" in text
    assert "mean R, last 20 trades" in text and "+1.10R" in text and "-0.30R" in text
    assert "drawdown from the peak" in text and "-6.00R" in text and "-10.00R" in text
    assert "harmful auto-action" in text and "not measurable" in text
    assert "BREACHED" in text
    assert "closed trades 26" in text
    assert "cumulative R +34.00R" in text
    assert "open positions 2" in text and "AEHR, FN" in text
    # the two buttons, carrying the page id
    page_id = detail["paged"][0]["page_id"]
    btns = _buttons(send)
    assert [b["callback_data"] for b in btns] == [f"ladder:demote:{page_id}", f"ladder:noaction:{page_id}"]
    assert "Demote to paper" in btns[0]["text"] and "No action" in btns[1]["text"]
    assert all(len(b["callback_data"].encode()) <= 64 for b in btns)
    # persisted: the page (sent), the episode (open), the audit row
    page = db.pages[page_id]
    assert page["sent_at"] is not None and page["phase_at_page"] == "live" and page["demote_to"] == "paper"
    assert page["breached"] == ["consec_losses"] and page["decision"] is None
    assert db.episodes[("magna53", _NIGHT1)]["closed_on"] is None
    assert len(db.audit_rows(lw.PAGED_EVENT)) == 1
    assert detail["paged"] == [{"strategy_id": "magna53", "action": "paged", "reason": "new episode",
                                "page_id": page_id}]
    # the nightly row still says the job itself acted on nothing
    assert detail["acted"] is False
    assert db.phase_writes == []


def test_the_page_states_the_night_its_id_and_that_nothing_moves_without_his_press(monkeypatch):
    db = _db(monkeypatch)
    detail = _run()
    text = db.sends[0]["text"]
    assert f"#{detail['paged'][0]['page_id']}" in text and _NIGHT1.isoformat() in text
    assert "Nothing moves until you press" in text


def test_a_second_breach_night_in_the_same_episode_sends_nothing(monkeypatch):
    """One page per strategy per breach EPISODE: the same breach the next night is not re-paged
    (the buttons on the first page are still live)."""
    db = _db(monkeypatch)
    _run(_NIGHT1)
    detail2 = _run(_NIGHT2)
    assert len(db.sends) == 1
    assert detail2["paged"] == [{"strategy_id": "magna53", "action": "skipped",
                                 "reason": "already paged this episode (page #1, nothing newly breached)",
                                 "page_id": 1}]
    assert len(db.pages) == 1


def test_a_new_limit_breaching_after_no_action_re_pages(monkeypatch):
    """After No action, no re-page in the episode UNLESS a limit that was not breached at the page
    newly breaches: night 1 breaches the streak alone (paged, he presses No action); night 2 adds
    the last-20 mean and the drawdown → a second page in the same episode."""
    db = _db(monkeypatch)
    detail1 = _run(_NIGHT1)
    assert "already decided" not in _press("noaction", detail1["paged"][0]["page_id"])
    db.closed_rows[("magna53", "live")] = _closed_rows(TRIPLE_BREACH)
    detail2 = _run(_NIGHT2)
    assert len(db.sends) == 2
    p = detail2["paged"][0]
    assert p["action"] == "paged" and "newly breached" in p["reason"]
    assert "dd_from_peak_r" in p["reason"] and "trailing20_expectancy_r" in p["reason"]
    assert db.pages[p["page_id"]]["episode_on"] == _NIGHT1       # same episode
    assert sorted(db.pages[p["page_id"]]["breached"]) == ["consec_losses", "dd_from_peak_r",
                                                          "trailing20_expectancy_r"]
    assert db.sends[1]["text"].count("BREACHED") == 3


def test_the_same_limits_after_no_action_do_not_re_page(monkeypatch):
    db = _db(monkeypatch)
    detail1 = _run(_NIGHT1)
    _press("noaction", detail1["paged"][0]["page_id"])
    detail2 = _run(_NIGHT2)
    assert len(db.sends) == 1 and detail2["paged"][0]["action"] == "skipped"


def test_a_clear_night_closes_the_episode_and_the_next_breach_opens_a_new_one(monkeypatch):
    db = _db(monkeypatch)
    _run(_NIGHT1)
    db.closed_rows[("magna53", "live")] = _closed_rows(CLEAR)
    detail2 = _run(_NIGHT2)
    assert detail2["paged"] == [{"strategy_id": "magna53", "action": "episode closed",
                                 "reason": "no limit breached tonight", "page_id": None}]
    assert db.episodes[("magna53", _NIGHT1)]["closed_on"] == _NIGHT2
    assert db.episodes[("magna53", _NIGHT1)]["closed_by"] == "cleared"
    assert len(db.audit_rows(lw.CLEARED_EVENT)) == 1
    db.closed_rows[("magna53", "live")] = _closed_rows(STREAK_BREACH)
    detail3 = _run(_NIGHT3)
    assert len(db.sends) == 2 and detail3["paged"][0]["reason"] == "new episode"
    assert db.episodes[("magna53", _NIGHT3)]["closed_on"] is None


def test_a_phase_moved_by_hand_ends_the_episode_so_the_new_rung_pages_afresh(monkeypatch):
    """The typed `/strategy magna53 demote` between two breach nights: the old page is stale
    (its Demote would refuse), so the open episode on the old rung closes and the breach on the
    new rung gets its own page."""
    db = _db(monkeypatch)
    _run(_NIGHT1)
    db.strategies["magna53"]["phase"] = "paper"
    db.closed_rows[("magna53", "paper")] = _closed_rows(STREAK_BREACH)
    detail2 = _run(_NIGHT2)
    assert len(db.sends) == 2
    assert detail2["paged"][0]["reason"] == "new episode (the rung changed: live → paper)"
    assert db.episodes[("magna53", _NIGHT1)]["closed_by"] == "phase_moved"
    assert db.pages[2]["phase_at_page"] == "paper" and db.pages[2]["demote_to"] == "shadow"
    assert "Demote to shadow" in _buttons(db.sends[1])[0]["text"]


def test_a_recovery_rerun_records_but_never_pages(monkeypatch):
    """Inside a #672 recovery re-run every Telegram is HELD at the httpx layer and reports a
    synthetic success, so a page 'sent' there never reached him. The re-run keeps its audit row
    and leaves the episode UNPAGED; the next live night pages."""
    from shared.dates import pinned_recovery
    db = _db(monkeypatch)
    slot = dt.datetime(2026, 10, 15, 16, 17, tzinfo=dt.timezone.utc)
    with pinned_recovery(lw.JOB_ID, slot):
        detail = _run(_NIGHT1)
    assert db.sends == []
    assert detail["paged"][0]["action"] == "held" and "recovery" in detail["paged"][0]["reason"]
    assert db.episodes == {} and db.pages == {}
    detail2 = _run(_NIGHT2)
    assert len(db.sends) == 1 and detail2["paged"][0]["action"] == "paged"


def test_a_failed_send_leaves_the_episode_unpaged_and_logs_an_error(monkeypatch):
    db = _db(monkeypatch)
    db.send_ok = False
    detail = _run(_NIGHT1)
    assert detail["paged"][0]["action"] == "send failed"
    assert db.pages[1]["sent_at"] is None and db.episodes == {}
    assert len(db.audit_rows(lw.SEND_ERROR_EVENT)) == 1
    db.send_ok = True
    detail2 = _run(_NIGHT2)
    assert detail2["paged"][0]["action"] == "paged" and db.pages[2]["sent_at"] is not None
    assert db.episodes[("magna53", _NIGHT2)]["closed_on"] is None


def test_a_rerun_of_the_same_night_does_not_re_page(monkeypatch):
    db = _db(monkeypatch)
    _run(_NIGHT1)
    second = _run(_NIGHT1)
    assert second["row_already_written"] is True and len(db.sends) == 1
    assert second["paged"] == []


def test_bottom_rung_shadow_gets_no_page_and_no_demote_button(monkeypatch):
    """Shadow has nothing below it: a shadow strategy is never evaluated or paged, and the keyboard
    builder refuses to draw a Demote button for a rung with nothing below."""
    db = LadderFakeDb(strategies=[strategy_row("shadow_orb_5m", "shadow")],
                      closed_rows={("shadow_orb_5m", "paper"): _closed_rows(STREAK_BREACH)}).wire(monkeypatch)
    detail = _run()
    assert db.sends == [] and detail["paged"] == []
    assert "no rung below" in detail["skipped"]["shadow_orb_5m"]
    kb = lw.build_ladder_keyboard(7, "shadow")
    assert [b["callback_data"] for row in kb["inline_keyboard"] for b in row] == ["ladder:noaction:7"]
    assert [b["text"] for row in lw.build_ladder_keyboard(7, "paper")["inline_keyboard"] for b in row][0] \
        == "⬇️ Demote to shadow"
    assert [b["text"] for row in lw.build_ladder_keyboard(7, "live")["inline_keyboard"] for b in row][0] \
        == "⬇️ Demote to paper"


def test_a_paper_strategys_page_wears_the_paper_tag_and_a_live_ones_the_live_tag(monkeypatch):
    """#699: the tag picks the chat. The page carries the strategy's RESOLVED mode (never the bare
    process default), so a paper lane's breach lands in the paper chat and a live one in the main."""
    from agents.market_intelligence.constants import mode_prefix
    db = _db(monkeypatch)
    _run()
    assert db.sends[0]["text"].startswith(mode_prefix("live"))
    db2 = LadderFakeDb(strategies=[strategy_row("magna53_smallcap", "paper")],
                       closed_rows={("magna53_smallcap", "paper"): _closed_rows(STREAK_BREACH)}).wire(monkeypatch)
    _run()
    assert db2.sends[0]["text"].startswith(mode_prefix("paper"))


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# B — the press
# ═══════════════════════════════════════════════════════════════════════════════════════════════


_ORIGINAL_UPDATE_STRATEGY = registry.update_strategy     # captured before any test patches it


def _paged(monkeypatch, **kw):
    """A breach night paged; the REAL `update_strategy` restored for the press (the `_db` fixture
    forbids it only for the nightly pass — `ladder_press` binds it at call time)."""
    db = _db(monkeypatch, **kw)
    detail = _run()
    monkeypatch.setattr(registry, "update_strategy", _ORIGINAL_UPDATE_STRATEGY)
    return db, detail["paged"][0]["page_id"]


def test_demote_press_moves_one_rung_and_writes_strategy_phase_change(monkeypatch):
    db, page_id = _paged(monkeypatch)
    answer = _press("demote", page_id)
    assert db.strategies["magna53"]["phase"] == "paper"
    assert db.phase_writes == [("phase_write", "magna53", ("paper",))]
    rows = db.audit_rows("strategy_phase_change")
    assert len(rows) == 1
    summary, detail = rows[0]
    assert "magna53 demoted live → paper" in summary and f"page #{page_id}" in summary
    d = json.loads(detail)
    assert d["phase_from"] == "live" and d["phase_to"] == "paper"
    assert d["page_id"] == page_id and d["pressed_by"] == OPERATOR and d["pressed_at"]
    assert d["breached"] == ["consec_losses"]
    assert db.pages[page_id]["decision"] == "demote" and db.pages[page_id]["decided_by"] == OPERATOR
    assert db.episodes[("magna53", _NIGHT1)]["closed_by"] == "demote"
    assert "magna53" in answer and "live" in answer and "paper" in answer
    # the lock, the phase read, the CAS write and the decision all sit in ONE transaction
    assert db.txn == ["begin", "commit"]


def test_double_press_moves_one_rung_total(monkeypatch):
    db, page_id = _paged(monkeypatch)
    first = _press("demote", page_id)
    second = _press("demote", page_id)
    assert db.strategies["magna53"]["phase"] == "paper", "a second press must not take it to shadow"
    assert len(db.phase_writes) == 1
    assert "already decided" in second and "demote" in second
    assert first != second
    assert len(db.audit_rows("strategy_phase_change")) == 1
    from agents.market_intelligence import ladder_press as lp
    assert len(db.audit_rows(lp.REFUSED_EVENT)) == 1


def test_stale_press_refuses_when_the_strategy_moved_since_the_page(monkeypatch):
    """A typed `/strategy magna53 demote` after the page was sent: the page shows `live`, the row
    says `paper` — the press must move nothing (it would otherwise take it to shadow)."""
    db, page_id = _paged(monkeypatch)
    db.strategies["magna53"]["phase"] = "paper"
    answer = _press("demote", page_id)
    assert db.strategies["magna53"]["phase"] == "paper"
    assert db.phase_writes == []
    assert "moved" in answer and "live" in answer and "paper" in answer
    assert db.pages[page_id]["decision"] == "stale"
    from agents.market_intelligence import ladder_press as lp
    assert len(db.audit_rows(lp.REFUSED_EVENT)) == 1
    assert db.audit_rows("strategy_phase_change") == []


def test_a_concurrent_move_between_the_read_and_the_write_is_refused_by_the_cas(monkeypatch):
    """The read inside the transaction still says `live`, but by the time the compare-and-set
    UPDATE runs the row is `paper`: the UPDATE matches no row, the handler refuses, nothing moves."""
    db, page_id = _paged(monkeypatch)
    db.current_phase_override["magna53"] = "live"
    db.strategies["magna53"]["phase"] = "paper"
    answer = _press("demote", page_id)
    assert db.strategies["magna53"]["phase"] == "paper" and db.phase_writes == []
    assert "moved" in answer and db.pages[page_id]["decision"] == "stale"


def test_no_action_press_moves_nothing_and_audits(monkeypatch):
    from agents.market_intelligence import ladder_press as lp
    db, page_id = _paged(monkeypatch)
    answer = _press("noaction", page_id)
    assert db.strategies["magna53"]["phase"] == "live" and db.phase_writes == []
    assert db.pages[page_id]["decision"] == "no_action" and db.pages[page_id]["decided_by"] == OPERATOR
    rows = db.audit_rows(lp.NO_ACTION_EVENT)
    assert len(rows) == 1 and f"page #{page_id}" in rows[0][0]
    d = json.loads(rows[0][1])
    assert d["pressed_by"] == OPERATOR and d["page_id"] == page_id and d["pressed_at"]
    assert "No action" in answer and "live" in answer
    assert db.episodes[("magna53", _NIGHT1)]["closed_on"] is None     # the episode stays open


def test_no_action_then_demote_on_the_same_page_is_refused(monkeypatch):
    db, page_id = _paged(monkeypatch)
    _press("noaction", page_id)
    answer = _press("demote", page_id)
    assert db.strategies["magna53"]["phase"] == "live" and db.phase_writes == []
    assert "already decided" in answer


def test_an_unauthorized_press_is_refused_by_the_market_agent_too(monkeypatch):
    """Defence in depth behind the channel gate: the market agent checks the pressing user
    against the same allowlist the pages are sent to."""
    from agents.market_intelligence import ladder_press as lp
    db, page_id = _paged(monkeypatch)
    answer = _press("demote", page_id, user_id=999)
    assert db.strategies["magna53"]["phase"] == "live" and db.phase_writes == []
    assert db.pages[page_id]["decision"] is None          # the page stays pressable by him
    assert "not authorized" in answer.lower()
    assert len(db.audit_rows(lp.REFUSED_EVENT)) == 1


def test_an_unknown_page_or_action_refuses(monkeypatch):
    db, page_id = _paged(monkeypatch)
    assert "no such page" in _press("demote", page_id + 500).lower()
    assert "unknown action" in _press("promote", page_id).lower()
    assert db.phase_writes == []


def test_update_strategy_compare_and_set_refuses_a_moved_phase(monkeypatch):
    """The registry's one phase writer, with `expect_phase`: it moves the row only if the phase is
    still the one the caller saw, and reports None otherwise. Without `expect_phase` it behaves as
    before (the typed commands)."""
    db = LadderFakeDb(strategies=[strategy_row("magna53", "live", live_real=True)]).wire(monkeypatch)
    moved = asyncio.run(registry.update_strategy("magna53", phase="paper", expect_phase="shadow"))
    assert moved is None and db.strategies["magna53"]["phase"] == "live"
    moved = asyncio.run(registry.update_strategy("magna53", phase="paper", expect_phase="live"))
    assert moved is not None and moved.phase == "paper" and db.strategies["magna53"]["phase"] == "paper"
    plain = asyncio.run(registry.update_strategy("magna53", phase="shadow"))
    assert plain.phase == "shadow"


# ── the two transports ─────────────────────────────────────────────────────────────────────────

from channels.telegram import TelegramChannel  # noqa: E402
from tests.conftest import fake_httpx_client  # noqa: E402


def _make_channel():
    channel = TelegramChannel.__new__(TelegramChannel)
    channel._secrets = SimpleNamespace(telegram_allowed_user_ids=[OPERATOR], internal_api_secret="s")
    return channel


def _cb_update(data, user_id=OPERATOR):
    query = SimpleNamespace(data=data, from_user=SimpleNamespace(id=user_id), answer=AsyncMock(),
                            message=SimpleNamespace(reply_text=AsyncMock()))
    return SimpleNamespace(callback_query=query)


@pytest.mark.asyncio
async def test_an_unauthorized_press_is_refused_at_the_channel_gate():
    """THE load-bearing check (#651's): a callback query is a separate update type from a text
    message and does not inherit the message allowlist — a stranger's tap on Demote must be
    refused before the market agent is ever reached."""
    channel = _make_channel()
    channel._handle_ladder_callback = AsyncMock()
    update = _cb_update("ladder:demote:17", user_id=999)
    await channel._handle_callback_query(update, None)
    channel._handle_ladder_callback.assert_not_awaited()
    update.callback_query.answer.assert_awaited_once_with("Unauthorized")


@pytest.mark.asyncio
async def test_an_authorized_press_dispatches_to_the_ladder_callback():
    channel = _make_channel()
    channel._handle_ladder_callback = AsyncMock()
    update = _cb_update("ladder:noaction:17")
    await channel._handle_callback_query(update, None)
    channel._handle_ladder_callback.assert_awaited_once()
    assert channel._handle_ladder_callback.await_args.args[1] == "ladder:noaction:17"


@pytest.mark.asyncio
async def test_the_ladder_callback_posts_the_press_to_the_market_agent_and_replies(monkeypatch):
    monkeypatch.delenv("INTERNAL_API_SECRET", raising=False)
    monkeypatch.setattr("core.router.auth_headers", lambda: {"X-Apollo-Secret": "test"})
    monkeypatch.setattr("shared.registry.get_agent_url", lambda name: "http://market-agent:9000")
    monkeypatch.setattr("core.router.get_agent_url", lambda name: "http://market-agent:9000")
    fake_client = fake_httpx_client(json_body={
        "request_id": "rid", "agent": "market_intelligence", "success": True,
        "result": "Demoted: magna53 moved from live to paper (page #17).",
    })
    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    channel = _make_channel()
    query = SimpleNamespace(data="ladder:demote:17", from_user=SimpleNamespace(id=OPERATOR),
                            message=SimpleNamespace(reply_text=AsyncMock()))
    await channel._handle_ladder_callback(query, "ladder:demote:17")
    posted = fake_client.last_post["kwargs"]["json"]
    assert posted["task"] == "/ladder_press demote 17" and posted["user_id"] == OPERATOR
    query.message.reply_text.assert_awaited_once()
    assert query.message.reply_text.await_args.kwargs["parse_mode"] == "HTML"
    assert "magna53" in query.message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_a_malformed_ladder_button_never_reaches_the_market_agent(monkeypatch):
    channel = _make_channel()
    channel._post_market_task = AsyncMock()
    query = SimpleNamespace(data="ladder:demote:abc", from_user=SimpleNamespace(id=OPERATOR),
                            message=SimpleNamespace(reply_text=AsyncMock()))
    await channel._handle_ladder_callback(query, "ladder:demote:abc")
    channel._post_market_task.assert_not_awaited()
    query.message.reply_text.assert_awaited_once()


def _request(text, user_id=OPERATOR):
    return SimpleNamespace(task=text, user_id=user_id)


@pytest.mark.asyncio
async def test_the_market_agent_dispatches_ladder_press_not_unknown_command():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    agent = MarketIntelligenceAgent()
    sentinel = object()
    with patch.object(agent, "_handle_ladder_press", new=AsyncMock(return_value=sentinel)) as h:
        resp = await agent._handle_slash_command(_request("/ladder_press demote 17"))
    assert resp is sentinel
    h.assert_awaited_once()


@pytest.mark.asyncio
async def test_the_market_agent_handler_passes_the_pressing_user_and_page(monkeypatch):
    from agents.market_intelligence import ladder_press as lp
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    handle = AsyncMock(return_value="done")
    monkeypatch.setattr(lp, "handle_ladder_press", handle)
    agent = SimpleNamespace(_ok=lambda req, *, result: SimpleNamespace(success=True, result=result),
                            _error=lambda req, err: SimpleNamespace(success=False, error=err))
    resp = await MarketIntelligenceAgent._handle_ladder_press(agent, _request("/ladder_press noaction 17", 42))
    assert resp.result == "done"
    assert handle.await_args.args == ("noaction", 17) and handle.await_args.kwargs == {"user_id": 42}
    bad = await MarketIntelligenceAgent._handle_ladder_press(agent, _request("/ladder_press 17"))
    assert "Malformed" in bad.result and handle.await_count == 1


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# C — an open LIVE position stays managed on the LIVE account after the demote
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Invariant pins, not red-first tests: today's exit and stop paths read `trade["account_mode"]`
# (order_manager.execute_full_exit:5855, live_tracker.morning_stop_refresh:2084,
# update_open_positions_live:1117, scan_profit_triggers:10128 select it, sync_positions iterates
# the modes). They pass on today's code; the mutation that reds them is "resolve the mode from
# the strategy's phase (the registry) instead of the row" — which, after a demote, would look a
# live position up on the PAPER book. The registry here says `paper` and the process default is
# `paper`, so only the ROW can say `live`.


def _registry_says_paper(monkeypatch):
    from agents.market_intelligence.strategies.registry import Strategy
    demoted = Strategy(strategy_id="magna53", name="magna53", family="orb_long", phase="paper", enabled=True,
                       signal_type="magna53", outcomes_table="mi_live_trades", promotion_model="unpaired_r",
                       promotion_thresholds={}, live_real_enabled=True)
    monkeypatch.setattr(registry, "_CACHE", {"magna53": demoted})
    monkeypatch.setattr(registry, "get_strategy", AsyncMock(return_value=demoted))
    return demoted


@pytest.mark.asyncio
async def test_a_live_positions_full_exit_still_sells_on_the_live_account_after_demote(monkeypatch):
    from contextlib import asynccontextmanager
    from agents.market_intelligence.broker import order_manager as om
    _registry_says_paper(monkeypatch)
    trade = {"id": 382, "ticker": "OKTA", "remaining_shares": 2, "stop_price": 165.57,
             "stop_order_id": "stop-1", "account_mode": "live", "signal_type": "magna53"}

    class _Conn:
        async def fetchrow(self, q, *a):
            return trade if "mi_live_trades" in q else None
        async def fetch(self, q, *a, **k):
            return []
        async def execute(self, *a, **k):
            return "UPDATE 1"
        async def fetchval(self, *a, **k):
            return None

    class _Acq:
        async def __aenter__(self): return _Conn()
        async def __aexit__(self, *a): return False

    class _Pool:
        def acquire(self, *a, **k): return _Acq()

    @asynccontextmanager
    async def _lock(trade_id):
        yield

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=_Pool()))
    monkeypatch.setattr(om, "_trade_advisory_lock", _lock)
    monkeypatch.setattr(om, "current_account_mode", lambda: "paper")       # the prod default: a fallback would be CAUGHT
    monkeypatch.setattr(om, "send_telegram_message", AsyncMock(return_value=True))
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock(return_value=True))
    monkeypatch.setattr(om, "mode_prefix", lambda m: "")
    cancel = AsyncMock(return_value=True)
    close = AsyncMock(return_value={"id": "sell-1"})
    monkeypatch.setattr(om.alpaca, "cancel_order", cancel)
    monkeypatch.setattr(om.alpaca, "close_position", close)
    monkeypatch.setattr(om.alpaca, "place_stop_order", AsyncMock(return_value={"id": "stop-2"}))
    monkeypatch.setattr(om.alpaca, "get_position", AsyncMock(return_value={"qty": 2, "qty_available": 2}))
    monkeypatch.setattr(om.alpaca, "get_all_positions", AsyncMock(return_value=[
        {"symbol": "OKTA", "qty": 2, "qty_available": 2}]))
    monkeypatch.setattr(om.alpaca, "get_open_orders", AsyncMock(return_value=[]))
    monkeypatch.setattr(om, "_EXIT_RELEASE_SLEEP_S", 0)
    monkeypatch.setattr(om, "_RESTORE_RETRY_SLEEP_S", 0)

    ok = await om.execute_full_exit(382, "sma_trail_stop")
    assert ok is True
    assert cancel.await_args.kwargs.get("account_mode") == "live"
    assert close.await_args.kwargs.get("account_mode") == "live"
    registry.get_strategy.assert_not_awaited()          # the exit never consults the registry


@pytest.mark.asyncio
async def test_a_live_positions_stop_is_checked_on_the_live_account_after_demote(monkeypatch):
    from agents.market_intelligence.broker import live_tracker as lt
    from tests.conftest import make_mock_pool
    _registry_says_paper(monkeypatch)
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[{"id": 382, "ticker": "OKTA", "remaining_shares": 2,
                                          "stop_price": 165.57, "stop_order_id": "stop-1",
                                          "account_mode": "live"}])
    get_order = AsyncMock(return_value={"status": "new"})
    update_stop = AsyncMock()
    monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(lt, "et_today", lambda: dt.date(2026, 10, 16))
    monkeypatch.setattr(lt.alpaca, "get_order", get_order)
    monkeypatch.setattr(lt, "update_stop", update_stop)
    monkeypatch.setattr(lt, "get_same_day_excluded_stop_candidates", AsyncMock(return_value=[]))
    monkeypatch.setattr(lt, "log_audit_event", AsyncMock())
    await lt.morning_stop_refresh()
    assert get_order.await_args.args[0] == "stop-1"
    assert get_order.await_args.kwargs.get("account_mode") == "live"
    update_stop.assert_not_awaited()                     # the live stop is still active → left alone
    registry.get_strategy.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# D — structure
# ═══════════════════════════════════════════════════════════════════════════════════════════════

ROOTS = ("agents", "core", "channels", "shared")


def _calls_with_phase(tree):
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
        if name != "update_strategy" or not any(k.arg == "phase" for k in node.keywords):
            continue
        cur, fn = node, None
        while cur in parents:
            cur = parents[cur]
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn = cur.name
                break
        yield fn


_DB_VERBS = {"execute", "executemany", "fetch", "fetchrow", "fetchval"}


def _raw_phase_updates(tree):
    """Every string constant reading `UPDATE mi_strategies … phase …` that is handed DIRECTLY to a
    DB verb (`conn.execute(<sql>)` etc.) — a raw phase write, as opposed to a message or a comment."""
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Constant) and isinstance(n.value, str)):
            continue
        flat = " ".join(n.value.lower().split())
        if "update mi_strategies" not in flat or "phase" not in flat:
            continue
        parent = parents.get(n)
        if isinstance(parent, ast.Call) and n in parent.args:
            f = parent.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name in _DB_VERBS:
                yield flat


def test_only_the_operators_three_paths_write_a_phase():
    """DERIVED over every production module: a call to the one phase writer carrying `phase=`
    exists in exactly three functions — the typed promote, the typed demote and the Demote
    button's handler — all three reached only by his message or his press. A raw phase UPDATE
    handed to a DB verb exists in the writer itself and in db.py's boot migration — which may
    only converge a retired row to the TERMINAL 'deprecated' phase (#424; dual_account.md names
    it), never to shadow / paper / live."""
    # source-pin-ok: the NON-existence of a fourth phase writer anywhere in the codebase cannot be
    # exercised by calling anything — the population of callers is only decidable from the source.
    found = set()
    raw_by_file: dict[str, list[str]] = {}
    mentions = set()
    for root in ROOTS:
        for p in sorted((REPO / root).rglob("*.py")):
            src = p.read_text(encoding="utf-8")
            rel = str(p.relative_to(REPO))
            tree = ast.parse(src)
            if "update_strategy" in src:
                for fn in _calls_with_phase(tree):
                    found.add((rel, fn))
            for flat in _raw_phase_updates(tree):
                raw_by_file.setdefault(rel, []).append(flat)
            if "update mi_strategies" in " ".join(src.lower().split()):
                mentions.add(rel)
    assert found == {
        ("agents/market_intelligence/strategies/telegram.py", "_do_promote"),
        ("agents/market_intelligence/strategies/telegram.py", "_do_demote"),
        ("agents/market_intelligence/ladder_press.py", "_demote_on_page"),
    }, found
    # The coarse net (any spelling, built any way): the writer, the boot migration (+ a comment
    # about the operator's own hand UPDATE), and one error message that SUGGESTS SQL to him.
    assert mentions == {"agents/market_intelligence/strategies/registry.py",
                        "agents/market_intelligence/db.py",
                        "agents/market_intelligence/agent.py"}, sorted(mentions)
    # The precise net: a phase UPDATE handed straight to a DB verb exists only in db.py's boot
    # migration, and may only set the terminal phase. (registry.py builds its UPDATE as an
    # f-string in a local — the coarse net covers it; its CAS semantics are pinned above.)
    assert set(raw_by_file) == {"agents/market_intelligence/db.py"}, sorted(raw_by_file)
    for flat in raw_by_file["agents/market_intelligence/db.py"]:
        assert "set phase = 'deprecated'" in flat, f"db.py writes a non-terminal phase raw: {flat}"
    reg = (REPO / "agents/market_intelligence/strategies/registry.py").read_text(encoding="utf-8")
    assert "UPDATE mi_strategies SET" in reg and "expect_phase" in reg


def test_the_watchdog_module_still_cannot_move_a_phase():
    """The nightly pass pages; it never writes a phase. Pinned by name AND by string."""
    # source-pin-ok: the absence of a code path cannot be exercised; the runtime tests above prove
    # no phase write happened, this proves none could.
    src = Path(lw.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "update_strategy" not in names | attrs
    assert "mi_strategies" not in src.split('"""', 2)[2].lower().replace("`mi_strategies`", "")


def test_the_allocator_zeroing_invariant_is_vacuous_until_the_l3_store_exists():
    """ADR 0022 §2: 'a demotion zeroes the pending proposal for that strategy'. There is no
    `allocation_proposals` store — L3 is unbuilt (grep: zero production hits) — so there is nothing
    to zero and the Demote handler records exactly that. THE DAY L3 LANDS THIS TEST FAILS: wire the
    zeroing into `ladder_press._demote_on_page` and then widen the allowance here."""
    # source-pin-ok: whether a proposal store EXISTS is a property of the codebase, not of any call.
    hits = set()
    for root in ROOTS:
        for p in sorted((REPO / root).rglob("*.py")):
            src = p.read_text(encoding="utf-8")
            if "allocation_proposal" in src:
                hits.add(str(p.relative_to(REPO)))
    assert hits == {"agents/market_intelligence/ladder_press.py"}, (
        f"an allocation_proposals store now exists in {sorted(hits)} — ADR 0022 §2 requires the "
        f"Demote press to zero the demoted strategy's pending proposal: wire it in ladder_press")


def test_the_ddl_is_applied_at_schema_init_and_names_both_tables():
    # source-pin-ok: there is no Postgres in the test environment to run the schema init against;
    # that the init EXECUTES this DDL is decidable only from its source (the _BREAKOUT_V1_DDL precedent).
    import agents.market_intelligence.db as dbmod
    ddl = dbmod._LADDER_DDL
    assert "CREATE TABLE IF NOT EXISTS mi_ladder_pages" in ddl
    assert "CREATE TABLE IF NOT EXISTS mi_ladder_episodes" in ddl
    assert "UNIQUE (strategy_id, as_of)" in ddl
    src = Path(dbmod.__file__).read_text(encoding="utf-8")
    assert "await conn.execute(_LADDER_DDL)" in src
