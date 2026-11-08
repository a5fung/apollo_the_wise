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
from tests._ladder_fake_db import LadderFakeDb, operator_env, strategy_row
from tests._ladder_fake_db import closed_rows as _closed_rows
from tests._ladder_fake_db import rs as _rs

REPO = Path(__file__).resolve().parents[1]
_NIGHT1 = dt.date(2026, 10, 15)
_NIGHT2 = dt.date(2026, 10, 16)
_NIGHT3 = dt.date(2026, 10, 19)
OPERATOR = 42


STREAK_BREACH = _rs(2.0, 20) + _rs(-1.0, 6)                 # streak 6 · last-20 +1.10R · dd −6.00R
TRIPLE_BREACH = _rs(2.0, 10) + [-1.0, 0.5] * 20 + _rs(-1.0, 6)   # streak 6 · last-20 −0.475R · dd −16R
CLEAR = [1.5, -1.0, 2.0, -1.0, -1.0, 3.0] * 5


@pytest.fixture(autouse=True)
def _operator_env(monkeypatch):
    operator_env(monkeypatch, OPERATOR)


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


def _press(db, action, page_id, user_id=OPERATOR, token="page"):
    """`token="page"` (the default) = the page's own button token, what a real button press carries
    (#312 review: a press without it is refused). Anything else is passed as given."""
    from agents.market_intelligence.ladder_press import handle_ladder_press
    if token == "page":
        token = db.pages[page_id]["token"] if page_id in db.pages else None
    return asyncio.run(handle_ladder_press(action, page_id, user_id=user_id, token=token))


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
    token = db.token_of(page_id)
    assert [b["callback_data"] for b in btns] == [f"ladder:demote:{page_id}:{token}",
                                                  f"ladder:noaction:{page_id}:{token}"]
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
    assert "already decided" not in _press(db, "noaction", detail1["paged"][0]["page_id"])
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
    _press(db, "noaction", detail1["paged"][0]["page_id"])
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
    kb = lw.build_ladder_keyboard(7, "shadow", "tok")
    assert [b["callback_data"] for row in kb["inline_keyboard"] for b in row] == ["ladder:noaction:7:tok"]
    assert [b["text"] for row in lw.build_ladder_keyboard(7, "paper", "tok")["inline_keyboard"] for b in row][0] \
        == "⬇️ Demote to shadow"
    assert [b["text"] for row in lw.build_ladder_keyboard(7, "live", "tok")["inline_keyboard"] for b in row][0] \
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
    answer = _press(db, "demote", page_id)
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
    first = _press(db, "demote", page_id)
    second = _press(db, "demote", page_id)
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
    answer = _press(db, "demote", page_id)
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
    answer = _press(db, "demote", page_id)
    assert db.strategies["magna53"]["phase"] == "paper" and db.phase_writes == []
    assert "moved" in answer and db.pages[page_id]["decision"] == "stale"


def test_no_action_press_moves_nothing_and_audits(monkeypatch):
    from agents.market_intelligence import ladder_press as lp
    db, page_id = _paged(monkeypatch)
    answer = _press(db, "noaction", page_id)
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
    _press(db, "noaction", page_id)
    answer = _press(db, "demote", page_id)
    assert db.strategies["magna53"]["phase"] == "live" and db.phase_writes == []
    assert "already decided" in answer


def test_an_unauthorized_press_is_refused_by_the_market_agent_too(monkeypatch):
    """Defence in depth behind the channel gate: the market agent checks the pressing user
    against the same allowlist the pages are sent to."""
    from agents.market_intelligence import ladder_press as lp
    db, page_id = _paged(monkeypatch)
    answer = _press(db, "demote", page_id, user_id=999)
    assert db.strategies["magna53"]["phase"] == "live" and db.phase_writes == []
    assert db.pages[page_id]["decision"] is None          # the page stays pressable by him
    assert "not authorized" in answer.lower()
    assert len(db.audit_rows(lp.REFUSED_EVENT)) == 1


