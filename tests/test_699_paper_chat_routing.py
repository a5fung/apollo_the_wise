"""#699 (2026-10-11) — paper alerts go to their own Telegram group, via ONE switch in the sender.

The rule under test (`briefing.send_telegram_message`): when NO explicit `chat_id` was passed AND
the text STARTS with the paper tag (`constants.mode_prefix("paper")`) AND env
`TELEGRAM_PAPER_CHAT_ID` is set, the message goes to that chat; if that send fails it falls back to
the main chat (never silent). Live-tagged and untagged (system) messages, an explicit `chat_id` and
an unset env var are byte-identical to before.

Every behavioural test here drives the REAL `send_telegram_message` with `httpx.AsyncClient` replaced
by a recorder, so it fails on the pre-#699 sender (which has no routing) rather than on an import.
The population tests DERIVE the answer to "which paper-tagged messages could bypass the switch" from
the AST instead of listing it (derive-the-population-never-hand-list-it); the pinned sets below are
the OUTPUT of that derivation and a new member fails the build until someone decides where it goes.
"""
from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
import logging
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence import briefing, constants
from shared.telegram_format import md_to_html
from tests.conftest import make_mock_pool

REPO = Path(__file__).resolve().parents[1]
ROOTS = ("agents", "core", "channels", "shared")

MAIN = 42
PAPER = -5382801675


# ── a recorder standing in for httpx.AsyncClient ─────────────────────────────

class _Resp:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.text = json.dumps({"ok": status_code < 400})

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Router:
    """`plan` maps chat_id -> queue of outcomes (an int status or an Exception); an empty queue
    answers 200. Every payload is recorded in `posts` in send order."""

    def __init__(self, plan: dict | None = None):
        self.plan = {k: list(v) for k, v in (plan or {}).items()}
        self.posts: list[dict] = []

    def __call__(self, *a, **k):          # httpx.AsyncClient(timeout=15)
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        self.posts.append(json)
        queue = self.plan.get(json["chat_id"])
        step = queue.pop(0) if queue else 200
        if isinstance(step, Exception):
            raise step
        return _Resp(step)

    def chats(self) -> list[int]:
        return [p["chat_id"] for p in self.posts]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", str(MAIN))
    monkeypatch.setenv("TELEGRAM_PAPER_CHAT_ID", str(PAPER))


async def _send(text, router, **kw):
    with patch.object(briefing.httpx, "AsyncClient", router), \
         patch.object(briefing, "log_audit_event", AsyncMock()):
        return await briefing.send_telegram_message(text, **kw)


PAPER_TEXT = "📄 PAPER ✅ *FILLED:* ABCD (attempt 1)\nEntry $10.00"
LIVE_TEXT = "💰 LIVE-$ ✅ *FILLED:* ABCD (attempt 1)\nEntry $10.00"
SYSTEM_TEXT = "🚨 *Job FAILED:* `ep_scan` — timeout"


# ── the sender ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_paper_text_goes_to_the_paper_chat_only():
    r = _Router()
    assert await _send(PAPER_TEXT, r) is True
    assert r.chats() == [PAPER]                      # one send, to the paper chat, none to main


@pytest.mark.asyncio
async def test_live_text_stays_in_the_main_chat():
    r = _Router()
    assert await _send(LIVE_TEXT, r) is True
    assert r.chats() == [MAIN]


@pytest.mark.asyncio
async def test_untagged_system_alert_stays_in_the_main_chat():
    r = _Router()
    assert await _send(SYSTEM_TEXT, r) is True
    assert r.chats() == [MAIN]


@pytest.mark.asyncio
async def test_a_cancel_digest_spanning_both_books_stays_in_the_main_chat():
    """order_manager._cleanup_cancel_label says '⚠️ MIXED live+paper ' rather than guess — that is
    NOT a paper message and must not move."""
    r = _Router()
    await _send("⚠️ MIXED live+paper 🕓 10:00 cleanup: cancelled 2 unfilled order(s) — AAA, BBB", r)
    assert r.chats() == [MAIN]


@pytest.mark.asyncio
async def test_an_explicit_chat_id_is_honoured_even_for_paper_text():
    r = _Router()
    assert await _send(PAPER_TEXT, r, chat_id=777) is True
    assert r.chats() == [777]


