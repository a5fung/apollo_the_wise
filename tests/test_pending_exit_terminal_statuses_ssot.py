"""Pending-exit terminal-status vocabulary — SSoT pin, plus a named exception.

P15 ("one value, three definitions, fixed in one" —
docs/roadmap/ep_profitability_program.md § THE PRINCIPLES): #591 fixed ONE of
three hand-copies of "does mi_live_orders.status mean this exit order is no
longer live" (`get_pending_exit_qty`, 2026-08-24). Alpaca's raw SDK enum value
for cancel is `canceled` (single-L — confirmed via
`alpaca.trading.enums.OrderStatus.CANCELED.value`); `reconcile_order_states`
(order_manager.py) writes that raw value straight into `mi_live_orders.status`
(`_canonical_order_status` only lowercases, it never respells), while
`_handle_cancel_or_reject` (trade_stream.py) normalizes its OWN writes to the
double-L `cancelled`. Both spellings can therefore land in the same column
depending which path wrote a row last. A follow-up review found the other two
hand-copies of `get_pending_exit_qty`'s tuple — `execute_partial_exit`'s and
`execute_full_exit`'s dedup checks (same file, both still single-l-blind).

Concrete cost of missing the single-l spelling in a DEDUP READ: a trade whose
exit order is cancelled with that spelling makes the dedup check see a
"pending exit" FOREVER — every future partial/full exit on that trade then
silently no-ops (`partial_exit_aborted`, `stage=dedup_pending_exit`) with no
operator-visible alarm. All three dedup reads now share one SSoT:
`order_manager.PENDING_EXIT_TERMINAL_STATUSES`, consumed via
`status != ALL($N::text[])`.

trade_stream.py ALSO hand-copies a narrower, related tuple three times (the
WS claim-before-update guards in `_handle_partial_fill`, `_handle_fill`,
`_handle_cancel_or_reject`: `status NOT IN ('filled', 'cancelled')`). Fixing
the spelling there was tried and REVERTED — traced in review and found to
invert the risk direction: these are WRITE claims that gate a COMMIT
(finalize_partial_exit / finalize_full_exit / stop restore), not dedup reads
that gate a skip. `reconcile_order_states` can write raw single-L 'canceled'
into a row BEFORE its WS event is processed — that race is the reconcile
job's whole purpose (#123: it exists to catch orders whose WS events were
missed, and explicitly does NOT commit trade state itself). Excluding
'canceled' from the claim-guard would make it MISS a row reconcile already
touched, silently dropping the only commit that follows. Left as three
literal `NOT IN ('filled', 'cancelled')` tuples pending an operator ruling —
a genuine divergence per P15-B ("if one genuinely must differ, that is a
finding to surface with its reason, never a silent exception"), not an
oversight.

This file pins BOTH:
  1. order_manager.py — SOURCE SCAN (no hand-copied `status NOT IN` literal
     survives; a fourth copy fails here), NAMED-CONSTANT REFERENCE (each
     consumer's own source names `PENDING_EXIT_TERMINAL_STATUSES`), and
     BEHAVIOURAL / MUTATION-PROVABLE checks (driven with a fake connection
     that applies the REAL bound parameter list against a `canceled`
     single-L order). Reverting the constant to the double-l-only spelling
     reddens every behavioural check (mutation run recorded in the commit
     message).
  2. trade_stream.py — the three known-divergent lines are named and
     excused with their reason (mirroring `_KNOWN_DIVERGENT_REASONS` in
     `tests/test_missed_outcomes_categorizer_agreement.py`); a DIFFERENT
     hand-copy, or a fourth occurrence, still fails.
"""
from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import trade_stream as ts

from tests.conftest import make_mock_pool


# ── 1a. Source scan — no hand-copied literal tuple survives in order_manager ─

def _source_lines(mod) -> list[str]:
    return inspect.getsource(mod).splitlines()