def test_an_unknown_page_or_action_refuses(monkeypatch):
    db, page_id = _paged(monkeypatch)
    assert "no such page" in _press(db, "demote", page_id + 500).lower()
    assert "unknown action" in _press(db, "promote", page_id).lower()
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
    update = _cb_update("ladder:demote:17:abcdefgh1234", user_id=999)
    await channel._handle_callback_query(update, None)
    channel._handle_ladder_callback.assert_not_awaited()
    update.callback_query.answer.assert_awaited_once_with("Unauthorized")


@pytest.mark.asyncio
async def test_an_authorized_press_dispatches_to_the_ladder_callback():
    channel = _make_channel()
    channel._handle_ladder_callback = AsyncMock()
    update = _cb_update("ladder:noaction:17:abcdefgh1234")
    await channel._handle_callback_query(update, None)
    channel._handle_ladder_callback.assert_awaited_once()
    assert channel._handle_ladder_callback.await_args.args[1] == "ladder:noaction:17:abcdefgh1234"


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
    query = SimpleNamespace(data="ladder:demote:17:abcdefgh1234", from_user=SimpleNamespace(id=OPERATOR),
                            message=SimpleNamespace(reply_text=AsyncMock()))
    await channel._handle_ladder_callback(query, "ladder:demote:17:abcdefgh1234")
    posted = fake_client.last_post["kwargs"]["json"]
    assert posted["task"] == "/ladder_press demote 17 abcdefgh1234" and posted["user_id"] == OPERATOR
    query.message.reply_text.assert_awaited_once()
    assert query.message.reply_text.await_args.kwargs["parse_mode"] == "HTML"
    assert "magna53" in query.message.reply_text.await_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("data", ["ladder:demote:abc:abcdefgh1234", "ladder:demote:17", "ladder:demote:17:x",
                                  "ladder:demote:17:bad token!"])
async def test_a_malformed_ladder_button_never_reaches_the_market_agent(monkeypatch, data):
    """Including a button WITHOUT the page's token (#312 review): the channel drops it before the
    market agent is asked."""
    channel = _make_channel()
    channel._post_market_task = AsyncMock()
    query = SimpleNamespace(data=data, from_user=SimpleNamespace(id=OPERATOR),
                            message=SimpleNamespace(reply_text=AsyncMock()))
    await channel._handle_ladder_callback(query, data)
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
        resp = await agent._handle_slash_command(_request("/ladder_press demote 17 abcdefgh1234"))
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
    resp = await MarketIntelligenceAgent._handle_ladder_press(
        agent, _request("/ladder_press noaction 17 abcdefgh1234", 42))
    assert resp.result == "done"
    assert handle.await_args.args == ("noaction", 17)
    assert handle.await_args.kwargs == {"user_id": 42, "token": "abcdefgh1234"}
    # A press WITHOUT a token is handed over with token=None — the press handler refuses and audits
    # it (the refusal is the record), rather than this layer answering "malformed" silently.
    await MarketIntelligenceAgent._handle_ladder_press(agent, _request("/ladder_press noaction 17", 42))
    assert handle.await_args.kwargs == {"user_id": 42, "token": None} and handle.await_count == 2
    bad = await MarketIntelligenceAgent._handle_ladder_press(agent, _request("/ladder_press 17"))
    assert "Malformed" in bad.result and handle.await_count == 2


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


def _update_strategy_calls(tree):
    """Every call of the one writer `update_strategy` in `tree`, whatever it passes — `phase=`, `enabled=`,
    `live_real_enabled=`, or a `**kw` splat (final review 2026-11-07, finding 3: the pin used to see `phase=`
    calls only, so an `enabled=` or `**kw` writer elsewhere passed the suite) → (enclosing function, carries
    `phase=`)."""
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
        if name != "update_strategy":
            continue
        cur, fn = node, None
        while cur in parents:
            cur = parents[cur]
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn = cur.name
                break
        yield fn, any(k.arg == "phase" for k in node.keywords)


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


def _called_names(fn: ast.AST) -> set[str]:
    out = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            out.add(f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None)
    out.discard(None)
    return out


