"""#596 — a FAILED coverage repair now gets re-driven on a schedule.

THE HOLE. When `_ensure_stop_coverage` fails to repair, the position can be left
genuinely unprotected — the leg-safe widen's `naked` / `stop_filled` outcomes mean
the old stop is confirmed gone with no replacement. That produced ONE 🚨 Telegram
and then nothing: `check_position_coverage` (every 15 min) only DETECTS by design,
and the next scheduled REPAIR is `sync_positions` inside `eod_cleanup` at 16:05 ET.
A failure at 09:31 could therefore sit unrepaired for the entire session.

`retry_failed_coverage_repairs` closes that. It is NOT a second repair mechanism:
it re-runs the SAME signed `_ensure_stop_coverage` (#151/#523) off FRESH broker
truth, and decides only WHEN. Nothing here changes a stop price, a target, or a
size.

WHAT THESE TESTS PIN:
  * a failure with no later success is retried; a failure already followed by a
    repair is not (the audit log IS the state — same idiom as
    `_coverage_gap_already_alerted_today`);
  * `stop_coverage_breach` never starts a retry AND a breach recorded after a
    failure ends one — a stop above market is structurally un-retryable, the
    invariant converges on it by design, and the breach-exit is the operator's call;
  * broker truth is re-read per attempt, never the qty the failed attempt carried;
  * attempts are bounded per trade per ET day, and the LAST one tells the operator
    it is giving up rather than going quiet;
  * a trade that closed or went flat since the failure is skipped.

⚠ #599 moved the retry onto `_ensure_stop_coverage_outcome` (the structured
result) so it can tell "checked, and covered" from "could not check". These
tests patch THAT function; the outcome-distinction tests themselves live in
`tests/test_599_coverage_outcome_distinction.py`, which reuses `_wire` / `_run`
from here.

Mocking mirrors `tests/test_position_coverage_check_527.py`.
"""
from __future__ import annotations

from contextlib import ExitStack
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import json
import pytest

from tests.conftest import make_mock_pool


_T0 = datetime(2026, 8, 26, 13, 40, tzinfo=timezone.utc)


def _audit_row(event_type, trade_id, *, at=_T0, ticker="IBM", account_mode="live",
               detail=None):
    body = {"trade_id": trade_id, "ticker": ticker, "account_mode": account_mode}
    if detail:
        body.update(detail)
    return {"event_type": event_type, "detail": json.dumps(body), "created_at": at}


def _covered():
    """#599: the invariant CHECKED and coverage meets target — the good no-op."""
    from agents.market_intelligence.broker import order_manager as om
    return om.CoverageOutcome(om.COVERAGE_COVERED, None, "live_stop_meets_target")


def _repaired(message):
    """It acted and coverage now meets target (the 🛡 messages)."""
    from agents.market_intelligence.broker import order_manager as om
    return om.CoverageOutcome(om.COVERAGE_REPAIRED, message,
                              "replaced_under_covering_stop")


def _flagged(message):
    """It checked and could not fix it (the ⚠️ / 🚨 messages)."""
    from agents.market_intelligence.broker import order_manager as om
    return om.CoverageOutcome(om.COVERAGE_FLAGGED, message, "repair_failed")


def _unverified(reason="partial_in_flight"):
    """#599: NOTHING was checked — a partial holds the advisory lock, or the
    broker orders-read failed. Pre-#599 this was the same bare `None` as
    `_covered()`, which is the whole bug."""
    from agents.market_intelligence.broker import order_manager as om
    return om.CoverageOutcome(om.COVERAGE_UNVERIFIED, None, reason)


def _trade_row(trade_id=221, ticker="IBM", remaining=100.0, account_mode="live"):
    return {"id": trade_id, "ticker": ticker, "remaining_shares": remaining,
            "stop_price": 95.0, "orb_low": 94.0, "signal_type": "magna53",
            "account_mode": account_mode}


def _wire(audit_rows, trade_row, *, position=None, coverage_outcome=None,
          coverage_side_effect=None, modes=("paper", "live")):
    """Patch order_manager's DB + broker surface for retry_failed_coverage_repairs.

    `_ensure_stop_coverage_outcome` itself is patched out — this function's job
    is SELECTION and BOUNDING, and the repair logic has its own tests
    (`test_never_naked_invariant.py`, `test_523_eton_leg_widen_replay.py`).
    `coverage_outcome` defaults to a VERIFIED-covered pass (#599); pass
    `_unverified()` for a pass that could not check at all.
    """
    from agents.market_intelligence.broker import order_manager as om

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=audit_rows)
    conn.fetchrow = AsyncMock(return_value=trade_row)

    audited: list[tuple] = []

    async def _audit(evt, summary=None, detail=None):
        audited.append((evt, summary, detail))

    ensure_mock = AsyncMock(
        return_value=coverage_outcome if coverage_outcome is not None else _covered(),
        side_effect=coverage_side_effect)
    telegram_mock = AsyncMock()
    get_position_mock = AsyncMock(
        return_value=position if position is not None else {"qty": 100.0,
                                                            "qty_available": 0.0})

    ctx = [
        patch.object(om, "get_pool", AsyncMock(return_value=pool)),
        patch.object(om, "log_audit_event", _audit),
        patch.object(om, "_ensure_stop_coverage_outcome", ensure_mock),
        patch.object(om, "send_telegram_message", telegram_mock),
        patch.object(om, "active_account_modes", lambda: list(modes)),
        patch.object(om.alpaca, "get_position", get_position_mock),
        patch("agents.market_intelligence.collector.et_today",
              lambda: date(2026, 8, 26)),
    ]
    return {"ctx": ctx, "audited": audited, "ensure": ensure_mock,
            "telegram": telegram_mock, "get_position": get_position_mock,
            "conn": conn}