@pytest.mark.asyncio
async def test_env_unset_is_byte_identical_to_before(monkeypatch):
    monkeypatch.delenv("TELEGRAM_PAPER_CHAT_ID", raising=False)
    r = _Router()
    assert await _send(PAPER_TEXT, r) is True
    assert r.posts == [{
        "chat_id": MAIN, "text": md_to_html(PAPER_TEXT),
        "disable_web_page_preview": True, "parse_mode": "HTML",
    }]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["", "   ", "Apollo Paper", "-53x"])
async def test_a_blank_or_malformed_env_value_means_the_main_chat(monkeypatch, bad):
    monkeypatch.setenv("TELEGRAM_PAPER_CHAT_ID", bad)
    r = _Router()
    assert await _send(PAPER_TEXT, r) is True
    assert r.chats() == [MAIN]


@pytest.mark.asyncio
async def test_the_paper_payload_is_the_same_message_just_another_chat():
    """Only chat_id differs — conversion, preview flag and parse mode are untouched."""
    routed, plain = _Router(), _Router()
    await _send(PAPER_TEXT, routed)
    await _send(PAPER_TEXT, plain, chat_id=MAIN)
    assert routed.posts[0] == {**plain.posts[0], "chat_id": PAPER}


@pytest.mark.asyncio
async def test_a_preconverted_html_body_routes_too():
    """order_ingest._emit hands over md_to_html(text) with parse_mode='HTML' — the sender must still
    see the tag at the start of what it is given."""
    body = md_to_html("📄 PAPER ⚠️ *Ingest R1 rejected* — ABCD: unknown_strategy x")
    r = _Router()
    assert await _send(body, r, parse_mode="HTML") is True
    assert r.chats() == [PAPER]


@pytest.mark.asyncio
async def test_a_long_paper_message_splits_inside_the_paper_chat():
    text = "📄 PAPER 📊 *Report*\n" + "\n\n".join(f"line {i} " + "x" * 300 for i in range(40))
    r = _Router()
    assert await _send(text, r) is True
    assert len(r.posts) > 1 and set(r.chats()) == {PAPER}


@pytest.mark.asyncio
async def test_reply_markup_rides_the_last_paper_chunk_only():
    text = "📄 PAPER 📊 *Report*\n" + "\n\n".join(f"line {i} " + "x" * 300 for i in range(40))
    markup = {"inline_keyboard": [[{"text": "ok", "callback_data": "ok"}]]}
    r = _Router()
    await _send(text, r, reply_markup=markup)
    assert set(r.chats()) == {PAPER}
    assert ["reply_markup" in p for p in r.posts] == [False] * (len(r.posts) - 1) + [True]


# ── the fallback: a paper-chat failure must never lose the alert ─────────────

@pytest.mark.asyncio
async def test_chat_not_found_falls_back_to_the_main_chat_and_warns(caplog):
    """The realistic failure: a mistyped/deleted group id answers 400 'chat not found'. That takes
    the markup->plain retry, then raises, then must land in the MAIN chat."""
    r = _Router({PAPER: [400, 400]})
    with caplog.at_level(logging.WARNING, logger=briefing.logger.name):
        assert await _send(PAPER_TEXT, r) is True
    assert r.chats() == [PAPER, PAPER, MAIN]         # html, plain retry, then the fallback
    assert r.posts[-1]["text"] == md_to_html(PAPER_TEXT) and r.posts[-1]["parse_mode"] == "HTML"
    assert any("paper chat" in rec.getMessage() and str(PAPER) in rec.getMessage()
               for rec in caplog.records if rec.levelno == logging.WARNING)


@pytest.mark.asyncio
async def test_bot_removed_from_the_group_403_falls_back():
    r = _Router({PAPER: [403]})
    assert await _send(PAPER_TEXT, r) is True
    assert r.chats() == [PAPER, MAIN]


@pytest.mark.asyncio
async def test_a_network_error_on_the_paper_send_falls_back():
    r = _Router({PAPER: [ConnectionError("boom")]})
    assert await _send(PAPER_TEXT, r) is True
    assert r.chats() == [PAPER, MAIN]