def test_only_the_operators_three_paths_write_a_phase():
    """DERIVED over every production module: EVERY call of the one writer `update_strategy` — whatever
    it passes (final review 2026-11-07, finding 3: the pin used to match `phase=` calls only) — exists
    in exactly four functions: the typed promote and demote (phase), the typed enable / disable (the
    enabled flag) and the Demote button's handler (phase) — all four reached only by his typed command
    or his press. The three that carry `phase=` are the phase writers. A raw phase UPDATE handed to a
    DB verb exists in the writer itself and in db.py's boot migration — which may only converge a
    retired row to the TERMINAL 'deprecated' phase (#424; dual_account.md names it), never to
    shadow / paper / live.

    And the typed ones sit behind the origin gate (#312 round 3, his ruling 2026-11-07 "Close it"):
    every function in `strategies/telegram.py` that calls `update_strategy` at all — the two phase
    writers AND the enabled-flag writer, derived, not listed — is called from exactly one place,
    `handle_strategy_action`, whose `origin` parameter is keyword-only with a default that refuses
    (a caller that forgets it cannot move anything). The behavioural proof that the gate acts is
    `tests/test_312_strategy_command_origin.py`; this proves nothing stands beside it."""
    # source-pin-ok: the NON-existence of a fifth writer anywhere in the codebase cannot be
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
                for fn, with_phase in _update_strategy_calls(tree):
                    found.add((rel, fn, with_phase))
            for flat in _raw_phase_updates(tree):
                raw_by_file.setdefault(rel, []).append(flat)
            if "update mi_strategies" in " ".join(src.lower().split()):
                mentions.add(rel)
    TELEGRAM, PRESS = "agents/market_intelligence/strategies/telegram.py", "agents/market_intelligence/ladder_press.py"
    assert found == {
        (TELEGRAM, "_do_promote", True),
        (TELEGRAM, "_do_demote", True),
        (TELEGRAM, "_do_enable_disable", False),       # the enabled flag — no phase
        (PRESS, "_demote_on_page", True),
    }, found
    assert {(rel, fn) for rel, fn, with_phase in found if with_phase} == {
        (TELEGRAM, "_do_promote"), (TELEGRAM, "_do_demote"), (PRESS, "_demote_on_page")}
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
    # the typed writers behind the one gated dispatcher (round 3)
    tree = ast.parse((REPO / "agents/market_intelligence/strategies/telegram.py").read_text(encoding="utf-8"))
    fns = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    writers = {name for name, fn in fns.items() if "update_strategy" in _called_names(fn)}
    assert writers == {"_do_enable_disable", "_do_promote", "_do_demote"}, writers
    for w in writers:
        callers = {name for name, fn in fns.items() if w in _called_names(fn)}
        assert callers == {"handle_strategy_action"}, (w, callers)
    gate = fns["handle_strategy_action"]
    kw = {a.arg: d for a, d in zip(gate.args.kwonlyargs, gate.args.kw_defaults)}
    assert "origin" in kw and isinstance(kw["origin"], ast.Constant) and kw["origin"].value is None, kw


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
    assert "token" in ddl and "ADD COLUMN IF NOT EXISTS token" in ddl     # the page's own button token (#312 review)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# E — the #312 review's findings (2026-11-07), each red on the pre-review build fa36a4fd
# ═══════════════════════════════════════════════════════════════════════════════════════════════
#
#   1. his Demote did not stop NEW entries until apollo-execution restarted (a per-process cache);
#   2. `/ladder_press` was reachable from the orchestrator's LLM with his user id (THE LINE);
#   3. the press could answer "Demoted" when the transaction had silently rolled back;
#   4. a strategy that left the ladder kept its episode open, so its return never paged;
#   5. a press on an ended episode still demoted on stale numbers;
#   6. one Telegram blip cost a trading day (no retry inside the run); an unsent page was "no such page";
#   7. a press racing the nightly run paged the rung the strategy had just left.
# (8, the webhook secret, is tests/test_telegram_webhook_secret.py.)


def _live_strategy(**over):
    base = dict(strategy_row("magna53", "live", live_real=True))
    base.update(over)
    return registry.Strategy(**base)


