"""#527 — market-hours position-coverage DETECTOR + Part 1 stop-refresh telemetry.

PART 1: `_stop_refresh` (shared body of `post_close_stop_refresh` /
`morning_stop_refresh`) must emit ONE `stop_refresh_ran` audit row every run,
UNCONDITIONALLY — including the all-quiet case where nothing needs doing. Before
this, the function was silent whenever every position was already covered, so
"ran clean" was indistinguishable from "never ran" (measured in prod:
`post_close_stop_refresh` produced ZERO `mi_audit_log` rows in its first 3 days).

PART 2: `check_position_coverage` answers "does every LIVE open position have a
resting stop RIGHT NOW?" by reading BROKER truth (never DB state) for every
mi_live_trades row with status='filled' AND remaining_shares > 0 AND
account_mode='live'. DETECTOR ONLY — never places/cancels/repairs an order
(`_ensure_stop_coverage` owns repair). Telegrams + writes `position_unprotected`
on a real gap, deduped to once per trade per ET session (the #508 bombardment
idiom — audit row lands every cycle, only the Telegram is deduped). Fails OPEN
AND LOUD on a broker-read error: never claims "covered" when the broker couldn't
be read. Defers (does not flag) a trade an in-flight partial exit currently
holds the advisory lock on — advisor review caught that a naive read during the
~72ms cancel-then-new-stop window of `execute_partial_exit` would otherwise read
as a false-positive naked position.

MUTATION CHECK (recorded here, not re-run by CI): during development the
broker-read except branch was manually reverted from writing
`position_unprotected_check_failed` + appending to `check_failed` to a bare
`continue` (silent swallow). `test_broker_read_failure_fails_open_never_claims_all_clear`
below FAILED against that mutation (`assert len(result["check_failed"]) == 1` →
`assert 0 == 1`) — confirming the assertion has teeth — before the code was
restored to the version in this diff.

Mocking pattern mirrors `tests/test_never_naked_invariant.py`'s `_patches` /
`_fake_try_lock` helpers for `_ensure_stop_coverage` and
`tests/conftest.py::make_mock_pool`.
"""
from __future__ import annotations

from contextlib import ExitStack, asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_mock_pool


# ─────────────────────────── Part 2: check_position_coverage ──────────────────


def _trade(trade_id=1, ticker="IBM", remaining_shares=4.0, account_mode="live"):
    return {"id": trade_id, "ticker": ticker, "remaining_shares": remaining_shares,
            "account_mode": account_mode}


def _live_stop(order_id, qty, status="new"):
    return {"id": order_id, "side": "sell", "type": "stop", "qty": qty, "status": status}


def _fake_try_lock(acquired: bool):
    """Stand-in for order_manager._trade_advisory_try_lock that yields `acquired`
    without touching a real Postgres pool — same helper `test_never_naked_invariant.py`
    uses for `_ensure_stop_coverage`. acquired=True (default) → the normal fast path;
    acquired=False → the detector defers, simulating an in-flight partial exit."""
    @asynccontextmanager
    async def _cm(trade_id):
        yield acquired
    return _cm


def _wire(trades, open_orders_by_ticker, *, already_alerted=0, lock_acquired=True):
    """Patch order_manager's broker + DB surface for check_position_coverage.

    open_orders_by_ticker: dict[ticker] -> list[order] OR an Exception instance
        (raised instead of returned, simulating a broker-read failure).
    already_alerted: value `_coverage_gap_already_alerted_today`'s COUNT(*) query
        returns — 0 means "not yet alerted today" (dedup lets the Telegram fire).
    lock_acquired: `_trade_advisory_try_lock` outcome — False simulates an
        in-flight partial exit holding the trade's advisory lock.
    Returns (ctx list, audited list, telegram mock, conn) for the caller to enter
    and assert against.
    """
    from agents.market_intelligence.broker import order_manager as om

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=trades)
    conn.fetchval = AsyncMock(return_value=already_alerted)

    audited: list[tuple] = []

    async def _audit(evt, summary=None, detail=None):
        audited.append((evt, summary, detail))

    async def _get_open_orders(ticker, account_mode=None, raise_on_error=False):
        val = open_orders_by_ticker.get(ticker, [])
        if isinstance(val, Exception):
            raise val
        return val

    telegram_mock = AsyncMock()

    ctx = [
        patch.object(om, "get_pool", AsyncMock(return_value=pool)),
        patch.object(om, "log_audit_event", _audit),
        patch.object(om, "_trade_advisory_try_lock", _fake_try_lock(lock_acquired)),
        patch.object(om.alpaca, "get_open_orders", AsyncMock(side_effect=_get_open_orders)),
        patch.object(om, "send_telegram_message", telegram_mock),
        patch(
            "agents.market_intelligence.collector.et_today",
            lambda: date(2026, 8, 7),
        ),
    ]
    return ctx, audited, telegram_mock, conn