@pytest.mark.asyncio
async def test_a_markup_400_that_the_plain_retry_fixes_stays_in_the_paper_chat():
    """Not every paper-chat hiccup is a failure — the ordinary html->plain retry still delivers
    there, and must not ALSO send a duplicate to the main chat."""
    r = _Router({PAPER: [400, 200]})
    assert await _send(PAPER_TEXT, r) is True
    assert r.chats() == [PAPER, PAPER]


@pytest.mark.asyncio
async def test_both_chats_failing_returns_false():
    r = _Router({PAPER: [403], MAIN: [403]})
    assert await _send(PAPER_TEXT, r) is False
    assert r.chats() == [PAPER, MAIN]


@pytest.mark.asyncio
async def test_the_paper_failure_leaves_an_audit_row_naming_the_chat():
    r = _Router({PAPER: [ConnectionError("boom")]})
    audit = AsyncMock()
    with patch.object(briefing.httpx, "AsyncClient", r), patch.object(briefing, "log_audit_event", audit):
        await briefing.send_telegram_message(PAPER_TEXT)
    rows = [c.args for c in audit.await_args_list]
    assert any(a[0] == "telegram_send_failed" and f"chat={PAPER}" in a[2] for a in rows)


@pytest.mark.asyncio
async def test_reply_markup_survives_the_fallback_on_the_last_chunk():
    markup = {"inline_keyboard": [[{"text": "ok", "callback_data": "ok"}]]}
    r = _Router({PAPER: [403]})
    await _send(PAPER_TEXT, r, reply_markup=markup)
    assert r.chats() == [PAPER, MAIN]
    assert "reply_markup" in r.posts[-1]


# ── the tag helpers ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("📄 PAPER ✅ *FILLED:*", True),
    ("   📄 PAPER ✅ filled", True),                      # leading whitespace
    ("\n📄 PAPER ✅ filled", True),
    ("*📄 PAPER ✅ filled*", True),                       # a Markdown opener in front
    ("<b>📄 PAPER </b>filled", True),                     # an HTML tag in front
    ("📄 PAPER \n🚨 something", True),
    ("📄 PAPER\n🚨 something", True),                     # tag at the end of its line
    ("💰 LIVE-$ ✅ *FILLED:*", False),
    ("🟡 *STAGED-PAPER (not armed — no auto-submit):* ABCD", False),
    ("⚠️ MIXED live+paper 🕓 cleanup", False),
    ("🚨 *Job FAILED:* later in the text 📄 PAPER ", False),   # tag not at the START
    ("📄 PAPERWORK filed", False),                        # a longer word is not the tag
    ("", False),
    (None, False),
])
def test_is_paper_message(text, expected):
    assert constants.is_paper_message(text) is expected


def test_the_tag_is_derived_from_mode_prefix_not_retyped(monkeypatch):
    """Change what mode_prefix says for paper and the routing follows — a re-typed literal here
    would have silently turned the switch off."""
    real = constants.mode_prefix
    monkeypatch.setattr(constants, "mode_prefix",
                        lambda m=None: "🧪 SIM " if m == "paper" else real(m))
    assert constants.is_paper_message("🧪 SIM ✅ filled") is True
    assert constants.is_paper_message("📄 PAPER ✅ filled") is False


def test_paper_chat_id_for_unit(monkeypatch):
    f = constants.paper_chat_id_for
    assert f(PAPER_TEXT) == PAPER
    assert f(LIVE_TEXT) is None and f(SYSTEM_TEXT) is None
    assert f(PAPER_TEXT, 123) is None                    # explicit chat wins
    monkeypatch.delenv("TELEGRAM_PAPER_CHAT_ID")
    assert f(PAPER_TEXT) is None
    monkeypatch.setenv("TELEGRAM_PAPER_CHAT_ID", " -5382801675 ")
    assert f(PAPER_TEXT) == PAPER                        # surrounding whitespace tolerated


# ── the population: who builds a paper-tagged text, and does it reach the switch? ──

def _callname(n: ast.Call) -> str | None:
    f = n.func
    return f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)


# Both build the account tag at the front of an alert: `mode_prefix` (caller knows the mode) and
# `strategy_mode_prefix` (caller looked the mode up and the lookup may have failed - #699 review fix).
_TAG_BUILDERS = {"mode_prefix", "strategy_mode_prefix"}