def test_a_demote_committed_in_the_market_agent_is_seen_by_the_execution_processs_next_read(monkeypatch):
    """Finding 1 at the registry: two processes, two caches, ONE database. Process B (apollo-execution,
    a second copy of the registry module with its own `_CACHE`, warmed at its boot) never learns of
    the demote process A (the market agent, his press) commits — `get_strategy` there still says live.
    The money path therefore reads `get_strategy_fresh`, which answers from the committed row."""
    import importlib.util
    import sys
    db = LadderFakeDb(strategies=[strategy_row("magna53", "live", live_real=True)]).wire(monkeypatch)
    spec = importlib.util.spec_from_file_location("registry_in_apollo_execution", registry.__file__)
    execution = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, execution)      # dataclasses resolves annotations by module name
    spec.loader.exec_module(execution)
    execution.get_pool = AsyncMock(return_value=db.pool)                      # the same database
    assert asyncio.run(execution.get_strategy("magna53")).phase == "live"     # warmed at its boot

    # process A — his press commits paper (the compare-and-set writer, as the press calls it)
    assert asyncio.run(registry.update_strategy("magna53", phase="paper", expect_phase="live")).phase == "paper"
    assert db.strategies["magna53"]["phase"] == "paper"

    # process B — the hole the review named: its cache still serves live to a new entry
    assert asyncio.run(execution.get_strategy("magna53")).phase == "live"
    # the fix: the fresh read is the committed row, no restart
    fresh = asyncio.run(execution.get_strategy_fresh("magna53"))
    assert fresh.phase == "paper" and fresh.strategy_id == "magna53"
    assert asyncio.run(execution.get_strategy_fresh("no_such_strategy")) is None   # unregistered: fail-open None