async def _run(h):
    from agents.market_intelligence.broker.order_manager import (
        retry_failed_coverage_repairs,
    )
    with ExitStack() as stack:
        for cm in h["ctx"]:
            stack.enter_context(cm)
        return await retry_failed_coverage_repairs()


@pytest.mark.asyncio
async def test_an_outstanding_failure_is_retried_off_fresh_broker_truth():
    """The whole point: a repair that failed and was never followed by a success
    gets re-driven, sized on a position qty read NOW — not on whatever the failed
    attempt was holding when it gave up."""
    h = _wire([_audit_row("stop_coverage_repair_failed", 221)], _trade_row(),
              position={"qty": 82.0, "qty_available": 0.0},
              coverage_outcome=_repaired("🛡 Coverage repaired IBM: stop 19→82"))
    result = await _run(h)

    assert result["retried"] == 1 and result["resolved"] == 1
    h["get_position"].assert_awaited_once()
    args = h["ensure"].await_args.args
    assert args[0] == 221 and args[1] == "IBM"
    assert args[2] == 82.0, "must size on the qty read this pass, not the failed one's"
    assert any(evt == "stop_coverage_retry_attempted" for evt, _, _ in h["audited"])
    h["telegram"].assert_awaited_once()
    assert "Coverage retry succeeded" in h["telegram"].await_args.args[0]


@pytest.mark.asyncio
async def test_a_failure_already_followed_by_a_repair_is_left_alone():
    """The audit log is the state. A later `stop_coverage_repaired` means the gap
    closed — re-driving would burn broker reads on a healthy position every five
    minutes for the rest of the session."""
    h = _wire(
        [_audit_row("stop_coverage_repair_failed", 221, at=_T0),
         _audit_row("stop_coverage_repaired", 221, at=_T0 + timedelta(minutes=2))],
        _trade_row(),
    )
    result = await _run(h)

    assert result == {"examined": 0, "retried": 0, "resolved": 0, "exhausted": 0,
                      "deferred": 0}
    h["ensure"].assert_not_awaited()
    h["telegram"].assert_not_awaited()


@pytest.mark.asyncio
async def test_a_repair_that_predates_the_failure_does_not_count_as_resolved():
    """Ordering matters, not mere presence: an EARLIER success followed by a LATER
    failure is an OUTSTANDING failure. Comparing on existence alone would silently
    skip the second break of the day."""
    h = _wire(
        [_audit_row("stop_coverage_repaired", 221, at=_T0),
         _audit_row("stop_coverage_repair_failed", 221, at=_T0 + timedelta(minutes=5))],
        _trade_row(), coverage_outcome=_covered(),
    )
    result = await _run(h)

    assert result["retried"] == 1
    h["ensure"].assert_awaited_once()


@pytest.mark.asyncio
async def test_a_stop_above_market_breach_is_never_retried():
    """`stop_coverage_breach` is the ONE failure the invariant converges on
    deliberately — the trigger sits above the market, retrying cannot fix a price,
    and the breach-exit decision is the operator's. It must not appear in the
    retry state machine at all."""
    h = _wire([_audit_row("stop_coverage_breach", 221)], _trade_row())
    result = await _run(h)

    assert result == {"examined": 0, "retried": 0, "resolved": 0, "exhausted": 0,
                      "deferred": 0}
    h["ensure"].assert_not_awaited()
    h["telegram"].assert_not_awaited()


@pytest.mark.asyncio
async def test_a_breach_recorded_after_a_failure_ends_the_retries():
    """A retry can DISCOVER a breach: the earlier failure was transient, the
    price has since run through the stop level. `_ensure_stop_coverage` converges
    on that (one alert, no auto-exit) because the breach-exit is the operator's
    call — so the retry must stop too, not re-submit a structurally invalid stop
    five more times."""
    h = _wire(
        [_audit_row("stop_coverage_repair_failed", 221, at=_T0),
         _audit_row("stop_coverage_breach", 221, at=_T0 + timedelta(minutes=5))],
        _trade_row(),
    )
    result = await _run(h)

    assert result["retried"] == 0
    h["ensure"].assert_not_awaited()
    h["telegram"].assert_not_awaited()