def _functions_calling_mode_prefix() -> list[tuple[str, str, ast.AST, bool]]:
    """(relative path, innermost enclosing function name, that function's node, bare_call) for
    every `mode_prefix(` / `strategy_mode_prefix(` call in production code. `bare_call` = no args or
    a literal None."""
    out = []
    for root in ROOTS:
        for p in sorted((REPO / root).rglob("*.py")):
            src = p.read_text(encoding="utf-8")
            if "mode_prefix" not in src or p.name == "constants.py":
                continue          # constants.py DEFINES mode_prefix and reads the tag in is_paper_message
            tree = ast.parse(src)
            parents = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}

            def enclosing(n):
                while n in parents:
                    n = parents[n]
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        return n
                return None

            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and _callname(n) in _TAG_BUILDERS:
                    fn = enclosing(n)
                    bare = (not n.args and not n.keywords) or (
                        len(n.args) == 1 and isinstance(n.args[0], ast.Constant) and n.args[0].value is None)
                    out.append((str(p.relative_to(REPO)), fn.name if fn else "<module>", fn, bare))
    return out


_SENDERS = {"send_telegram_message", "send_trade_proposal"}

# Functions that call mode_prefix() but do not themselves call the sender. DERIVED once, pinned with
# the reason each is fine — a NEW one fails the build until someone decides where its text goes.
_BUILDERS_VIA_SENDER = {
    ("agents/market_intelligence/broker/coverage_drift.py", "_format_d1_message"),   # -> _alert -> send_telegram_message
    ("agents/market_intelligence/broker/coverage_drift.py", "_format_d2_message"),
    ("agents/market_intelligence/broker/order_ingest.py", "_handle_r1"),             # -> _emit -> send_telegram_message
    ("agents/market_intelligence/broker/order_ingest.py", "_handle_r2_r3i"),
    ("agents/market_intelligence/broker/order_manager.py", "_cleanup_cancel_label"),  # label in front of a send_telegram_message digest
    ("agents/market_intelligence/broker/trade_stream.py", "_full_exit_restore_page"),  # page text -> send_telegram_message
    # breakout v1 phase 1 (2026-10-29): the nightly list message, paper-tagged ON PURPOSE (a paper setup's list ->
    # the paper chat); run_breakout_v1_list hands it to send_telegram_message
    ("agents/market_intelligence/breakout_v1_list.py", "format_list_message"),
}
_BUILDERS_NOT_ROUTED = {
    # an interactive /dryrun reply to the operator: stays where he asked
    ("agents/market_intelligence/agent.py", "_handle_dryrun"),
    # an interactive `/trades TICKER` reply (#624): tags each row's book mid-message, but the reply
    # opens with its own header (never the paper tag, pinned in tests/test_trades_ticker_both_books.py)
    # and returns through AgentResponse to the chat he asked in
    ("agents/market_intelligence/agent.py", "_handle_trades_query"),
    # folded into the 16:55 Market Close Digest (a composite message that starts with the digest
    # header, so it is untagged and stays in the main chat by design)
    ("agents/market_intelligence/broker/live_tracker.py", "send_live_trade_summary"),
}
# A raw Bot-API POST that also builds a mode-tagged header: bypasses the sender.
_RAW_BYPASS = {("agents/market_intelligence/broker/telegram_confirm.py", "send_trade_proposal")}


def _calls_in(fn: ast.AST) -> set[str]:
    return {nm for n in ast.walk(fn) if isinstance(n, ast.Call) and (nm := _callname(n))}


def _has_string(fn: ast.AST, needle: str) -> bool:
    return any(isinstance(n, ast.Constant) and isinstance(n.value, str) and needle in n.value
               for n in ast.walk(fn))