def test_the_fresh_read_is_bounded_on_the_acquire_and_on_the_query(monkeypatch):
    """Re-review 2026-11-07 finding 5: `get_strategy_fresh` runs at 09:31 in front of EVERY entry (the funnel, both
    paper lanes, the batch's dedup book), and it had no timeout on the acquire or the SELECT — a hung database made
    the entry HANG rather than skip fail-closed. The bound is asyncpg's own `timeout=` on both (the #621 path, as
    `log_audit_event` and the open-floor read do — never `asyncio.wait_for` around a pooled call). RED before the
    fix: neither call carried the kwarg."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=strategy_row("magna53", "paper", live_real=True))
    monkeypatch.setattr(registry, "get_pool", AsyncMock(return_value=pool))
    assert asyncio.run(registry.get_strategy_fresh("magna53")).phase == "paper"
    assert pool.acquire.call_args.kwargs.get("timeout") == registry.FRESH_READ_TIMEOUT_S
    assert conn.fetchrow.call_args.kwargs.get("timeout") == registry.FRESH_READ_TIMEOUT_S
    assert 0 < registry.FRESH_READ_TIMEOUT_S <= 10                   # bounded, and short enough for the 09:31 open


@pytest.mark.asyncio
async def test_a_fresh_read_timeout_is_the_same_fail_closed_skip_and_page_as_any_read_error(monkeypatch):
    """Finding 5, the behaviour the bound buys: asyncpg answers a fired `timeout=` with `asyncio.TimeoutError`, an
    `Exception` — so the funnel's one read path treats it exactly like a connection error: the entry is SKIPPED
    `infra:strategy_unreadable` before the dedup SELECT, the safeguards and the builder, and paged (infra pages even
    for a batching caller). Nothing is routed on the stale process cache (LIVE here). This pins the contract the
    timeout joins; it held before the fix too (a timeout was already an Exception) — the red-first test for the
    finding is the kwargs one above."""
    from agents.market_intelligence.broker import entry_pipeline as ep
    from agents.market_intelligence.broker import live_tracker as lt
    from tests.conftest import make_mock_pool

    monkeypatch.setattr(registry, "_CACHE", {"magna53": _live_strategy()})     # the stale cache: never consulted
    reg_pool, reg_conn = make_mock_pool()
    reg_conn.fetchrow = AsyncMock(side_effect=asyncio.TimeoutError("statement timeout"))
    monkeypatch.setattr(registry, "get_pool", AsyncMock(return_value=reg_pool))
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(side_effect=AssertionError("the dedup SELECT must not run after a failed read"))
    conn.execute = AsyncMock()
    monkeypatch.setattr(ep, "get_pool", AsyncMock(return_value=pool))
    audits = []

    async def _audit(ev, summary, detail="", **kw):
        audits.append(ev)
        return True
    monkeypatch.setattr(ep, "log_audit_event", _audit)
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(ep, "send_telegram_message", sent)
    monkeypatch.setattr(ep, "current_account_mode", lambda: "paper")
    monkeypatch.setattr(lt, "_insert_skipped_trade", AsyncMock())
    safeguards = AsyncMock(side_effect=AssertionError("the safeguards must not run after a failed read"))
    monkeypatch.setattr(lt, "_check_safeguards", safeguards)

    async def _spec_builder(*_a, **_k):
        raise AssertionError("skipped at the read; the builder must not run")

    out = await ep.submit_trade_entry(
        alert_context={"ticker": "OKTA", "ep_score": 80, "catalyst_quality": "strong", "gap_pct": 12.0},
        spec_builder=_spec_builder, regime_record=None, strategy_label="ORB", signal_type="magna53",
        today=dt.date(2026, 11, 9), aggregate_skips=True)
    assert out["action"] == ep.ACTION_SKIPPED
    assert out["reason"].startswith("infra:strategy_unreadable") and "TimeoutError" in out["reason"]
    assert safeguards.await_count == 0 and conn.fetchval.await_count == 0
    assert "strategy_mode_resolve_error" in audits and sent.await_count == 1   # loud: the audit row and the page


@pytest.mark.asyncio
async def test_the_entry_funnel_routes_on_the_committed_phase_not_the_process_cache(monkeypatch):
    """Finding 1 at the entry funnel: the process cache says LIVE (apollo-execution's copy, never
    invalidated by a press in the market agent), the committed row says PAPER. The funnel's dedup
    book and the safeguards' account must be PAPER — on fa36a4fd both read the cache and were live."""
    from agents.market_intelligence.broker import entry_pipeline as ep
    from agents.market_intelligence.broker import live_tracker as lt
    from tests.conftest import make_mock_pool

    monkeypatch.setattr(registry, "_CACHE", {"magna53": _live_strategy()})     # the stale cache
    reg_pool, reg_conn = make_mock_pool()
    reg_conn.fetchrow = AsyncMock(return_value=strategy_row("magna53", "paper", live_real=True))   # the committed row
    monkeypatch.setattr(registry, "get_pool", AsyncMock(return_value=reg_pool))
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(side_effect=[False, None])                       # no duplicate, no open position
    conn.execute = AsyncMock()
    monkeypatch.setattr(ep, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ep, "log_audit_event", AsyncMock())
    monkeypatch.setattr(ep, "send_telegram_message", AsyncMock(return_value=True))
    monkeypatch.setattr(ep, "current_account_mode", lambda: "paper")
    monkeypatch.setattr(lt, "_insert_skipped_trade", AsyncMock())
    safeguards = AsyncMock(return_value=(False, "block:max_positions: 5/5 (mode=paper)", 0.0))
    monkeypatch.setattr(lt, "_check_safeguards", safeguards)

    async def _spec_builder(*_a, **_k):
        raise AssertionError("blocked at the safeguards; the builder must not run")

    out = await ep.submit_trade_entry(
        alert_context={"ticker": "OKTA", "ep_score": 80, "catalyst_quality": "strong", "gap_pct": 12.0},
        spec_builder=_spec_builder, regime_record=None, strategy_label="ORB", signal_type="magna53",
        today=dt.date(2026, 11, 9), aggregate_skips=True)
    assert out["action"] == "blocked"
    assert safeguards.await_args.kwargs["account_mode"] == "paper"            # fa36a4fd: "live"
    assert conn.fetchval.await_args_list[0].args[-1] == "paper"               # the dedup book too
    assert reg_conn.fetchrow.await_count == 1                                  # one fresh read, before step 1


