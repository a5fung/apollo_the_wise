"""`scripts/probes/_probe_safety.py::teardown` — #548 fix (2026-08-10).

THE DEFECT: `teardown` used to report "cancelled N/N" meaning "cancel REQUEST sent N/N", not
confirmed. `alpaca_client.cancel_order` returns True on success and swallows ANY exception
(including "already terminal") into False, and the old `teardown` never inspected that return
value; its one verify pass only checked for a FILL, never for whether the cancel actually
landed. Observed live 2026-08-10 (#548): teardown reported "cancelled 1/1" for a sell-stop a
direct `get_open_orders` check showed was STILL resting, and the probe's next order was
REJECTED citing that "cancelled" order as a live opposite-side position.

THE FIX (this file tests it): `teardown` now polls each order's own status until it reaches a
real terminal state (bounded, not a single read), classifies against that status — never the
cancel request's return value — and separately sweeps every touched symbol's open-orders list
for anything the id list missed (e.g. a `replace_order_by_id` successor, a NEW id the caller
never saw).

Every test here uses a fake broker client — no real Alpaca calls, no DB, no network. Confirm
budgets are monkeypatched down to keep the "never confirms" cases fast.

`test_unconfirmed_cancel_is_reported_loudly_not_counted` below is the fails-without-fix proof:
run manually against the git-HEAD (pre-fix) `teardown` with `git show HEAD:scripts/probes/
_probe_safety.py`, the identical stuck-at-'new' scenario returns `{"cancelled": 1, "errors":
[], "filled": []}` and prints "clean — nothing filled, nothing left behind" — the exact false
positive from #548. Not kept as a permanent git-diffing test here: once this fix is committed,
HEAD *is* the fixed code, and a test that loads "HEAD" to represent "the bug" would silently
stop proving anything while still claiming to.
"""
from __future__ import annotations

import asyncio

import pytest

from scripts.probes import _probe_safety as ps


def _order(status: str, *, symbol="F", qty=1, filled_qty=0):
    return {"id": "oid-1", "symbol": symbol, "qty": qty, "filled_qty": filled_qty,
            "status": status}


class _FakeAlpaca:
    """Minimal broker double. `orders`: oid -> list of status dicts returned in sequence on
    successive `get_order` calls (the last entry repeats once exhausted — models "status
    never changes again"). `open_orders`: symbol -> list of open-order lists, same
    repeat-last-entry semantics, consumed by `get_open_orders`."""

    def __init__(self, orders: dict[str, list[dict]] | None = None,
                 positions: dict[str, dict] | None = None,
                 open_orders: dict[str, list[list[dict]]] | None = None,
                 cancel_raises: bool = False):
        self._orders = orders or {}
        self._positions = positions or {}
        self._open_orders = open_orders or {}
        self._order_calls: dict[str, int] = {}
        self._oo_calls: dict[str, int] = {}
        self._cancel_raises = cancel_raises
        self.cancel_calls: list[str] = []
        self.closed: list[str] = []

    async def cancel_order(self, order_id, account_mode=None):
        self.cancel_calls.append(order_id)
        if self._cancel_raises:
            raise RuntimeError("simulated broker cancel failure")
        return True

    async def get_order(self, order_id, account_mode=None):
        seq = self._orders.get(order_id)
        if not seq:
            return None
        idx = self._order_calls.get(order_id, 0)
        self._order_calls[order_id] = idx + 1
        return seq[min(idx, len(seq) - 1)]

    async def get_position(self, symbol, account_mode=None):
        return self._positions.get(symbol)

    async def close_position(self, symbol, account_mode=None):
        self.closed.append(symbol)

    async def get_open_orders(self, ticker, account_mode=None, raise_on_error=False):
        seq = self._open_orders.get(ticker)
        if seq is None:
            return []
        idx = self._oo_calls.get(ticker, 0)
        self._oo_calls[ticker] = idx + 1
        return seq[min(idx, len(seq) - 1)]


@pytest.fixture(autouse=True)
def _fast_confirm_budget(monkeypatch):
    """Keep 'never confirms' test cases fast — real deadline is 10s/0.25s poll."""
    monkeypatch.setattr(ps, "_CANCEL_CONFIRM_BUDGET_S", 0.06)
    monkeypatch.setattr(ps, "_CANCEL_CONFIRM_POLL_S", 0.02)