async def _run_coverage_check(ctx):
    from agents.market_intelligence.broker.order_manager import check_position_coverage
    with ExitStack() as stack:
        for cm in ctx:
            stack.enter_context(cm)
        return await check_position_coverage()


@pytest.mark.asyncio
async def test_covered_book_is_silent():
    """A fully-covered position produces NO audit row and NO Telegram — a guard
    that always fires is not a guard (CLAUDE.md 2026-08-03)."""
    trades = [_trade(1, "AAPL", 4.0)]
    orders = {"AAPL": [_live_stop("s1", 4.0)]}
    ctx, audited, telegram_mock, _ = _wire(trades, orders)

    result = await _run_coverage_check(ctx)

    assert result == {"examined": 1, "covered": 1, "gaps": [], "check_failed": [], "deferred": []}
    assert audited == []
    telegram_mock.assert_not_called()


@pytest.mark.asyncio
async def test_naked_position_alerts_and_writes_position_unprotected():
    """Zero live stops on a held position → alert + `position_unprotected`."""
    trades = [_trade(1, "NAKD", 5.0)]
    orders = {"NAKD": []}
    ctx, audited, telegram_mock, _ = _wire(trades, orders)

    result = await _run_coverage_check(ctx)

    assert len(result["gaps"]) == 1
    assert result["gaps"][0]["ticker"] == "NAKD"
    assert any(evt == "position_unprotected" for evt, _, _ in audited)
    telegram_mock.assert_called_once()
    assert "NAKD" in telegram_mock.call_args[0][0]


@pytest.mark.asyncio
async def test_under_covering_stop_alerts():
    """Stop covers only 2 of 4 held shares → still a gap, must alert."""
    trades = [_trade(1, "UNDR", 4.0)]
    orders = {"UNDR": [_live_stop("s1", 2.0)]}
    ctx, audited, telegram_mock, _ = _wire(trades, orders)

    result = await _run_coverage_check(ctx)

    assert len(result["gaps"]) == 1
    assert result["gaps"][0]["live_qty"] == 2.0
    assert any(evt == "position_unprotected" for evt, _, _ in audited)
    telegram_mock.assert_called_once()


@pytest.mark.asyncio
async def test_within_half_share_tolerance_is_silent():
    """3.5 covering 4 held shares is within the codebase's standard 0.5-share
    tolerance (matches `_ensure_stop_coverage`'s own decision tree) — no gap."""
    trades = [_trade(1, "TOLR", 4.0)]
    orders = {"TOLR": [_live_stop("s1", 3.5)]}
    ctx, audited, telegram_mock, _ = _wire(trades, orders)

    result = await _run_coverage_check(ctx)

    assert result["gaps"] == []
    assert result["covered"] == 1
    assert audited == []
    telegram_mock.assert_not_called()


@pytest.mark.asyncio
async def test_broker_read_failure_fails_open_never_claims_all_clear():
    """A broker-read exception must NEVER read as "covered" — it writes
    `position_unprotected_check_failed` and the position is excluded from both
    `covered` and silently-dropped counts. (Mutation-tested — see module
    docstring: reverting this except branch to a bare swallow makes this
    assertion fail.)"""
    trades = [_trade(1, "FAIL", 4.0)]
    orders = {"FAIL": RuntimeError("alpaca timeout")}
    ctx, audited, telegram_mock, _ = _wire(trades, orders)

    result = await _run_coverage_check(ctx)

    assert result["covered"] == 0, "a broker error must never be counted as covered"
    assert len(result["check_failed"]) == 1
    assert result["check_failed"][0]["ticker"] == "FAIL"
    assert any(evt == "position_unprotected_check_failed" for evt, _, _ in audited), (
        "broker-read failure must leave a durable, loud audit row"
    )