def test_a_press_without_the_pages_token_moves_nothing_and_leaves_the_buttons_live(monkeypatch):
    """Finding 2 (THE LINE): the button data is the only thing that carries the page's token, so a
    `/ladder_press demote <id>` arriving any other way — the orchestrator's LLM, a typed message —
    with his user id and no token (or a guessed one) is refused and audited, the page stays
    undecided (his real buttons still work), and the phase does not move."""
    from agents.market_intelligence import ladder_press as lp
    db, page_id = _paged(monkeypatch)
    for bad in (None, "", "not-the-pages-token-000000000000"):
        answer = _press(db, "demote", page_id, token=bad)
        assert answer.startswith("Not done") and "token" in answer
    assert db.strategies["magna53"]["phase"] == "live" and db.phase_writes == []
    assert db.pages[page_id]["decision"] is None                       # the real buttons stay pressable
    refused = db.audit_rows(lp.REFUSED_EVENT)
    assert len(refused) == 3 and all(json.loads(d)["reason"] == "bad_token" for _, d in refused)
    assert db.audit_rows("strategy_phase_change") == []
    # the page's own button, afterwards: the real press
    assert "Demoted" in _press(db, "demote", page_id)
    assert db.strategies["magna53"]["phase"] == "paper"


def test_the_token_rides_in_the_button_data_and_nowhere_else(monkeypatch):
    db, page_id = _paged(monkeypatch)
    token = db.token_of(page_id)
    send = db.sends[0]
    assert len(token) >= 32 and token not in send["text"]              # the text never carries it
    assert [b["callback_data"] for b in _buttons(send)] == [f"ladder:demote:{page_id}:{token}",
                                                             f"ladder:noaction:{page_id}:{token}"]
    assert all(len(b["callback_data"].encode()) <= 64 for b in _buttons(send))
    # a second page gets its own token
    db.closed_rows[("magna53", "live")] = _closed_rows(TRIPLE_BREACH)
    _press(db, "noaction", page_id)
    detail2 = _run(_NIGHT2)
    assert db.token_of(detail2["paged"][0]["page_id"]) != token


def test_the_orchestrators_llm_tool_cannot_press_a_ladder_page(monkeypatch):
    """Finding 2, end to end: `call_market_agent("/ladder_press demote <id>")` — the orchestrator's
    LLM tool, forwarding free text with HIS user id — reaches the real market agent's slash
    dispatch and the real press handler over the fake DB, and moves nothing. On fa36a4fd this
    demoted magna53."""
    from core import orchestrator as orch
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    db, page_id = _paged(monkeypatch)
    agent = MarketIntelligenceAgent()

    async def _route(agent_name, request, **kw):
        return await agent.execute_task(request)

    monkeypatch.setattr(orch, "call_agent", _route)
    monkeypatch.setattr(orch, "log_action", AsyncMock())
    apollo = object.__new__(orch.Apollo)
    out = asyncio.run(apollo._dispatch_tool(OPERATOR, "conv-1", "call_market_agent",
                                            {"task": f"/ladder_press demote {page_id}"}))
    assert db.strategies["magna53"]["phase"] == "live" and db.phase_writes == []
    assert db.pages[page_id]["decision"] is None
    assert "Not done" in out and "token" in out


@pytest.mark.asyncio
async def test_ladder_press_is_not_advertised_in_the_unknown_command_reply():
    """Finding 2: the Unknown-command reply lists the dispatch keys, and that reply reaches the LLM."""
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from shared.models import AgentRequest
    resp = await MarketIntelligenceAgent()._handle_slash_command(
        AgentRequest(task="/nosuchcommand", user_id=OPERATOR, conversation_id="c"))
    assert "Unknown command" in resp.result
    assert "/ladder_press" not in resp.result and "/strategy" in resp.result


