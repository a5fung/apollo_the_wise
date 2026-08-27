"""#599 — "I could not check" must never be recorded as "I checked and it's fine".

THE DEFECT. `_ensure_stop_coverage` returned `str | None`, and `None` meant THREE
different things:
  * coverage was CHECKED and meets target                      → genuinely fine;
  * a partial-exit held the per-trade advisory lock            → NOTHING checked;
  * the broker open-orders read failed                         → NOTHING checked.

`retry_failed_coverage_repairs` (#596) collapsed all three with
`healed = msg is None or msg.startswith("🛡")` — parsing a Telegram emoji off a
human-facing string as a control signal. Every non-check was audited
`healed=true` / "coverage now meets target" AND spent one of the six per-trade
attempts. On recurring lock contention or broker flakiness a trade could burn the
whole budget on passes that verified nothing, drop out of the retry set, and the
exhaustion 🚨 would never fire — because every attempt looked healthy. No wrong
order was ever placed; this is an ALERTING gap on a live repair loop, the class
that hides a genuinely unprotected position.

WHAT THESE TESTS PIN:
  * the THREE outcomes are distinguishable AT THE SOURCE — `CoverageOutcome.status`,
    not the emoji prefix (which stays exactly as it was: it is the operator's
    Telegram text, and it is fine as display);
  * `_ensure_stop_coverage` (the pre-#599 wrapper every other caller uses) returns
    precisely `.message`, so those callers are unchanged;
  * a could-not-check pass writes `stop_coverage_retry_deferred`, NOT an attempt
    row: no budget spent, not reported healed, trade stays in the retry set for
    the next 5-minute cycle;
  * the exhaustion alert still fires after a run of non-checks.

Harnesses are reused, not rebuilt: `_patches` from `test_never_naked_invariant.py`
(the source-level repair surface) and `_wire`/`_run` from
`test_596_coverage_repair_retry.py` (the retry's DB + broker surface).
"""
from __future__ import annotations

from contextlib import ExitStack
from datetime import timedelta
from unittest.mock import AsyncMock

import json
import pytest

from tests.test_596_coverage_repair_retry import (
    _T0, _audit_row, _covered, _flagged, _run, _trade_row, _unverified, _wire,
)
from tests.test_never_naked_invariant import _live_stop, _patches


async def _run_outcome(harness, *, broker_qty, stop_price=95.0,
                       signal_type="magna53", account_mode="paper",
                       trade_id=221, ticker="IBM"):
    """Drive the REAL `_ensure_stop_coverage_outcome` — no mock in the middle."""
    from agents.market_intelligence.broker.order_manager import (
        _ensure_stop_coverage_outcome,
    )
    with ExitStack() as stack:
        for cm in harness["ctx"]:
            stack.enter_context(cm)
        return await _ensure_stop_coverage_outcome(
            trade_id, ticker, broker_qty, stop_price, signal_type, account_mode,
        )


async def _run_wrapper(harness, **kw):
    """Drive the pre-#599 `_ensure_stop_coverage` wrapper on the same surface."""
    from agents.market_intelligence.broker.order_manager import _ensure_stop_coverage
    kw.setdefault("stop_price", 95.0)
    with ExitStack() as stack:
        for cm in harness["ctx"]:
            stack.enter_context(cm)
        return await _ensure_stop_coverage(
            221, "IBM", kw["broker_qty"], kw["stop_price"], "magna53", "paper",
        )


# ── 1. The three outcomes, told apart at the SOURCE ──────────────────────────


@pytest.mark.asyncio
async def test_a_partial_holding_the_lock_is_reported_as_not_checked():
    """A partial-exit owns coverage while it holds the lock, so the reconciler
    skips — correctly. But skipping is NOT a coverage check, and the caller must
    be able to see that. The position LOOKS under-covered here (live 134 stop vs
    target 200), so this proves the status comes from the lock, not from a
    coincidental covered branch."""
    h = _patches([_live_stop("stop_134", 134)], pending_qty=0, lock_acquired=False)
    out = await _run_outcome(h, broker_qty=200)

    from agents.market_intelligence.broker import order_manager as om
    assert out.status == om.COVERAGE_UNVERIFIED
    assert out.reason == "partial_in_flight"
    assert out.message is None, "still silent — the message surface is unchanged"
    h["get_open"].assert_not_called()  # we bail before any broker read


