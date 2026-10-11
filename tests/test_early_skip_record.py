"""Early open-position skip (2026-10-11 review of #699): the guard's skip row + page name the OWNING strategy.

`submit_trade_entry`'s open-position guard (step 1b, `BLOCK_TICKER_OPEN_POSITION`) calls `_skip` BEFORE
the phase-gate line binds `strategy`. `_skip` read `strategy` from the enclosing scope to resolve the
skip row's `account_mode`, so on that one early path the read raised ("free variable referenced before
assignment") inside `_skip`'s try: the skipped row was NOT persisted (a `skip_row_write_error` audit row
instead - the #465 class, where a missing skip row once let a duplicate Telegram through) and, since
#699, the page went to the main chat as "MODE UNKNOWN".

Every test drives the REAL funnel with the REAL `_insert_skipped_trade` (its INSERT is captured at the
connection) and the REAL sender (httpx replaced by a recorder), and sets `current_account_mode()` to the
OPPOSITE of the strategy's book - without that trap a paper strategy in a paper container would pass on
code that never looked at the strategy at all. Each of the first four FAILS on the code before this fix.
Telemetry / labelling only: no entry decision, gate, size or order moves, and the tests assert that too.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import briefing, constants
from agents.market_intelligence.broker import entry_pipeline as ep
from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker.skip_reasons import (
    BLOCK_STRATEGY_IN_SHADOW,
    BLOCK_TICKER_OPEN_POSITION,
)
import agents.market_intelligence.strategies.registry as registry
from tests.conftest import make_mock_pool
from tests.test_699_paper_chat_routing import MAIN, PAPER, _Router

TODAY = date(2026, 10, 12)
OPEN_SINCE = date(2026, 10, 5)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", str(MAIN))
    monkeypatch.setenv("TELEGRAM_PAPER_CHAT_ID", str(PAPER))


def _wire(monkeypatch, *, phase, process_mode, open_since=OPEN_SINCE, registry_raises=False):
    """Drive the funnel to its first two checks: not a same-day duplicate, then `open_since` (a date =
    the open-position guard fires; None = it does not). Returns (router, conn, spies)."""
    router = _Router()
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(side_effect=[False, open_since])
    conn.execute = AsyncMock()
    monkeypatch.setattr(ep, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=pool))        # the REAL skip-row INSERT
    audit = AsyncMock()
    monkeypatch.setattr(ep, "log_audit_event", audit)
    monkeypatch.setattr(briefing, "log_audit_event", AsyncMock())
    # The opposite-value trap: the process-wide mode is NOT the strategy's book.
    monkeypatch.setattr(constants, "current_account_mode", lambda: process_mode)
    monkeypatch.setattr(ep, "current_account_mode", lambda: process_mode)
    if registry_raises:
        monkeypatch.setattr(registry, "get_strategy", AsyncMock(side_effect=RuntimeError("registry down")))
    else:
        strategy = SimpleNamespace(enabled=True, phase=phase, live_real_enabled=True,
                                   position_size_multiplier=1.0, strategy_id="magna53")
        monkeypatch.setattr(registry, "get_strategy", AsyncMock(return_value=strategy))
    safeguards = AsyncMock(return_value=(True, None, 0.0))
    monkeypatch.setattr(lt, "_check_safeguards", safeguards)
    monkeypatch.setattr(briefing.httpx, "AsyncClient", router)
    return router, conn, SimpleNamespace(audit=audit, safeguards=safeguards)


async def _run():
    built = []

    async def _spec_builder(*_a, **_k):
        built.append(1)
        return ({}, "should never be reached")

    out = await ep.submit_trade_entry(
        alert_context={"ticker": "OPN", "ep_score": 80, "catalyst_quality": "strong", "gap_pct": 12.0},
        spec_builder=_spec_builder, regime_record=None, strategy_label="ORB",
        signal_type="magna53", today=TODAY, atr_14=1.0)
    return out, built


def _row(conn):
    """The one skip-row INSERT: (sql, ticker, alert_date, ep, cq, gap, regime, skip_reason, signal_type, mode)."""
    inserts = [c.args for c in conn.execute.await_args_list if "INSERT INTO mi_live_trades" in c.args[0]]
    assert len(inserts) == 1, f"expected exactly one skipped-trade INSERT, got {inserts}"
    return inserts[0]


def _pages(router):
    return [p for p in router.posts if "skipped" in p["text"]]


def _write_errors(spies):
    return [c for c in spies.audit.await_args_list if c.args and c.args[0] == "skip_row_write_error"]


def _assert_entry_decision_untouched(out, built, spies):
    assert out == {"ticker": "OPN", "action": ep.ACTION_BLOCKED,
                   "reason": f"{BLOCK_TICKER_OPEN_POSITION}: open since {OPEN_SINCE.isoformat()}"}
    assert built == [] and spies.safeguards.await_count == 0     # blocked at 1b, nothing after it ran


# ── the fix: the early guard records its row under the OWNING strategy's book ────────────────────

@pytest.mark.asyncio
async def test_a_live_strategys_open_position_skip_is_recorded_as_live_and_paged_to_the_main_chat(monkeypatch):
    router, conn, spies = _wire(monkeypatch, phase="live", process_mode="paper")
    out, built = await _run()
    _assert_entry_decision_untouched(out, built, spies)

    row = _row(conn)                                             # pre-fix: no INSERT at all
    assert row[1] == "OPN" and row[2] == TODAY
    assert row[7] == f"{BLOCK_TICKER_OPEN_POSITION}: open since {OPEN_SINCE.isoformat()}"
    assert row[8] == "magna53" and row[9] == "live"
    assert _write_errors(spies) == []                            # pre-fix: one skip_row_write_error

    (page,) = _pages(router)                                     # pre-fix: "MODE UNKNOWN"
    assert page["chat_id"] == MAIN
    assert "💰 LIVE-$" in page["text"] and "MODE UNKNOWN" not in page["text"] and "📄 PAPER" not in page["text"]


@pytest.mark.asyncio
async def test_a_paper_strategys_open_position_skip_is_recorded_as_paper_and_paged_to_the_paper_chat(monkeypatch):
    router, conn, spies = _wire(monkeypatch, phase="paper", process_mode="live")
    out, built = await _run()
    _assert_entry_decision_untouched(out, built, spies)

    row = _row(conn)
    assert row[8] == "magna53" and row[9] == "paper"             # not the process-wide "live"
    assert _write_errors(spies) == []

    (page,) = _pages(router)
    assert page["chat_id"] == PAPER and "📄 PAPER" in page["text"]


@pytest.mark.asyncio
async def test_the_early_skip_still_lands_when_the_registry_lookup_failed(monkeypatch):
    """The dedup-mode resolve is wrapped (a registry hiccup must not drop an entry); the skip it can
    still produce is recorded under the book the guard actually queried - the process mode - and
    does not crash on a strategy that was never bound."""
    router, conn, spies = _wire(monkeypatch, phase=None, process_mode="paper", registry_raises=True)
    out, built = await _run()
    _assert_entry_decision_untouched(out, built, spies)
    assert _row(conn)[9] == "paper"
    assert _write_errors(spies) == []
    assert len(_pages(router)) == 1


@pytest.mark.asyncio
async def test_a_failing_mode_resolver_is_still_loud_and_the_page_still_says_mode_unknown(monkeypatch):
    """The existing fail-open contract is unchanged (a regression pin, true before and after the fix):
    if the resolver raises, the row is NOT written but the failure is LOUD (skip_row_write_error) and
    the page says MODE UNKNOWN in the main chat."""
    router, conn, spies = _wire(monkeypatch, phase="live", process_mode="paper")
    monkeypatch.setattr(ep, "get_strategy_account_mode",
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("resolver boom")))
    out, built = await _run()
    _assert_entry_decision_untouched(out, built, spies)
    assert [c for c in conn.execute.await_args_list if "INSERT INTO mi_live_trades" in c.args[0]] == []
    assert len(_write_errors(spies)) == 1
    (page,) = _pages(router)
    assert page["chat_id"] == MAIN and constants.UNRESOLVED_MODE_TAG.strip() in page["text"]


# ── a LATER `_skip` resolves exactly as before ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_phase_gate_skip_resolves_from_the_fetched_strategy_as_before(monkeypatch):
    """Passes before AND after the fix (a regression pin): the phase-gate fetch is what a later skip
    attributes to. A shadow strategy is not a paper/live book, so it falls back to the process mode -
    "live" here, which a skip that wrongly kept the early `_dedup_strategy`/None would still match, so the
    second half pins the strategy itself: the SAME shadow row under a paper process records "paper"."""
    for process_mode in ("live", "paper"):
        router, conn, spies = _wire(monkeypatch, phase="shadow", process_mode=process_mode, open_since=None)
        out, _built = await _run()
        assert out["action"] == ep.ACTION_BLOCKED and out["reason"] == BLOCK_STRATEGY_IN_SHADOW
        assert _row(conn)[9] == process_mode
        assert _write_errors(spies) == []
        (page,) = _pages(router)
        assert page["chat_id"] == (MAIN if process_mode == "live" else PAPER)


@pytest.mark.asyncio
async def test_a_live_strategys_phase_gate_style_skip_is_still_recorded_live(monkeypatch):
    """A later skip for a LIVE strategy under a paper process (the prod shape) keeps attributing to
    live: the strategy fetched at the phase gate is `_skip`'s source from that line on."""
    router, conn, spies = _wire(monkeypatch, phase="live", process_mode="paper", open_since=None)
    monkeypatch.setattr(lt, "_check_safeguards",
                        AsyncMock(return_value=(False, "block:max_positions: 5/5 (mode=live)", 0.0)))
    out, _built = await _run()
    assert out["action"] == ep.ACTION_BLOCKED
    assert _row(conn)[9] == "live"
    (page,) = _pages(router)
    assert page["chat_id"] == MAIN and "💰 LIVE-$" in page["text"]