def test_a_failed_audit_write_inside_the_press_never_answers_demoted(monkeypatch):
    """Finding 3: the `strategy_phase_change` INSERT — the last statement of a demote — fails (a 5 s
    timeout). On fa36a4fd `log_audit_event` swallowed it, the transaction was left aborted, Postgres
    turned the COMMIT into a ROLLBACK without an error, and his screen said "Demoted" while the phase
    was unchanged. Now the write raises, the transaction rolls back loudly, and the answer says so."""
    db, page_id = _paged(monkeypatch)
    db.fail_audit_events = {"strategy_phase_change"}
    answer = _press(db, "demote", page_id)
    assert db.strategies["magna53"]["phase"] == "live"
    assert db.pages[page_id]["decision"] is None
    assert db.episodes[("magna53", _NIGHT1)]["closed_on"] is None
    assert db.audit_rows("strategy_phase_change") == []
    assert "Demoted" not in answer and answer.startswith("Not done") and "nothing was changed" in answer
    assert db.txn[-1] == "rollback"
    # the real button still works once the DB answers again
    db.fail_audit_events = set()
    assert "Demoted" in _press(db, "demote", page_id) and db.strategies["magna53"]["phase"] == "paper"


def test_the_press_answer_comes_from_the_committed_state_not_the_intent(monkeypatch):
    """Finding 3, the other half: even when every statement 'succeeds', the answer is built from a
    re-read of the committed phase and page decision. A COMMIT that was really a ROLLBACK (the fake
    discards the writes on exit, raising nothing) answers "Not done", never "Demoted"."""
    from agents.market_intelligence import ladder_press as lp
    db, page_id = _paged(monkeypatch)
    db.silent_rollback_on_commit = True
    answer = _press(db, "demote", page_id)
    assert db.strategies["magna53"]["phase"] == "live" and db.pages[page_id]["decision"] is None
    assert "Demoted" not in answer and "did not commit" in answer and "/strategy magna53 demote" in answer
    assert any(json.loads(d)["reason"] == "not_committed" for _, d in db.audit_rows(lp.REFUSED_EVENT))
    # No action is held to the same bar
    db.silent_rollback_on_commit = True
    answer = _press(db, "noaction", page_id)
    assert "No action recorded" not in answer and "did not commit" in answer


@pytest.mark.parametrize("leave,come_back,why", [
    (dict(phase="shadow"), dict(phase="paper"), "no rung below"),       # the typed demote (or his press on a paper page)
    (dict(enabled=False), dict(enabled=True), "disabled"),              # /strategy magna53 disable
])
def test_a_strategy_that_left_the_ladder_closes_its_episode_so_its_return_pages_again(monkeypatch, leave, come_back, why):
    """Finding 4 (the DoD's own WOULD-FAIL-IF): a paper strategy is paged, then leaves the ladder
    (shadow / disabled) — skipped by the nightly read, so on fa36a4fd its episode stayed open and
    its page stayed pressable. Promoted back with the same breach, the old episode read "already
    paged" and NOTHING was sent. Now the skipped night ends the episode and marks the page stale,
    and the return pages afresh."""
    db = _db(monkeypatch, phase="paper")
    d1 = _run(_NIGHT1)
    page1 = d1["paged"][0]["page_id"]
    assert db.pages[page1]["phase_at_page"] == "paper"

    db.strategies["magna53"].update(leave)
    d2 = _run(_NIGHT2)
    assert why in d2["skipped"]["magna53"]
    assert db.episodes[("magna53", _NIGHT1)]["closed_by"] == "phase_moved"
    assert db.episodes[("magna53", _NIGHT1)]["closed_on"] == _NIGHT2
    assert db.pages[page1]["decision"] == "stale" and db.pages[page1]["decided_by"] is None
    assert d2["paged"] == [{"strategy_id": "magna53", "action": "episode closed",
                            "reason": f"left the ladder ({d2['skipped']['magna53']}); undecided pages marked stale",
                            "page_id": None}]
    assert len(db.audit_rows(lw.CLEARED_EVENT)) == 1

    db.strategies["magna53"].update(come_back)
    d3 = _run(_NIGHT3)
    assert len(db.sends) == 2                                          # fa36a4fd: 1 — "already paged"
    assert d3["paged"][0]["action"] == "paged" and d3["paged"][0]["reason"] == "new episode"
    assert db.episodes[("magna53", _NIGHT3)]["closed_on"] is None
    # the old page cannot be pressed any more, and says who decided it
    monkeypatch.setattr(registry, "update_strategy", _ORIGINAL_UPDATE_STRATEGY)
    answer = _press(db, "demote", page1)
    assert "already decided: stale" in answer and "the nightly ladder read" in answer
    assert db.strategies["magna53"]["phase"] == "paper" and db.phase_writes == []