# ── Genuinely-fine terminal cases — rule 4: no crying wolf ────────────────────────────────


@pytest.mark.asyncio
async def test_confirms_cancel_that_reaches_terminal_after_polling():
    """Status transitions new -> canceled across 2 reads: a real, confirmed cancel."""
    alpaca = _FakeAlpaca(orders={"oid-1": [_order("new"), _order("canceled")]})
    out = await ps.teardown(alpaca, ["oid-1"], account_mode="paper", symbols=[])
    assert out["cancelled"] == 1
    assert out["unconfirmed"] == []
    assert out["errors"] == []
    assert out["filled"] == []


@pytest.mark.asyncio
async def test_already_cancelled_before_request_is_not_an_error():
    alpaca = _FakeAlpaca(orders={"oid-1": [_order("canceled")]})
    out = await ps.teardown(alpaca, ["oid-1"], account_mode="paper", symbols=[])
    assert out["cancelled"] == 1
    assert out["errors"] == []


@pytest.mark.asyncio
async def test_already_filled_before_request_is_not_an_error():
    """Rule 4 + the original 2026-08-06 incident: a cancel cannot undo a fill, and that is
    not teardown's failure — it must still be flagged (existing fill-check behaviour) but not
    as an error."""
    alpaca = _FakeAlpaca(orders={"oid-1": [_order("filled", qty=1, filled_qty=1)]})
    out = await ps.teardown(alpaca, ["oid-1"], account_mode="paper", symbols=[])
    assert out["cancelled"] == 0
    assert out["errors"] == []
    assert len(out["filled"]) == 1
    assert out["filled"][0]["status"] == "filled"
    assert out["filled"][0]["symbol"] == "F"


# ── THE FIX: a cancel that never confirms must be LOUD, never counted as success ──────────


@pytest.mark.asyncio
async def test_unconfirmed_cancel_is_reported_loudly_not_counted():
    """THE defect this card fixes. Status is 'new' forever — cancel_order returns True (the
    request landed) but the order never actually leaves the book within the deadline. Old
    behaviour: cancelled 1/1, no errors, prints 'clean'. New behaviour: cancelled 0/1, a loud
    error naming the order and its stuck status, unconfirmed non-empty."""
    alpaca = _FakeAlpaca(orders={"oid-1": [_order("new")]})
    out = await ps.teardown(alpaca, ["oid-1"], account_mode="paper", symbols=[])
    assert out["cancelled"] == 0
    assert out["unconfirmed"] == ["oid-1"]
    assert len(out["errors"]) == 1
    assert "oid-1" in out["errors"][0]
    assert "still new" in out["errors"][0]
    assert out["filled"] == []


@pytest.mark.asyncio
async def test_cancel_request_return_value_is_never_trusted():
    """cancel_order raising (simulating alpaca_client's own True/False-only contract being
    violated by a test double, or a genuine transport error) must NOT stop classification —
    the order's real status still decides the outcome, per order_manager's documented
    principle this fix follows."""
    alpaca = _FakeAlpaca(orders={"oid-1": [_order("canceled")]}, cancel_raises=True)
    out = await ps.teardown(alpaca, ["oid-1"], account_mode="paper", symbols=[])
    assert out["cancelled"] == 1          # confirmed via status despite the raise
    assert any("cancel request oid-1" in e for e in out["errors"])  # the raise is still logged


@pytest.mark.asyncio
async def test_stuck_partially_filled_flags_both_filled_and_unconfirmed():
    """Rule 4 (preserve fill-check) + rule 3 (loud on non-confirm) apply SIMULTANEOUSLY here:
    a partial fill that never resolves the remainder must still show up in `filled` (existing
    behaviour) AND be reported as not-confirmed (the fix)."""
    alpaca = _FakeAlpaca(orders={"oid-1": [_order("partially_filled", qty=3, filled_qty=1)]})
    out = await ps.teardown(alpaca, ["oid-1"], account_mode="paper", symbols=[])
    assert out["cancelled"] == 0
    assert out["unconfirmed"] == ["oid-1"]
    assert len(out["filled"]) == 1
    assert out["filled"][0]["status"] == "partially_filled"
    assert any("partially filled" in e for e in out["errors"])