@pytest.mark.asyncio
async def test_an_unreadable_broker_is_reported_as_not_checked():
    """F16 made the orders-read DEFER instead of driving the place branch on a
    false premise. #599 makes that defer VISIBLE: 'the API is down' is not a
    clean bill of health, and the retry must not bank it as one."""
    def _boom():
        raise RuntimeError("api down")

    h = _patches(_boom, pending_qty=0)
    out = await _run_outcome(h, broker_qty=200)

    from agents.market_intelligence.broker import order_manager as om
    assert out.status == om.COVERAGE_UNVERIFIED
    assert out.reason == "open_orders_read_failed"
    assert out.message is None
    h["place"].assert_not_called()
    h["replace"].assert_not_called()


@pytest.mark.asyncio
async def test_a_stop_that_meets_target_is_reported_as_verified():
    """The one `None` that always deserved to mean 'fine'. Same silent message as
    the two above, DIFFERENT status — that difference is the whole fix."""
    h = _patches([_live_stop("stop_200", 200)], pending_qty=0)
    out = await _run_outcome(h, broker_qty=200)

    from agents.market_intelligence.broker import order_manager as om
    assert out.status == om.COVERAGE_COVERED
    assert out.message is None
    h["replace"].assert_not_called()
    h["place"].assert_not_called()


@pytest.mark.asyncio
async def test_pending_exits_covering_the_position_is_also_a_verified_check():
    """target <= 0 means in-flight exits already account for the whole position.
    Nothing to protect — a CHECKED no-op, not a skipped one."""
    h = _patches([], pending_qty=200)
    out = await _run_outcome(h, broker_qty=200)

    from agents.market_intelligence.broker import order_manager as om
    assert out.status == om.COVERAGE_COVERED
    assert out.message is None


@pytest.mark.asyncio
async def test_an_actual_repair_is_reported_as_repaired_and_keeps_its_emoji():
    """The emoji prefix is the OPERATOR-FACING surface and stays exactly as it
    was — #599 only stops using it as a control signal."""
    h = _patches([_live_stop("stop_134", 134)], pending_qty=0)
    out = await _run_outcome(h, broker_qty=200)

    from agents.market_intelligence.broker import order_manager as om
    assert out.status == om.COVERAGE_REPAIRED
    assert out.message.startswith("🛡 Coverage repaired IBM")


@pytest.mark.asyncio
async def test_an_ambiguous_book_is_reported_as_flagged_not_covered():
    """Two live sell-stops: checked, and deliberately not fixed here (Phase 2b
    owns dedup). A flagged pass is a real attempt — it must keep spending budget
    and keep reaching the exhaustion alert."""
    h = _patches([_live_stop("s1", 100), _live_stop("s2", 100)], pending_qty=0)
    out = await _run_outcome(h, broker_qty=200)

    from agents.market_intelligence.broker import order_manager as om
    assert out.status == om.COVERAGE_FLAGGED
    assert out.message.startswith("⚠️")


# ── 2. Every pre-#599 caller is unchanged ────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("build,broker_qty,expected", [
    (lambda: _patches([_live_stop("stop_134", 134)], pending_qty=0,
                      lock_acquired=False), 200, None),
    (lambda: _patches([_live_stop("stop_200", 200)], pending_qty=0), 200, None),
    (lambda: _patches([_live_stop("stop_134", 134)], pending_qty=0), 200,
     "🛡 Coverage repaired IBM"),
])
async def test_the_wrapper_returns_exactly_the_message_field(build, broker_qty,
                                                             expected):
    """`_sync_positions_for_mode`, `execute_partial_exit`'s abort and breakeven
    re-protect paths, and `trade_stream`'s OCO-cancel re-protect all call
    `_ensure_stop_coverage` and batch its string into a Telegram. They were not
    touched by #599 because the wrapper hands back `.message` verbatim — including
    `None` for BOTH no-op kinds, which is what those callers already handle (their
    fallback line says "coverage already met, or broker read failed")."""
    out = await _run_wrapper(build(), broker_qty=broker_qty)
    if expected is None:
        assert out is None
    else:
        assert out.startswith(expected)


# ── 3. A could-not-check pass does not spend the budget ──────────────────────