def test_every_function_that_builds_a_mode_tagged_text_reaches_the_sender_or_is_pinned():
    direct, no_sender = set(), set()
    for rel, name, fn, _bare in _functions_calling_mode_prefix():
        if fn is None:
            no_sender.add((rel, name))
        elif _calls_in(fn) & _SENDERS:
            direct.add((rel, name))
        else:
            no_sender.add((rel, name))
    # the raw sender calls neither (it IS one) — it is judged by the next test
    unexplained = no_sender - _BUILDERS_VIA_SENDER - _BUILDERS_NOT_ROUTED - _RAW_BYPASS
    assert not unexplained, (
        f"{sorted(unexplained)} build a mode-tagged text but call neither send_telegram_message nor "
        "send_trade_proposal. Decide where the text goes and add the function to the matching pinned "
        "set in tests/test_699_paper_chat_routing.py (routed via the sender / deliberately not routed).")
    stale = (_BUILDERS_VIA_SENDER | _BUILDERS_NOT_ROUTED | _RAW_BYPASS) - no_sender
    assert not stale, f"pinned but no longer a no-sender builder (moved or now sends directly): {sorted(stale)}"
    assert len(direct) >= 40                              # 49 today — a sanity floor, not the proof


def test_builders_marked_routed_via_the_sender_live_in_a_file_that_calls_it():
    for rel, _name in sorted(_BUILDERS_VIA_SENDER):
        tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
        assert any(isinstance(n, ast.Call) and _callname(n) == "send_telegram_message"
                   for n in ast.walk(tree)), f"{rel} claims to deliver through send_telegram_message but never calls it"


def test_the_only_raw_bot_api_post_that_builds_a_mode_tagged_text_is_the_pinned_one():
    """A function that calls mode_prefix AND posts to api.telegram.org itself bypasses the switch.
    Today that is exactly send_trade_proposal."""
    raw = {(rel, name) for rel, name, fn, _ in _functions_calling_mode_prefix()
           if fn is not None and _has_string(fn, "api.telegram.org")}
    assert raw == _RAW_BYPASS, (
        f"raw senders that build a mode-tagged text changed: now {sorted(raw)}. Route the new one "
        "through briefing.send_telegram_message (or constants.paper_chat_id_for) and update the pin.")


def test_the_proposal_bypass_cannot_carry_a_paper_message_today():
    """send_trade_proposal is reached only when entry_pipeline does NOT auto-enter. Every paper
    strategy auto-enters (it never gets a proposal), so the raw sender never carries a paper
    message. If that stops being true, this fails and the proposal must be routed."""
    from agents.market_intelligence.broker.entry_pipeline import _should_auto_enter
    assert _should_auto_enter("paper", True) is True
    assert _should_auto_enter("paper", False) is True
    assert _should_auto_enter("live", False) is False     # the only way to a proposal: live, not armed


@pytest.mark.asyncio
async def test_a_staged_live_proposal_stays_in_the_main_chat_with_the_env_set(monkeypatch):
    """The one raw sender, driven for real: a live-not-armed proposal wears the untagged STAGED-PAPER
    banner and posts to the main chat — the paper var does not touch it."""
    from agents.market_intelligence.broker import telegram_confirm
    r = _Router()
    monkeypatch.setattr(telegram_confirm.httpx, "AsyncClient", r)
    import agents.market_intelligence.catalyst_rubric_runtime as crr

    async def _boom(*a, **k):
        raise RuntimeError("no db in test")

    monkeypatch.setattr(crr, "get_theme_membership", _boom)
    spec = {"ticker": "SNX", "entry_price": 10.0, "stop_loss_price": 9.0, "risk_dollars": 40,
            "shares": 3, "ep_score": 72, "equity": 5000, "regime": "Choppy"}
    ok = await telegram_confirm.send_trade_proposal(
        {"catalyst_quality": "game_changer", "gap_pct": 11.2}, spec, trade_id=1,
        live_real_enabled=False, account_mode="live")
    assert ok is True and r.chats() == [MAIN]
    assert not constants.is_paper_message(r.posts[0]["text"])


def test_bare_default_label_sites_are_pinned():
    """A bare mode_prefix() / mode_prefix(None) takes its tag from current_account_mode(), which is
    'paper' in EVERY prod container (ALPACA_PAPER=true - the account_mode_active boot rows of
    2026-10-11). Such an alert carries the PAPER tag whatever it is about, so after #699 it lands in
    the paper chat. The review of #699 found two of the three that mattered - bar_stream's stream
    failure and entry_pipeline's un-aggregated skip (an infra: page for a LIVE entry) - and both now
    resolve their own label; what is left is an interactive reply, which never goes through the switch
    (explicit chat). A NEW one fails the build so it is a decision, not an accident."""
    bare = {(rel, name) for rel, name, _fn, b in _functions_calling_mode_prefix() if b}
    assert bare == {
        ("agents/market_intelligence/agent.py", "_handle_dryrun"),                  # interactive reply
    }, f"bare-label sites changed: {sorted(bare)}"