def test_no_hand_copied_status_not_in_literal_in_order_manager():
    """A fresh `status NOT IN (...)` is exactly how this bug keeps recurring —
    every "is this order still live" exclusion must route through
    PENDING_EXIT_TERMINAL_STATUSES via `!= ALL($N::text[])` instead."""
    offenders = [ln for ln in _source_lines(om) if "status NOT IN ('" in ln]
    assert not offenders, (
        "a hand-copied 'status NOT IN' literal reappeared in order_manager.py — "
        "route through PENDING_EXIT_TERMINAL_STATUSES instead:\n" + "\n".join(offenders)
    )


# ── 1b. order_manager consumers name the shared constant ────────────────────

_OM_PENDING_EXIT_CONSUMERS = ("get_pending_exit_qty", "execute_partial_exit", "execute_full_exit")


@pytest.mark.parametrize("fn_name", _OM_PENDING_EXIT_CONSUMERS)
def test_order_manager_consumer_names_the_shared_constant(fn_name):
    src = inspect.getsource(getattr(om, fn_name))
    assert "PENDING_EXIT_TERMINAL_STATUSES" in src, (
        f"{fn_name} no longer references the shared constant by name — "
        "a hand-copy or a silent rename would pass every other check here"
    )


# ── 1c. order_manager behavioural / mutation-provable ───────────────────────
# Each helper drives just far enough into the real function to capture the
# dedup query's bound parameters, then applies them the same way Postgres'
# `!= ALL($N::text[])` would: a row whose status is IN the bound list does
# not count as "still pending". Reverting the shared constant to the
# double-l-only spelling makes 'canceled' fail to appear in that bound list,
# so the single-l order counts as pending again — every assertion below goes
# red on that mutation (mutation run recorded in the commit message).


@pytest.mark.asyncio
async def test_get_pending_exit_qty_excludes_a_single_l_cancelled_order():
    orders = [
        {"qty": 5, "status": "canceled"},   # single-L — the bug if excluded here
        {"qty": 7, "status": "cancelled"},  # double-L — already excluded pre-fix
        {"qty": 3, "status": "new"},        # genuinely still pending
    ]

    async def _fetchval(_sql, _trade_id, statuses):
        return sum(o["qty"] for o in orders if o["status"] not in statuses)

    pool, conn = make_mock_pool()
    conn.fetchval = _fetchval
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)):
        assert await om.get_pending_exit_qty(367) == 3


async def _execute_partial_exit_dedup_statuses(monkeypatch) -> list[str]:
    """Drive execute_partial_exit just past its dedup fetchrow and return the
    bound status-list parameter from that call."""
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value="paper")  # breaker account_mode lookup
    conn.fetchrow = AsyncMock(side_effect=[
        {"ticker": "TEST"},                                    # trade lookup
        {"alpaca_order_id": "x", "qty": 1, "purpose": "partial_exit"},  # dedup hit -> abort
    ])
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "_consecutive_partial_exit_failures", AsyncMock(return_value=0))
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())

    @asynccontextmanager
    async def _noop_lock(_trade_id):
        yield

    monkeypatch.setattr(om, "_trade_advisory_lock", _noop_lock)

    result = await om.execute_partial_exit(1, 10, force=True)
    assert result is False  # aborted on the dedup hit, as designed

    dedup_call = conn.fetchrow.await_args_list[1]
    return dedup_call.args[-1]


@pytest.mark.asyncio
async def test_execute_partial_exit_dedup_uses_the_shared_constant(monkeypatch):
    statuses = await _execute_partial_exit_dedup_statuses(monkeypatch)
    assert set(statuses) == om.PENDING_EXIT_TERMINAL_STATUSES
    assert "canceled" in statuses and "cancelled" in statuses


async def _execute_full_exit_dedup_statuses(monkeypatch) -> list[str]:
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(side_effect=[
        {"ticker": "TEST", "remaining_shares": 10},            # trade lookup
        {"alpaca_order_id": "x", "purpose": "full_exit"},      # dedup hit -> abort
    ])
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))

    result = await om.execute_full_exit(1, "test")
    assert result is False

    dedup_call = conn.fetchrow.await_args_list[1]
    return dedup_call.args[-1]


@pytest.mark.asyncio
async def test_execute_full_exit_dedup_uses_the_shared_constant(monkeypatch):
    statuses = await _execute_full_exit_dedup_statuses(monkeypatch)
    assert set(statuses) == om.PENDING_EXIT_TERMINAL_STATUSES
    assert "canceled" in statuses and "cancelled" in statuses