@pytest.mark.asyncio
async def test_in_flight_partial_exit_defers_not_flags():
    """A trade whose advisory lock is held (an `execute_partial_exit` mid-flight)
    must be DEFERRED, not flagged as a gap — even though the broker momentarily
    shows zero live stops during the cancel-then-new-stop window. Flagging this
    as a naked position would be a false positive on a position that IS being
    actively re-protected right now (advisor review, #527)."""
    trades = [_trade(1, "MIDX", 4.0)]
    orders = {"MIDX": []}  # momentarily naked mid-partial — must NOT alert
    ctx, audited, telegram_mock, _ = _wire(trades, orders, lock_acquired=False)

    result = await _run_coverage_check(ctx)

    assert result["gaps"] == [], "an in-flight partial must never be read as a gap"
    assert result["deferred"] == ["MIDX"]
    assert audited == [], "a deferred trade must not write position_unprotected"
    telegram_mock.assert_not_called()


# ── Dedup: same gap on two consecutive runs → one alert (#508 idiom) ──────────


@pytest.mark.asyncio
async def test_dedup_persistent_gap_alerts_once_per_session():
    """Same ticker, same gap, two consecutive 15-min cron cycles: the audit row
    lands BOTH times (durable record — matches `stop_coverage_repaired` /
    `_profit_trigger_already_announced`'s sibling idiom), but the Telegram fires
    only on the FIRST cycle. `conn.fetchval` (the dedupe COUNT query) returns 0
    on the first check and 1 on the second, simulating "the first cycle's audit
    row now exists"."""
    from agents.market_intelligence.broker import order_manager as om

    trades = [_trade(1, "PERS", 4.0)]
    orders = {"PERS": []}
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=trades)
    conn.fetchval = AsyncMock(side_effect=[0, 1])  # not-yet-alerted, then already-alerted

    audited: list[tuple] = []

    async def _audit(evt, summary=None, detail=None):
        audited.append(evt)

    async def _get_open_orders(ticker, account_mode=None, raise_on_error=False):
        return orders.get(ticker, [])

    telegram_mock = AsyncMock()

    with patch.object(om, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(om, "log_audit_event", _audit), \
         patch.object(om, "_trade_advisory_try_lock", _fake_try_lock(True)), \
         patch.object(om.alpaca, "get_open_orders", AsyncMock(side_effect=_get_open_orders)), \
         patch.object(om, "send_telegram_message", telegram_mock), \
         patch("agents.market_intelligence.collector.et_today", lambda: date(2026, 8, 7)):
        from agents.market_intelligence.broker.order_manager import check_position_coverage
        await check_position_coverage()
        await check_position_coverage()

    assert audited.count("position_unprotected") == 2, (
        "the durable audit row must land EVERY cycle a gap persists"
    )
    assert telegram_mock.call_count == 1, (
        "the Telegram must be deduped to once per trade per session — a "
        "persistent gap must not bombard every 15 minutes (#508 lesson)"
    )


@pytest.mark.asyncio
async def test_dedup_query_guards_empty_detail_before_jsonb_cast():
    """`_coverage_gap_already_alerted_today` must filter `detail <> ''` BEFORE the
    `::jsonb` cast in its own SQL text — Postgres does not guarantee AND-clause
    evaluation order, and `log_audit_event`'s `detail` defaults to `""` for
    callers that omit it, so an unguarded cast risks `invalid input syntax for
    type json` on unrelated rows (advisor review, #527)."""
    import inspect
    from agents.market_intelligence.broker.order_manager import (
        _coverage_gap_already_alerted_today,
    )
    src = inspect.getsource(_coverage_gap_already_alerted_today)
    guard_pos = src.index("detail <> ''")
    cast_pos = src.index("detail::jsonb")
    assert guard_pos < cast_pos, (
        "the empty-string guard must appear BEFORE the ::jsonb cast in the SQL text"
    )


# ───────────────────────── Part 1: _stop_refresh telemetry ────────────────────


@pytest.mark.asyncio
async def test_stop_refresh_emits_stop_refresh_ran_even_when_nothing_placed():
    """The all-quiet case — every position already covered, nothing to place —
    must STILL produce a `stop_refresh_ran` audit row. Before Part 1, this path
    was completely silent (logger.info only), making "ran and found nothing to
    do" indistinguishable from "never ran"."""
    from agents.market_intelligence.broker import live_tracker as lt

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])  # no open positions this run

    audited: list[tuple] = []

    async def _audit(evt, summary=None, detail=None):
        audited.append((evt, summary, detail))

    with patch.object(lt, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(lt, "et_today", lambda: date(2026, 8, 7)), \
         patch.object(lt, "log_audit_event", _audit):
        count = await lt.post_close_stop_refresh()

    assert count == 0
    ran_events = [(evt, summary, detail) for evt, summary, detail in audited if evt == "stop_refresh_ran"]
    assert len(ran_events) == 1, (
        "stop_refresh_ran must fire unconditionally, including the all-quiet case"
    )
    _, summary, detail = ran_events[0]
    assert "examined 0" in summary
    assert "placed 0" in summary
    import json as _json
    parsed = _json.loads(detail)
    assert parsed["examined"] == 0
    assert parsed["placed"] == 0
    assert parsed["pass"] == "post-close"


@pytest.mark.asyncio
async def test_stop_refresh_ran_reports_already_covered_and_skip_reasons():
    """A run with one already-covered position and one skipped (no stop_price)
    must surface both in the audit row — the summary carries the label,
    examined/placed/already-covered/skipped counts; the per-ticker breakdown
    lives in `detail`, not the summary."""
    from agents.market_intelligence.broker import live_tracker as lt

    covered_trade = {
        "id": 1, "ticker": "COVR", "remaining_shares": 4.0, "stop_price": 10.0,
        "stop_order_id": "order-1", "account_mode": "live",
    }
    no_price_trade = {
        "id": 2, "ticker": "NOPR", "remaining_shares": 4.0, "stop_price": None,
        "stop_order_id": None, "account_mode": "live",
    }
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[covered_trade, no_price_trade])

    audited: list[tuple] = []

    async def _audit(evt, summary=None, detail=None):
        audited.append((evt, summary, detail))

    async def _get_order(order_id, account_mode=None):
        return {"status": "new"}  # still-active stop → "already covered" skip path

    with patch.object(lt, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(lt, "et_today", lambda: date(2026, 8, 7)), \
         patch.object(lt, "log_audit_event", _audit), \
         patch.object(lt.alpaca, "get_order", AsyncMock(side_effect=_get_order)):
        count = await lt.post_close_stop_refresh()

    assert count == 0
    ran_events = [(s, d) for evt, s, d in audited if evt == "stop_refresh_ran"]
    assert len(ran_events) == 1
    summary, detail = ran_events[0]
    assert "examined 2" in summary
    assert "already-covered 1" in summary
    assert "skipped 1" in summary
    import json as _json
    parsed = _json.loads(detail)
    assert parsed["already_covered"] == ["COVR"]
    assert parsed["skipped"] == [{"ticker": "NOPR", "reason": "no_stop_price"}]


# ─────────────── Part 2 scheduling: the 09:31-15:55 ET window is enforced ─────


def test_job_enforces_the_dod_window_not_just_the_cron_slot():
    """Advisor review, #527: the cron slot (`hour="9-15", minute="*/15"`) fires
    wider than the DoD's stated 09:31-15:55 ET window, and — unlike
    track_position_extremes — a Day-2+ position genuinely exists at 9:00/9:15.
    `_position_coverage_check_job` must enforce the window itself, in code."""
    import inspect
    from agents.market_intelligence import scheduler as sched
    src = inspect.getsource(sched._position_coverage_check_job)
    assert "now_et" in src and "_ET" in src, (
        "the job must read the current ET time and compare against the window"
    )
    assert "31" in src and "55" in src, (
        "the 09:31 / 15:55 boundaries must appear in the guard"
    )