# ── review fixes (2026-10-11): an alert about a LIVE book must never wear the paper tag ──────────
#
# The first cut of #699 left two live-relevant alerts on a bare `mode_prefix()` (whose answer is
# `current_account_mode()` = "paper" in every prod container) and four more that fall back to it when
# the strategy-mode lookup fails. Each of those would have moved from "right chat, wrong label" to
# "WRONG CHAT" the moment the switch went live. The tests below drive the real sender.

def test_strategy_mode_prefix_never_guesses_a_failed_lookup(monkeypatch):
    monkeypatch.setattr(constants, "current_account_mode", lambda: "paper")   # the prod default
    f = constants.strategy_mode_prefix
    assert f("live") == constants.mode_prefix("live")
    assert f("paper") == constants.mode_prefix("paper")
    unknown = f(None)
    assert unknown == constants.UNRESOLVED_MODE_TAG and unknown != constants.mode_prefix("paper")
    assert constants.paper_chat_id_for(unknown + "x") is None                 # stays in the main chat
    assert constants.BOTH_BOOKS_TAG not in (unknown, constants.mode_prefix("live"), constants.mode_prefix("paper"))
    assert constants.paper_chat_id_for(constants.BOTH_BOOKS_TAG + "x") is None


def _wire_infra_skip(monkeypatch, router, *, phase, resolver_raises=False):
    """Drive the REAL entry funnel to an `infra:` skip for a magna53 whose phase is `phase`, with the
    REAL sender writing into `router`. `current_account_mode()` is paper, as in every prod container."""
    from agents.market_intelligence.broker import entry_pipeline as ep
    from agents.market_intelligence.broker import live_tracker as lt
    from agents.market_intelligence.broker.skip_reasons import INFRA_NO_BAR
    import agents.market_intelligence.strategies.registry as registry

    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(side_effect=[False, None])        # not a duplicate, not already open
    monkeypatch.setattr(ep, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ep, "log_audit_event", AsyncMock())
    monkeypatch.setattr(constants, "current_account_mode", lambda: "paper")
    strategy = SimpleNamespace(enabled=True, phase=phase, live_real_enabled=True,
                               position_size_multiplier=1.0, strategy_id="magna53")
    monkeypatch.setattr(registry, "get_strategy", AsyncMock(return_value=strategy))
    monkeypatch.setattr(lt, "_check_safeguards",
                        AsyncMock(return_value=(False, f"{INFRA_NO_BAR}: 3 retries exhausted", 0.0)))
    monkeypatch.setattr(lt, "_insert_skipped_trade", AsyncMock())
    if resolver_raises:
        monkeypatch.setattr(ep, "get_strategy_account_mode",
                            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("resolver boom")))
    monkeypatch.setattr(briefing.httpx, "AsyncClient", router)
    monkeypatch.setattr(briefing, "log_audit_event", AsyncMock())
    return ep


async def _run_infra_skip(ep):
    async def _never(*_a, **_k):
        raise AssertionError("the safeguard block must stop the entry before the spec is built")

    return await ep.submit_trade_entry(
        alert_context={"ticker": "SNX", "ep_score": 80, "catalyst_quality": "strong", "gap_pct": 12.0},
        spec_builder=_never, regime_record=None, strategy_label="ORB", signal_type="magna53",
        today=date(2026, 10, 12), atr_14=1.0, aggregate_skips=True)   # infra:* pings even when aggregating


def _skip_posts(router):
    return [p for p in router.posts if "skipped" in p["text"]]


