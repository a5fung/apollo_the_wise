"""Early open-position skip (2026-10-11 review of #699): the guard's skip ROW is recorded under the OWNING strategy.

`submit_trade_entry`'s open-position guard (step 1b, `BLOCK_TICKER_OPEN_POSITION`) calls `_skip` BEFORE
the phase-gate line binds `strategy`. `_skip` read `strategy` from the enclosing scope to resolve the
skip row's `account_mode`, so on that one early path the read raised ("free variable referenced before
assignment") inside `_skip`'s try: the skipped row was NOT persisted (a `skip_row_write_error` audit row
instead - the #465 class, where a missing skip row once let a duplicate Telegram through).

The ROW is what guards the fix. Both prod callers (live_tracker's ORB pass, the small-cap paper lane)
batch their `block:*` skips (`aggregate_skips=True`), so `_skip` sends no page for this path in prod; the
page tag below only applies to a caller that does not batch (none in prod today), and the tests cover
both settings.

Every test drives the REAL funnel with the REAL `_insert_skipped_trade` (its INSERT is captured at the
connection) and the REAL sender (httpx replaced by a recorder), and sets `current_account_mode()` to the
OPPOSITE of the strategy's book - without that trap a paper strategy in a paper container would pass on
code that never looked at the strategy at all.

FAIL ON THE CODE BEFORE THIS FIX (run against the parent of the builder's commit, 7 of 10): the live and
paper row tests, both batched (`aggregate_skips=True`) row tests, the registry-lookup-failed test, the
recovered-lookup test and the second-pass test. The last two registry-lookup tests also fail on the
builder's own first commit (they pin the `strategy_mode_resolve_error` row + MODE UNKNOWN tag added in
the review fix); the other five pass there. Pins that pass before AND after, kept so a later edit cannot
quietly undo them: the failing-resolver test and both phase-gate attribution tests.

One deliberate consequence, pinned by the second-pass test: the saved row is the duplicate anchor, so a
name that closes inside the opening-range window and re-alerts on a later pass the same day is NOT
re-entered (the pre-fix bug let it re-run the guard, find the position gone, and enter). That is the
original design - the same row every other skip kind leaves - not a change to any entry criterion.
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
    WINDOW_DUPLICATE,
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


def _strategy(phase):
    return SimpleNamespace(enabled=True, phase=phase, live_real_enabled=True,
                           position_size_multiplier=1.0, strategy_id="magna53")


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
        monkeypatch.setattr(registry, "get_strategy", AsyncMock(return_value=_strategy(phase)))
    safeguards = AsyncMock(return_value=(True, None, 0.0))
    monkeypatch.setattr(lt, "_check_safeguards", safeguards)
    monkeypatch.setattr(briefing.httpx, "AsyncClient", router)
    return router, conn, SimpleNamespace(audit=audit, safeguards=safeguards)


async def _run(aggregate_skips=False):
    built = []

    async def _spec_builder(*_a, **_k):
        built.append(1)
        return ({}, "should never be reached")

    out = await ep.submit_trade_entry(
        alert_context={"ticker": "OPN", "ep_score": 80, "catalyst_quality": "strong", "gap_pct": 12.0},
        spec_builder=_spec_builder, regime_record=None, strategy_label="ORB",
        signal_type="magna53", today=TODAY, atr_14=1.0, aggregate_skips=aggregate_skips)
    return out, built


def _row(conn):
    """The one skip-row INSERT: (sql, ticker, alert_date, ep, cq, gap, regime, skip_reason, signal_type, mode)."""
    inserts = [c.args for c in conn.execute.await_args_list if "INSERT INTO mi_live_trades" in c.args[0]]
    assert len(inserts) == 1, f"expected exactly one skipped-trade INSERT, got {inserts}"
    return inserts[0]


def _pages(router):
    return [p for p in router.posts if "skipped" in p["text"]]


def _audit(spies, event):
    return [c for c in spies.audit.await_args_list if c.args and c.args[0] == event]


def _write_errors(spies):
    return _audit(spies, "skip_row_write_error")


def _assert_entry_decision_untouched(out, built, spies):
    assert out == {"ticker": "OPN", "action": ep.ACTION_BLOCKED,
                   "reason": f"{BLOCK_TICKER_OPEN_POSITION}: open since {OPEN_SINCE.isoformat()}"}
    assert built == [] and spies.safeguards.await_count == 0     # blocked at 1b, nothing after it ran



# ── the fix: the early guard records its row under the OWNING strategy's book ────────────────────

@pytest.mark.asyncio
async def test_a_live_strategys_open_position_skip_is_recorded_as_live_and_its_unbatched_page_goes_to_the_main_chat(monkeypatch):
    router, conn, spies = _wire(monkeypatch, phase="live", process_mode="paper")
    out, built = await _run()                                    # aggregate_skips=False: a caller that pages
    _assert_entry_decision_untouched(out, built, spies)

    row = _row(conn)                                             # pre-fix: no INSERT at all
    assert row[1] == "OPN" and row[2] == TODAY
    assert row[7] == f"{BLOCK_TICKER_OPEN_POSITION}: open since {OPEN_SINCE.isoformat()}"
    assert row[8] == "magna53" and row[9] == "live"
    assert _write_errors(spies) == []                            # pre-fix: one skip_row_write_error
    assert len(_audit(spies, "orb_blocked")) == 1

    (page,) = _pages(router)                                     # pre-fix: "MODE UNKNOWN"
    assert page["chat_id"] == MAIN
    assert "💰 LIVE-$" in page["text"] and "MODE UNKNOWN" not in page["text"] and "📄 PAPER" not in page["text"]


@pytest.mark.asyncio
async def test_a_paper_strategys_open_position_skip_is_recorded_as_paper_and_its_unbatched_page_goes_to_the_paper_chat(monkeypatch):
    router, conn, spies = _wire(monkeypatch, phase="paper", process_mode="live")
    out, built = await _run()
    _assert_entry_decision_untouched(out, built, spies)

    row = _row(conn)
    assert row[8] == "magna53" and row[9] == "paper"             # not the process-wide "live"
    assert _write_errors(spies) == []

    (page,) = _pages(router)
    assert page["chat_id"] == PAPER and "📄 PAPER" in page["text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("phase,process_mode,book", [("live", "paper", "live"), ("paper", "live", "paper")])
async def test_the_batched_callers_get_the_row_and_no_page_from_the_skip(monkeypatch, phase, process_mode, book):
    """The PROD setting: live_tracker's ORB pass and the small-cap paper lane both pass
    `aggregate_skips=True`, so `_skip` pages nothing for a `block:*` reason - the row (and the
    `orb_blocked` audit row) is the whole observable. Pre-fix: no row, one skip_row_write_error."""
    router, conn, spies = _wire(monkeypatch, phase=phase, process_mode=process_mode)
    out, built = await _run(aggregate_skips=True)
    _assert_entry_decision_untouched(out, built, spies)

    row = _row(conn)                                             # pre-fix: no INSERT at all
    assert row[8] == "magna53" and row[9] == book
    assert row[7] == f"{BLOCK_TICKER_OPEN_POSITION}: open since {OPEN_SINCE.isoformat()}"
    assert _write_errors(spies) == []                            # pre-fix: one skip_row_write_error
    assert len(_audit(spies, "orb_blocked")) == 1
    assert router.posts == []                                    # batched: the caller's digest is the page


@pytest.mark.asyncio
async def test_the_early_skip_still_lands_when_the_registry_lookup_failed(monkeypatch):
    """The dedup-mode resolve is wrapped (a registry hiccup must not drop an entry); the skip it can
    still produce is recorded under the book the guard actually queried - the process mode - and
    does not crash on a strategy that was never bound. The failure itself is loud
    (`strategy_mode_resolve_error`, the morning-banner event the other label resolves use) and an
    unbatched page says MODE UNKNOWN in the main chat (#699), never a guessed PAPER tag."""
    router, conn, spies = _wire(monkeypatch, phase=None, process_mode="paper", registry_raises=True)
    out, built = await _run()
    _assert_entry_decision_untouched(out, built, spies)
    assert _row(conn)[9] == "paper"                              # pre-fix: no row at all
    assert _write_errors(spies) == []
    assert len(_audit(spies, "strategy_mode_resolve_error")) == 1    # on the builder's commit and on main: none
    (page,) = _pages(router)
    assert page["chat_id"] == MAIN and constants.UNRESOLVED_MODE_TAG.strip() in page["text"]
    assert "📄 PAPER" not in page["text"]


@pytest.mark.asyncio
async def test_a_lookup_that_recovers_at_the_phase_gate_does_not_leave_later_skips_unlabelled(monkeypatch):
    """Regression pin for the failed-lookup flag: it covers ONLY the early skip. If the dedup lookup
    blips and the phase-gate fetch then succeeds, a later skip is attributed to that fetched strategy
    (live here) - not tagged MODE UNKNOWN because an earlier lookup once failed."""
    router, conn, spies = _wire(monkeypatch, phase="live", process_mode="paper", open_since=None)
    monkeypatch.setattr(registry, "get_strategy",
                        AsyncMock(side_effect=[RuntimeError("registry blip"), _strategy("live")]))
    monkeypatch.setattr(lt, "_check_safeguards",
                        AsyncMock(return_value=(False, "block:max_positions: 5/5 (mode=live)", 0.0)))
    out, _built = await _run()
    assert out["action"] == ep.ACTION_BLOCKED
    assert _row(conn)[9] == "live"
    assert len(_audit(spies, "strategy_mode_resolve_error")) == 1
    (page,) = _pages(router)
    assert page["chat_id"] == MAIN and "💰 LIVE-$" in page["text"] and "MODE UNKNOWN" not in page["text"]


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


# ── the row is the duplicate anchor: the one entry-side consequence of the fix ───────────────────

@pytest.mark.asyncio
async def test_a_name_that_closes_inside_the_window_is_not_re_entered_on_a_later_pass(monkeypatch):
    """The deliberate consequence of the row now existing (as for every other skip kind): pass 1 is
    blocked by the held position and leaves its skipped row; the position then closes inside the
    window and the HIGH comes round again. The row is the stage-1 duplicate anchor, so pass 2 is a
    silent `window:duplicate` and builds nothing. Pre-fix there was no row, so pass 2 re-ran the
    guard, found the position gone and went on to the safeguards and the spec builder - an entry the
    original design never allowed (the guard plus its row IS the design)."""
    router, conn, spies = _wire(monkeypatch, phase="live", process_mode="paper")
    held = {"open": True}
    rows: list[tuple] = []

    async def _fetchval(sql, *args):
        if "SELECT EXISTS" in sql:                               # stage 1: a row for (ticker, day, book)?
            return tuple(args) in rows
        if "SELECT alert_date FROM mi_live_trades" in sql:       # stage 1b: still holding it?
            return OPEN_SINCE if held["open"] else None
        raise AssertionError(f"unexpected query before the phase gate: {sql[:80]}")

    async def _execute(sql, *args):
        if "INSERT INTO mi_live_trades" in sql:                  # (ticker, alert_date, ..., account_mode)
            rows.append((args[0], args[1], args[8]))

    conn.fetchval = AsyncMock(side_effect=_fetchval)
    conn.execute = AsyncMock(side_effect=_execute)

    first, built_1 = await _run(aggregate_skips=True)            # pass 1
    assert first["action"] == ep.ACTION_BLOCKED and built_1 == []
    assert rows == [("OPN", TODAY, "live")]

    held["open"] = False                                         # the position closes inside the window
    second, built_2 = await _run(aggregate_skips=True)           # pass 2: the same HIGH again
    assert second == {"ticker": "OPN", "action": ep.ACTION_SKIPPED, "reason": WINDOW_DUPLICATE}
    assert built_2 == [] and spies.safeguards.await_count == 0   # never reached safeguards or sizing
    assert rows == [("OPN", TODAY, "live")]                      # and wrote nothing more
    assert len(_audit(spies, "orb_blocked")) == 1                # the guard fired once, not once per pass


# ── a LATER `_skip` resolves exactly as before ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_phase_gate_skip_resolves_from_the_strategy_fetched_at_the_phase_gate(monkeypatch):
    """Passes before AND after the fix (a regression pin). The two registry fetches return DIFFERENT
    strategies: the dedup-mode resolve sees a LIVE one, the phase gate a SHADOW one (not a paper/live
    book, so it labels from the process mode - "paper" here). A later skip must read the phase-gate
    strategy: if `_skip_strategy` stayed on the early (live) one this row would be "live"."""
    router, conn, spies = _wire(monkeypatch, phase="live", process_mode="paper", open_since=None)
    monkeypatch.setattr(registry, "get_strategy",
                        AsyncMock(side_effect=[_strategy("live"), _strategy("shadow")]))
    out, _built = await _run()
    assert out["action"] == ep.ACTION_BLOCKED and out["reason"] == BLOCK_STRATEGY_IN_SHADOW
    assert _row(conn)[9] == "paper"
    assert _write_errors(spies) == []
    (page,) = _pages(router)
    assert page["chat_id"] == PAPER and "📄 PAPER" in page["text"]


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