@pytest.mark.asyncio
async def test_a_pass_that_could_not_check_spends_no_attempt_and_is_not_healed():
    """THE FIX. Pre-#599 this pass wrote `stop_coverage_retry_attempted` with
    `healed=true` / "coverage now meets target" and burned one of six attempts —
    for a pass that read nothing. Now it writes a deferred row, spends nothing,
    and the trade stays in the retry set for the next 5-minute cycle."""
    h = _wire([_audit_row("stop_coverage_repair_failed", 221)], _trade_row(),
              coverage_outcome=_unverified("partial_in_flight"))
    result = await _run(h)

    assert result["deferred"] == 1
    assert result["retried"] == 0 and result["resolved"] == 0
    events = [evt for evt, _, _ in h["audited"]]
    assert "stop_coverage_retry_deferred" in events
    assert "stop_coverage_retry_attempted" not in events, \
        "a non-check must never be recorded as an attempt"
    detail = json.loads(next(d for evt, _, d in h["audited"]
                             if evt == "stop_coverage_retry_deferred"))
    assert detail["attempts_used"] == 0 and detail["reason"] == "partial_in_flight"
    h["telegram"].assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unreadable_broker_pass_also_spends_no_attempt():
    """The second could-not-check variant — broker flakiness, not contention.
    `get_open_orders` fires its own deduped alpaca alert before re-raising, so the
    operator already hears about the read failure itself; what must not happen is
    this pass being banked as coverage evidence."""
    h = _wire([_audit_row("stop_coverage_repair_failed", 221)], _trade_row(),
              coverage_outcome=_unverified("open_orders_read_failed"))
    result = await _run(h)

    assert result["deferred"] == 1 and result["retried"] == 0
    assert "stop_coverage_retry_attempted" not in [e for e, _, _ in h["audited"]]


@pytest.mark.asyncio
async def test_deferred_rows_in_the_audit_log_never_consume_the_budget():
    """The state fold reads the day's rows back. Six deferred rows must leave the
    budget untouched — if they were counted (the old `else: attempts += 1`
    catch-all), the trade would be 'exhausted' having never been checked once."""
    rows = [_audit_row("stop_coverage_repair_failed", 221)]
    rows += [_audit_row("stop_coverage_retry_deferred", 221,
                        at=_T0 + timedelta(minutes=i)) for i in range(1, 7)]
    h = _wire(rows, _trade_row(), coverage_outcome=_covered())
    result = await _run(h)

    assert result["exhausted"] == 0
    assert result["retried"] == 1, "still allowed a real attempt"
    attempt = json.loads(next(d for evt, _, d in h["audited"]
                              if evt == "stop_coverage_retry_attempted"))
    assert attempt["attempt"] == 1, "deferrals must not advance the attempt counter"


# ── 4. The exhaustion alert can still fire ───────────────────────────────────


@pytest.mark.asyncio
async def test_the_exhaustion_alert_still_fires_after_a_run_of_non_checks():
    """WHY #599 MATTERS. Five real attempts plus a run of non-checks: the sixth
    real failure must still reach the operator. Pre-#599 those non-checks would
    have looked healed AND eaten attempts, so the trade would have fallen out of
    the retry set in silence."""
    rows = [_audit_row("stop_coverage_repair_failed", 221)]
    rows += [_audit_row("stop_coverage_retry_attempted", 221,
                        at=_T0 + timedelta(minutes=i)) for i in range(1, 6)]
    rows += [_audit_row("stop_coverage_retry_deferred", 221,
                        at=_T0 + timedelta(minutes=10 + i)) for i in range(3)]
    h = _wire(rows, _trade_row(),
              coverage_outcome=_flagged("⚠️ IBM: failed to widen stop coverage"))
    result = await _run(h)

    assert result["retried"] == 1 and result["resolved"] == 0
    h["telegram"].assert_awaited_once()
    assert "Coverage still broken" in h["telegram"].await_args.args[0]


@pytest.mark.asyncio
async def test_a_verified_covered_pass_still_closes_the_loop():
    """The good `None` keeps working: a checked-and-covered pass is healed,
    counts, and stops the retry re-driving a healthy position every five
    minutes."""
    h = _wire([_audit_row("stop_coverage_repair_failed", 221)], _trade_row(),
              coverage_outcome=_covered())
    result = await _run(h)

    assert result["retried"] == 1 and result["resolved"] == 1
    assert result["deferred"] == 0
    attempt = json.loads(next(d for evt, _, d in h["audited"]
                              if evt == "stop_coverage_retry_attempted"))
    assert attempt["healed"] is True and attempt["status"] == "covered"