@pytest.mark.asyncio
async def test_an_infra_skip_for_a_live_entry_reaches_the_main_chat(monkeypatch):
    """The reviewer's blocking case: INFRA_NO_BAR on a LIVE magna53 entry. Pre-fix the page opened with
    the bare-default PAPER tag and (with the switch on) went to Apollo Paper."""
    router = _Router()
    ep = _wire_infra_skip(monkeypatch, router, phase="live")
    await _run_infra_skip(ep)
    posts = _skip_posts(router)
    assert len(posts) == 1, router.posts
    assert posts[0]["chat_id"] == MAIN
    assert "💰 LIVE-$" in posts[0]["text"] and "📄 PAPER" not in posts[0]["text"]


@pytest.mark.asyncio
async def test_an_infra_skip_for_a_paper_entry_still_goes_to_the_paper_chat(monkeypatch):
    """Control: the fix must not pull a PAPER strategy's own skip out of the paper chat."""
    router = _Router()
    ep = _wire_infra_skip(monkeypatch, router, phase="paper")
    await _run_infra_skip(ep)
    posts = _skip_posts(router)
    assert len(posts) == 1, router.posts
    assert posts[0]["chat_id"] == PAPER and "📄 PAPER" in posts[0]["text"]


@pytest.mark.asyncio
async def test_an_infra_skip_whose_mode_lookup_failed_is_not_guessed_paper(monkeypatch):
    router = _Router()
    ep = _wire_infra_skip(monkeypatch, router, phase="live", resolver_raises=True)
    await _run_infra_skip(ep)
    posts = _skip_posts(router)
    assert len(posts) == 1, router.posts
    assert posts[0]["chat_id"] == MAIN
    assert constants.UNRESOLVED_MODE_TAG.strip() in posts[0]["text"] and "📄 PAPER" not in posts[0]["text"]


@pytest.mark.asyncio
async def test_the_bar_stream_failure_page_is_a_both_books_alert_in_the_main_chat(monkeypatch):
    """`_run_stream` serves every subscribed ticker across every strategy, live ORB entries included.
    Pre-fix it wore the bare-default PAPER tag and would have moved to Apollo Paper."""
    from agents.market_intelligence.broker import bar_stream
    import agents.market_intelligence.db as db

    class _DeadSocket:
        async def _run_forever(self):
            raise RuntimeError("socket closed")

    real_sleep = asyncio.sleep

    async def _no_wait(_seconds, *a, **k):
        await real_sleep(0)

    router = _Router()
    monkeypatch.setattr(bar_stream, "_data_stream", _DeadSocket())
    monkeypatch.setattr(bar_stream, "_subscribed", set())
    monkeypatch.setattr(bar_stream, "_stream_healthy", False)
    monkeypatch.setattr(bar_stream.asyncio, "sleep", _no_wait)
    monkeypatch.setattr(db, "log_audit_event", AsyncMock())
    monkeypatch.setattr(constants, "current_account_mode", lambda: "paper")   # the prod default
    monkeypatch.setattr(briefing.httpx, "AsyncClient", router)
    monkeypatch.setattr(briefing, "log_audit_event", AsyncMock())

    await bar_stream._run_stream()

    assert router.chats() == [MAIN], router.posts
    text = router.posts[0]["text"]
    assert "Bar stream failed" in text and "📄 PAPER" not in text
    assert constants.BOTH_BOOKS_TAG.strip() in text and not constants.is_paper_message(text)


_RESOLVER_CALLS = {"resolve_strategy_mode_nonfatal", "_magna53_account_mode"}


def test_a_function_that_looks_a_strategy_mode_up_never_uses_the_guessing_prefix():
    """DERIVED, not listed: every function in production code that calls the fail-open resolver
    (`resolve_strategy_mode_nonfatal`, or the scheduler's `_magna53_account_mode` closure over it) gets
    None back when the registry hiccups. `mode_prefix(None)` then guesses "paper" - and with #699 a
    guessed paper tag sends a LIVE strategy's alert (ORB pipeline crashed, skip digest, catalyst
    downgrade, out-of-window HIGH) to Apollo Paper. They must use `strategy_mode_prefix`."""
    offenders, resolvers_seen = [], 0
    for root in ROOTS:
        for p in sorted((REPO / root).rglob("*.py")):
            src = p.read_text(encoding="utf-8")
            if "resolve_strategy_mode_nonfatal" not in src:
                continue
            for fn in ast.walk(ast.parse(src)):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                names = [nm for n in ast.walk(fn) if isinstance(n, ast.Call) and (nm := _callname(n))]
                if _RESOLVER_CALLS & set(names):
                    resolvers_seen += 1
                    if "mode_prefix" in names:
                        offenders.append(f"{p.relative_to(REPO)}::{fn.name}")
    assert resolvers_seen >= 3                     # live_tracker, ep_detector, scheduler (+ the closure's owner)
    assert not offenders, (
        f"{offenders} look up a strategy's mode (fail-open: None on error) and then label with the bare "
        "mode_prefix, which guesses paper. Use constants.strategy_mode_prefix.")