@pytest.mark.asyncio
async def test_retries_are_bounded_and_the_last_one_says_it_is_giving_up():
    """A repair that has failed six times is not a transient broker hiccup. The
    cap stops an unbounded loop hammering the broker — but silence at the cap
    would recreate the once-only alert this task exists to remove, so the final
    attempt speaks."""
    rows = [_audit_row("stop_coverage_repair_failed", 221)]
    rows += [_audit_row("stop_coverage_retry_attempted", 221,
                        at=_T0 + timedelta(minutes=i)) for i in range(1, 6)]
    h = _wire(rows, _trade_row(),
              coverage_outcome=_flagged(
                  "⚠️ IBM: failed to widen stop coverage 19→82: nope"))
    result = await _run(h)

    assert result["retried"] == 1 and result["resolved"] == 0
    h["telegram"].assert_awaited_once()
    assert "Coverage still broken" in h["telegram"].await_args.args[0]

    # One more recorded attempt and the trade is skipped entirely.
    rows.append(_audit_row("stop_coverage_retry_attempted", 221,
                           at=_T0 + timedelta(minutes=6)))
    h2 = _wire(rows, _trade_row())
    result2 = await _run(h2)
    assert result2["examined"] == 1 and result2["retried"] == 0
    assert result2["exhausted"] == 1
    h2["ensure"].assert_not_awaited()


@pytest.mark.asyncio
async def test_a_trade_that_closed_since_the_failure_is_skipped():
    """The failure row outlives the position. A closed / flat row has nothing left
    to protect and must not be re-driven (the DB query filters status='filled' AND
    remaining_shares > 0, so it returns nothing)."""
    h = _wire([_audit_row("stop_coverage_repair_failed", 221)], None)
    result = await _run(h)

    assert result["retried"] == 0
    h["ensure"].assert_not_awaited()
    h["get_position"].assert_not_awaited()


@pytest.mark.asyncio
async def test_a_position_flat_at_the_broker_is_skipped():
    """DB says shares remain, broker says zero. Broker truth wins — the invariant
    is never driven off a position that no longer exists."""
    h = _wire([_audit_row("stop_coverage_repair_failed", 221)], _trade_row(),
              position={"qty": 0.0, "qty_available": 0.0})
    result = await _run(h)

    assert result["retried"] == 0
    h["ensure"].assert_not_awaited()


@pytest.mark.asyncio
async def test_a_mode_this_container_does_not_own_is_skipped():
    """Dual-account invariant 3: never act on a trade whose account_mode this
    container is not authoritative for (a paper-only dev container must not touch
    live rows)."""
    h = _wire([_audit_row("stop_coverage_repair_failed", 221)],
              _trade_row(account_mode="live"), modes=("paper",))
    result = await _run(h)

    assert result["retried"] == 0
    h["ensure"].assert_not_awaited()


@pytest.mark.asyncio
async def test_a_malformed_audit_row_does_not_blind_the_scan():
    """`mi_audit_log.detail` is TEXT, so one unparseable row must be skipped, not
    fail the pass — otherwise a single bad write blinds the retry for the whole
    session."""
    bad = {"event_type": "stop_coverage_repair_failed", "detail": "{not json",
           "created_at": _T0}
    h = _wire([bad, _audit_row("stop_coverage_repair_failed", 221)], _trade_row(),
              coverage_outcome=_covered())
    result = await _run(h)

    assert result["retried"] == 1


@pytest.mark.asyncio
async def test_the_invariant_raising_is_recorded_not_propagated():
    """One trade's exception must not abort the pass for every other trade with an
    outstanding failure."""
    h = _wire([_audit_row("stop_coverage_repair_failed", 221)], _trade_row(),
              coverage_side_effect=RuntimeError("broker exploded"))
    result = await _run(h)

    assert result["retried"] == 1 and result["resolved"] == 0
    attempt = next(d for evt, _, d in h["audited"]
                   if evt == "stop_coverage_retry_attempted")
    assert "broker exploded" in json.loads(attempt)["outcome"]


@pytest.mark.asyncio
async def test_job_is_execution_owned_and_registered():
    """`broker/` runs on apollo-execution, so this job must be declared there —
    an unclassified job silently routes to intelligence, where the broker clients
    are not bootstrapped."""
    from agents.market_intelligence import scheduler as sched

    assert "stop_coverage_repair_retry" in sched.EXECUTION_OWNED_JOB_IDS


@pytest.mark.asyncio
async def test_job_no_ops_outside_the_market_window():
    """Same window guard as `position_coverage_check`: the hour="9-15" cron slot
    fires wider than 09:31-15:55, so the window is enforced in code."""
    from agents.market_intelligence import scheduler as sched

    called = AsyncMock(return_value={"examined": 0, "retried": 0, "resolved": 0,
                                     "exhausted": 0, "deferred": 0})
    with patch("agents.market_intelligence.broker.order_manager"
               ".retry_failed_coverage_repairs", called), \
         patch("agents.market_intelligence.constants.LIVE_TRADING_ENABLED", True), \
         patch.object(sched, "datetime") as dt:
        dt.now.return_value = datetime(2026, 8, 26, 9, 15, tzinfo=timezone.utc)
        await sched._stop_coverage_repair_retry_job()
    called.assert_not_awaited()
