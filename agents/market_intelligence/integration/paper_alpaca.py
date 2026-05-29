"""Paper-Alpaca integration test harness (#151, 2026-05-29).

Lives inside `agents/market_intelligence/integration/` (NOT `tests/`)
so it ships via the Dockerfile.market `COPY agents/market_intelligence/`
chain — G6 preflight runs via `docker exec apollo-market` and needs
this module importable inside the container.

Provides a context manager that:
  1. Sweeps any orphaned test orders from prior crashed runs (idempotent cleanup)
  2. Places a synthetic BUY STOP order at a price far above market
     (guaranteed to stay open since price won't reach the trigger)
  3. Yields the order_id to the test body
  4. Cancels the order on exit (even if the test body raised)

Used by:
  - Preflight Gate G6 (scripts/preflight_replace_order_smoke.py)
  - execute_partial_exit architectural split integration tests (#151 a)
  - sync_positions remediation integration tests (#151 a.2)

**Why BUY STOP at $999**: Alpaca paper rejects sell-side orders that don't
have backing shares, so we use buy-side. A stop_price far above market
(e.g., $999 for F at ~$12) ensures the order never triggers, regardless
of intraday volatility. Trigger-then-limit is via stop_limit so the order
remains identifiable + replaceable without risk of accidental fill.

**Why a sentinel COID prefix**: harness identifies test orders by
client_order_id pattern `apollo_paper_integration_test_*`. Startup
sweep cancels any matching orders from prior runs (orphan cleanup).
Production COIDs use mode/strategy/ticker pattern so there's zero
collision risk.

**Account mode**: hardcoded to 'paper'. The harness must NEVER touch
live accounts.

Author note: integration tests using this harness require live network
to paper-api.alpaca.markets. They are not part of the standard pytest
suite. Invoke explicitly via `pytest -m paper_alpaca`.
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

logger = logging.getLogger(__name__)

# Sentinel COID prefix — all test orders use this so startup-sweep can
# identify and cancel any orphans from prior crashed test runs.
_HARNESS_COID_PREFIX = "apollo_paper_integration_test"

# Default test ticker: liquid, cheap, large float so a $999 BUY STOP
# can never trigger (the price will not reach $999 — equity tickers
# don't 80x intraday). F (Ford) trades ~$12 daily.
DEFAULT_TEST_TICKER = "F"

# Stop price far above any realistic intraday move.
_FAR_STOP_PRICE = 999.0
_FAR_LIMIT_PRICE = 1000.0

# Alpaca statuses from which an order can be replaced/cancelled. A freshly
# submitted order transits pending_new → new before it's replaceable; calling
# replace during pending_new returns 422 "cannot replace order in pending_new
# status". The harness waits for one of these before yielding so consumers
# (G6, #151 (a) integration tests) get a SETTLED order — faithfully matching
# production, where execute_partial_exit replaces a stop that's been resting on
# the book since the 9:31 bracket entry (long since accepted).
_REPLACEABLE_STATUSES = {"new", "accepted", "held", "partially_filled"}


def _normalize_status(raw: str | None) -> str:
    """Normalize Alpaca status to bare lowercase token.

    Handles both the SDK enum repr ('OrderStatus.PENDING_NEW') and the bare
    wire form ('pending_new'). Mirrors order_manager._canonical_order_status.
    """
    return (raw or "").lower().split(".")[-1]


def _make_test_coid(suffix: str = "") -> str:
    """Build a sentinel-prefixed client_order_id unique per test run.

    Format: `apollo_paper_integration_test_<ms_epoch>[_<suffix>]`
    The ms_epoch makes each test's COID unique even if multiple tests
    run within the same second.
    """
    ms = int(time.time() * 1000)
    base = f"{_HARNESS_COID_PREFIX}_{ms}"
    return f"{base}_{suffix}" if suffix else base


async def _sweep_orphaned_test_orders() -> int:
    """Cancel any open orders whose client_order_id starts with the
    sentinel prefix. Idempotent: returns the count cancelled (0 if none).

    Called at the start of every harness use to clean up after any
    prior test run that crashed without reaching its cleanup phase.
    """
    from agents.market_intelligence.broker import alpaca_client

    try:
        all_orders = await alpaca_client.get_open_orders(account_mode="paper")
    except Exception as e:
        logger.warning(f"harness sweep: get_open_orders failed: {e}")
        return 0

    cancelled = 0
    for order in all_orders:
        coid = order.get("client_order_id") or ""
        if not coid.startswith(_HARNESS_COID_PREFIX):
            continue
        order_id = order.get("id")
        if not order_id:
            continue
        try:
            await alpaca_client.cancel_order(order_id, account_mode="paper")
            cancelled += 1
            logger.info(f"harness sweep: cancelled orphan {order_id} (coid={coid})")
        except Exception as e:
            logger.warning(f"harness sweep: cancel {order_id} failed: {e}")
    return cancelled


async def _wait_until_replaceable(
    order_id: str,
    *,
    timeout_s: float = 5.0,
    poll_interval_s: float = 0.25,
) -> str:
    """Poll the order until it reaches a replaceable status, then return it.

    A fresh order sits in pending_new for a few hundred ms before the broker
    accepts it. Replace/cancel during that window returns 422. Polls
    get_order until status ∈ _REPLACEABLE_STATUSES or timeout.

    Raises:
        TimeoutError: order never became replaceable within timeout_s. The
            caller's finally-block + next-run sweep still clean it up.
    """
    from agents.market_intelligence.broker import alpaca_client

    deadline = time.monotonic() + timeout_s
    last_status = "unknown"
    while time.monotonic() < deadline:
        order = await alpaca_client.get_order(order_id, account_mode="paper")
        last_status = _normalize_status(order.get("status") if order else None)
        if last_status in _REPLACEABLE_STATUSES:
            return last_status
        await asyncio.sleep(poll_interval_s)
    raise TimeoutError(
        f"test order {order_id} not replaceable after {timeout_s}s "
        f"(last status: {last_status})"
    )


@asynccontextmanager
async def paper_test_stop(
    ticker: str = DEFAULT_TEST_TICKER,
    *,
    stop_price: float = _FAR_STOP_PRICE,
    limit_price: float = _FAR_LIMIT_PRICE,
    qty: int = 1,
    suffix: str = "",
) -> AsyncIterator[str]:
    """Context manager that places a synthetic BUY STOP_LIMIT order on
    paper Alpaca, yields the order_id, and cancels-on-exit regardless of
    test outcome.

    Args:
        ticker: stock symbol. Default F (Ford ~$12, liquid).
        stop_price: trigger price. Default $999 (far above market).
        limit_price: limit price after trigger. Default $1000.
        qty: shares. Default 1.
        suffix: optional COID suffix for test identification.

    Yields:
        order_id (str): the Alpaca order_id of the placed test order.

    Cleanup:
        On exit (success OR exception), the placed order is cancelled.
        Cancellation failures are logged but do not raise — the orphan
        sweep at the next harness invocation will catch them.

    Usage:
        async with paper_test_stop() as order_id:
            new = await alpaca_client.replace_order(
                order_id, qty=2, stop_price=998.0, account_mode="paper",
            )
            assert new["id"] != order_id
            # ... assertions ...
        # order_id is now cancelled
    """
    from agents.market_intelligence.broker import alpaca_client

    # 1. Sweep any orphans from prior runs
    swept = await _sweep_orphaned_test_orders()
    if swept:
        logger.info(f"harness: pre-test sweep cancelled {swept} orphan(s)")

    # 2. Place the test order via direct alpaca-py call (no wrapper exists
    # for a bare buy stop_limit — place_bracket_order forces a stop_loss
    # leg which we don't want for the harness).
    from alpaca.trading.requests import StopLimitOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    coid = _make_test_coid(suffix=suffix or "stop")
    client = alpaca_client.get_trading_client("paper")
    request = StopLimitOrderRequest(
        symbol=ticker,
        qty=qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        stop_price=round(stop_price, 2),
        limit_price=round(limit_price, 2),
        client_order_id=coid,
    )
    placed_raw = client.submit_order(request)
    order_id = str(placed_raw.id)
    logger.info(
        f"harness: placed test {ticker} BUY STOP_LIMIT qty={qty} "
        f"stop=${stop_price} limit=${limit_price} id={order_id} coid={coid}"
    )

    try:
        # 2b. Wait for the order to settle out of pending_new before yielding.
        # Replace/cancel during pending_new returns 422; production stops are
        # always long-since-accepted by the time a partial-exit replaces them.
        settled = await _wait_until_replaceable(order_id)
        logger.info(f"harness: test order {order_id} replaceable (status={settled})")
        yield order_id
    finally:
        # 3. Cleanup — best-effort cancel. Sweep handles failures.
        try:
            await alpaca_client.cancel_order(order_id, account_mode="paper")
            logger.info(f"harness: cleanup cancelled {order_id}")
        except Exception as e:
            # The most common reason cancel fails is the order was already
            # cancelled (e.g., by replace_order returning a new id and
            # implicitly cancelling the old). That's expected — don't raise.
            logger.info(f"harness: cleanup cancel {order_id} non-fatal: {e}")