# ── the probes that ship with #699 ──────────────────────────────────────────

def _load_probe(name: str):
    path = REPO / "scripts" / "probes" / "_699_paper_chat" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_probe_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_dryrun_precheck_reads_the_real_env_and_names_a_wrong_id(monkeypatch):
    """Pre-check (i) used to print only whether the variable was PRESENT, so a mistyped id still
    passed. It must resolve the id the container really holds and demand the signed one."""
    dry = _load_probe("dryrun_routing")
    monkeypatch.setenv("TELEGRAM_PAPER_CHAT_ID", str(PAPER))
    assert dry.check_real_env(require=True) == (True, f"real env routes a paper message to {PAPER}")
    monkeypatch.setenv("TELEGRAM_PAPER_CHAT_ID", "-100123")
    ok, why = dry.check_real_env(require=True)
    assert ok is False and "-100123" in why and str(PAPER) in why
    monkeypatch.setenv("TELEGRAM_PAPER_CHAT_ID", "'-5382801675'")      # a quoted value: malformed -> silently main
    ok, why = dry.check_real_env(require=True)
    assert ok is False and "malformed" in why
    monkeypatch.delenv("TELEGRAM_PAPER_CHAT_ID")
    assert dry.check_real_env(require=False)[0] is True                 # a laptop run is allowed to be unset
    assert dry.check_real_env(require=True)[0] is False                 # a container check is not


def test_live_routing_probe_sends_exactly_one_paper_message():
    """One test message, into Apollo Paper only: a LIVE-$ / untagged line in the main chat would be the
    very noise #699 removes, and the env var cannot change where those go (the dry run proves it)."""
    probe = _load_probe("live_routing_check")
    probes = probe.probe_texts()
    assert [kind for kind, _ in probes] == ["paper"]
    text = probes[0][1]
    assert constants.is_paper_message(text) and "#699" in text and "no trade" in text   # tag derived from mode_prefix
    # the probe refuses to send anything unless the real env resolves a paper message to the signed id
    assert probe.EXPECTED_PAPER_CHAT == PAPER


# ── env wiring ───────────────────────────────────────────────────────────────

def test_prod_containers_that_send_telegram_read_the_var_from_env_file():
    """No explicit `environment:` list carries Telegram variables, and every service that sends
    reads ../.env — so TELEGRAM_PAPER_CHAT_ID needs no compose edit. If someone adds an explicit
    Telegram var to a service, that service must list the new one too."""
    import yaml
    compose = yaml.safe_load((REPO / "docker/docker-compose.prod.yml").read_text(encoding="utf-8"))
    for svc in ("orchestrator", "market-agent", "apollo-execution"):
        conf = compose["services"][svc]
        env_file = conf["env_file"]
        assert "../.env" in ([env_file] if isinstance(env_file, str) else env_file), svc
        explicit = conf.get("environment") or {}
        names = set(explicit) if isinstance(explicit, dict) else {e.split("=")[0] for e in explicit}
        assert not {n for n in names if n.startswith("TELEGRAM_")}, (
            f"{svc} lists a Telegram variable explicitly - add TELEGRAM_PAPER_CHAT_ID there too")


def test_staging_never_gets_the_paper_chat():
    assert "TELEGRAM_PAPER_CHAT_ID" not in (REPO / "docker/docker-compose.staging.yml").read_text(encoding="utf-8")


def test_the_var_is_documented_where_operators_look():
    for rel in (".env.example", "docs/architecture/market_agent_reference.md"):
        assert "TELEGRAM_PAPER_CHAT_ID" in (REPO / rel).read_text(encoding="utf-8"), rel