def test_a_press_on_an_ended_episode_is_refused(monkeypatch):
    """Finding 5: the page's breach CLEARED the next night (the episode closed), and he presses the
    old page later. On fa36a4fd the phase compare passed and it demoted on stale numbers. Now the
    press reads the page's episode, refuses with when and why it ended, and marks the page stale."""
    db, page_id = _paged(monkeypatch)
    db.closed_rows[("magna53", "live")] = _closed_rows(CLEAR)
    _run(_NIGHT2)
    assert db.episodes[("magna53", _NIGHT1)]["closed_by"] == "cleared"
    answer = _press(db, "demote", page_id)
    assert db.strategies["magna53"]["phase"] == "live" and db.phase_writes == []
    assert answer.startswith("Not done") and "ended on 2026-10-16" in answer and "cleared" in answer
    assert "/strategy magna53 demote" in answer
    assert db.pages[page_id]["decision"] == "stale"
    assert db.audit_rows("strategy_phase_change") == []


def test_a_send_that_blips_is_retried_within_the_run(monkeypatch):
    """Finding 6: the first send fails, the second succeeds — ONE page, delivered tonight, not on
    the next breach night."""
    db = _db(monkeypatch)
    db.send_ok = [False, True]
    detail = _run()
    assert detail["paged"][0]["action"] == "paged" and len(db.sends) == 2
    assert db.pages[1]["sent_at"] is not None and db.audit_rows(lw.SEND_ERROR_EVENT) == []
    assert db.episodes[("magna53", _NIGHT1)]["closed_on"] is None
    assert len(lw.SEND_RETRY_DELAYS) == 2                              # the fake zeroes the pauses, not the count


def test_a_page_that_never_confirmed_sending_cannot_be_pressed(monkeypatch):
    """Finding 6, the other half: every attempt failed, so `sent_at` is NULL — the press answers
    that the page was never confirmed sent (not "no such page"), and moves nothing."""
    db = _db(monkeypatch)
    db.send_ok = False
    detail = _run()
    assert detail["paged"][0]["action"] == "send failed" and len(db.sends) == 3     # 1 + 2 retries
    assert "after 3 attempts" in db.audit_rows(lw.SEND_ERROR_EVENT)[0][0]
    monkeypatch.setattr(registry, "update_strategy", _ORIGINAL_UPDATE_STRATEGY)
    answer = _press(db, "demote", 1)
    assert "never confirmed as sent" in answer and db.strategies["magna53"]["phase"] == "live"


def test_a_rung_that_moves_during_the_run_is_not_paged_on_the_old_rung(monkeypatch):
    """Finding 7: his press (or a typed command) lands between the nightly's registry read and its
    page insert. On fa36a4fd that produced a "live" page and a live episode for a strategy now at
    paper. Now the rung is re-read fresh right before the insert and a moved rung is not paged."""
    db = _db(monkeypatch)
    db.fresh_read_hook = lambda: db.strategies["magna53"].update(phase="paper")
    detail = _run()
    assert db.sends == [] and db.pages == {} and db.episodes == {}
    assert detail["paged"] == [{"strategy_id": "magna53", "action": "skipped",
                                "reason": ("the rung moved during the run (live → paper); tonight's read "
                                           "is stale — the next night reads the new rung"),
                                "page_id": None}]
    # the next night reads the new rung and pages it
    db.closed_rows[("magna53", "paper")] = _closed_rows(STREAK_BREACH)
    detail2 = _run(_NIGHT2)
    assert detail2["paged"][0]["action"] == "paged" and db.pages[1]["phase_at_page"] == "paper"