# ── 2. trade_stream.py — three NAMED, EXCUSED exceptions ─────────────────────
# Considered and reverted (see the module docstring above and the per-site
# comments in trade_stream.py): closing the single-l gap in these three WRITE
# claim-guards risks silently dropping a commit, the opposite direction from
# the dedup-read fix above. `_KNOWN_DIVERGENT_REASONS` shape mirrors
# tests/test_missed_outcomes_categorizer_agreement.py — a genuine divergence
# is named with its reason, not silently exempted; anything ELSE still fails.

_KNOWN_DIVERGENT_LINES = {
    "                  AND status NOT IN ('filled', 'cancelled')":
        "_handle_partial_fill terminal-partial claim — reconcile_order_states "
        "race, see trade_stream.py #591-review comment",
    "            WHERE alpaca_order_id = $1 AND status NOT IN ('filled', 'cancelled')":
        "_handle_fill / _handle_cancel_or_reject claim guards — same reason",
}


def test_trade_stream_status_not_in_literals_are_all_named_exceptions():
    """A DIFFERENT hand-copy (a new literal shape, or a fourth occurrence
    beyond the three known sites) still fails here — only the exact,
    documented lines are excused."""
    offenders = [
        ln for ln in _source_lines(ts)
        if "status NOT IN ('" in ln and ln not in _KNOWN_DIVERGENT_LINES
    ]
    assert not offenders, (
        "a new 'status NOT IN' literal appeared in trade_stream.py outside the "
        "three named #591-review exceptions — either it is a genuine fourth "
        "hand-copy (fix it) or a real new exception (name it here with its "
        "reason):\n" + "\n".join(offenders)
    )


def test_trade_stream_has_exactly_the_three_known_divergent_sites():
    """The inverse of the check above: if a future fix DOES close the gap at
    one of these sites, this goes red as a reminder to shrink the allowlist
    (and, ideally, extend the pin to the new behaviour) rather than leaving
    stale slack — the same discipline the P15-B precedent names as Finding 4
    cleanup in test_missed_outcomes_categorizer_agreement.py."""
    present = [ln for ln in _source_lines(ts) if ln in _KNOWN_DIVERGENT_LINES]
    assert len(present) == 3, (
        f"expected exactly 3 known-divergent 'status NOT IN' lines in "
        f"trade_stream.py, found {len(present)} — the allowlist is stale, "
        "update it and this test together"
    )


def _ws_order(**overrides):
    fields = dict(
        id="oid-1", symbol="TEST", status="canceled",
        filled_qty=10.0, filled_avg_price=5.0, qty=10.0, side="sell",
        order_class="simple", type="limit", limit_price=5.0, stop_price=None,
        canceled_at=None, failed_at=None, expired_at=None, updated_at=None,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


@pytest.mark.asyncio
async def test_handle_partial_fill_claim_guard_still_omits_the_single_l_spelling():
    """Documents the CURRENT (unfixed, deliberate) behaviour at the SQL level:
    the claim-guard's exclusion list still reads only 'cancelled' (double-L),
    so a row already marked single-l 'canceled' is NOT excluded and the WS
    event still gets a chance at its claim. This pins the SQL text, not the
    downstream commit — if this ever goes red because the guard started
    excluding 'canceled', the money-path consequence (a dropped commit on the
    reconcile-race) needs re-deriving before "fixing" it — see the module
    docstring."""
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(side_effect=[
        {"id": 1, "ticker": "TEST"},                       # trade lookup
        {"trade_id": 1, "purpose": None, "exit_reason": None, "qty": 10},  # claim SUCCEEDS
    ])
    with patch.object(ts, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(ts, "log_audit_event", AsyncMock()):
        data = SimpleNamespace(order=_ws_order(), qty=10.0)
        await ts._handle_partial_fill(data, "paper")

    claim_call = conn.fetchrow.await_args_list[1]
    sql = claim_call.args[0]
    assert "status NOT IN ('filled', 'cancelled')" in sql
    assert "canceled" not in sql.split("NOT IN")[1]