@pytest.mark.asyncio
async def test_unreadable_order_is_unconfirmed_not_silently_dropped():
    alpaca = _FakeAlpaca(orders={})  # get_order returns None every time -> unreadable
    out = await ps.teardown(alpaca, ["oid-ghost"], account_mode="paper", symbols=[])
    assert out["cancelled"] == 0
    assert out["unconfirmed"] == ["oid-ghost"]
    assert len(out["errors"]) == 1


# ── Symbol-level sweep (moved-in `wait_for_open_orders_clear`) ────────────────────────────


@pytest.mark.asyncio
async def test_symbol_sweep_catches_untracked_open_order():
    """Per-id confirms clean, but the symbol still shows a resting order teardown was never
    given the id for (e.g. a replace_order_by_id successor) — must be reported, and must NOT
    be silently swallowed into 'clean'."""
    alpaca = _FakeAlpaca(
        orders={"oid-1": [_order("canceled")]},
        open_orders={"F": [[{"id": "oid-2-successor", "symbol": "F", "status": "new"}]]},
    )
    out = await ps.teardown(alpaca, ["oid-1"], account_mode="paper", symbols=["F"])
    assert out["cancelled"] == 1                 # the id we knew about IS confirmed cancelled
    assert out["unswept_symbols"] == ["F"]
    assert any("open orders not confirmed clear for F" in e for e in out["errors"])


@pytest.mark.asyncio
async def test_symbol_sweep_runs_before_flatten_not_after():
    """`close_position` submits a market order — sweeping AFTER flatten would see that order
    and falsely flag it. Assert the sweep call happens before any flatten call by checking the
    sweep observes the PRE-flatten (empty) open-orders snapshot only once, and a position is
    still flattened despite an unrelated sweep failure elsewhere."""
    alpaca = _FakeAlpaca(
        orders={"oid-1": [_order("canceled")]},
        positions={"F": {"qty": "5"}},
        open_orders={"F": [[]]},   # empty on the one call the sweep is expected to make
    )
    out = await ps.teardown(alpaca, ["oid-1"], account_mode="paper", symbols=["F"])
    assert alpaca._oo_calls.get("F") == 1        # sweep polled exactly once (cleared immediately)
    assert out["unswept_symbols"] == []
    assert out["flattened"] == [{"symbol": "F", "qty": "5"}]
    assert alpaca.closed == ["F"]


@pytest.mark.asyncio
async def test_flatten_still_runs_when_sweep_cannot_confirm_clean():
    """A resting order the sweep can't clear and a real position are two independent problems
    — the sweep failing must not block flatten from doing its job."""
    alpaca = _FakeAlpaca(
        orders={"oid-1": [_order("canceled")]},
        positions={"F": {"qty": "5"}},
        open_orders={"F": [[{"id": "stuck", "symbol": "F", "status": "new"}]]},
    )
    out = await ps.teardown(alpaca, ["oid-1"], account_mode="paper", symbols=["F"])
    assert out["unswept_symbols"] == ["F"]
    assert out["flattened"] == [{"symbol": "F", "qty": "5"}]


# ── Wrong-object fallback keeps working with the new required capability ──────────────────


@pytest.mark.asyncio
async def test_wrong_object_without_get_open_orders_falls_back_loudly():
    class _ReadOnlyFacade:
        __name__ = "execution_client"

        async def cancel_order(self, *a, **k):
            raise AttributeError("no cancel here")

        async def get_order(self, *a, **k):
            raise AttributeError("no get_order here")

        async def get_position(self, *a, **k):
            return None

    out = await ps.teardown(_ReadOnlyFacade(), [], account_mode="paper", symbols=[])
    assert any("cannot cancel/read orders" in e for e in out["errors"])


if __name__ == "__main__":
    # Allow `python tests/test_probe_safety.py` for a quick manual run outside pytest.
    asyncio.run(test_unconfirmed_cancel_is_reported_loudly_not_counted())
    print("ok")
