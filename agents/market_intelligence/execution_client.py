"""#256 W1 — execution facade: THE seam between intelligence and execution.

Intelligence-side code (detection, scheduler intelligence jobs, operator
command handlers) reaches trade execution ONLY through these functions —
never by importing `broker.*` directly. Enforced statically by
scripts/check_execution_boundary.py (deploy gate [5j/7] once W1 completes).

W1 (now): every function is a thin passthrough to the broker internals via a
FUNCTION-LOCAL import, so intelligence never imports broker at module load.
Behavior-identical to the direct imports it replaces.

W2 (process split): these bodies swap to HTTP calls against the
apollo-execution service behind `EXECUTION_MODE=inprocess|http` — call sites
don't change again. That is the whole point of the seam: the 44-site
migration happens once, here, and the transport flip is invisible.

Signatures are deliberately *args/**kwargs passthroughs in W1 (signature-
proof against broker-side evolution); W2 types them when they become wire
calls. Vocabulary (broker.skip_reasons) is NOT routed through here — it's
pure constants and stays directly importable.
"""
from __future__ import annotations

# ── Reads ────────────────────────────────────────────────────────────────────

async def get_account(*args, **kwargs):
    """Broker account snapshot (equity, buying power, blocked flags)."""
    from agents.market_intelligence.broker import alpaca_client
    return await alpaca_client.get_account(*args, **kwargs)


async def get_stream_status(*args, **kwargs):
    """Trade-stream health (per-mode connection state)."""
    from agents.market_intelligence.broker.trade_stream import get_stream_status as _f
    return _f(*args, **kwargs)


def get_data_feed_name() -> str:
    """Active market-data feed as a lowercase string ('iex' / 'sip')."""
    from agents.market_intelligence.broker.alpaca_client import get_data_feed
    return get_data_feed().value.lower()


async def verify_accounts(*args, **kwargs):
    """Boot-time smoke of every configured Alpaca account (per-mode result)."""
    from agents.market_intelligence.broker.alpaca_client import verify_dual_account_clients
    return await verify_dual_account_clients(*args, **kwargs)


# ── Detection → entry handoffs ───────────────────────────────────────────────

async def subscribe_orb_candidate(*args, **kwargs):
    """Register a pre-market HIGH with the bar stream for first-bar ORB entry."""
    from agents.market_intelligence.broker import bar_stream
    return await bar_stream.subscribe_ep_candidate(*args, **kwargs)


async def record_skipped_trade(*args, **kwargs):
    """Persist a terminal skipped-trade row (e.g. WINDOW_OUT_OF_ORB) so every
    HIGH alert has a durable state for /why + the evening brief."""
    from agents.market_intelligence.broker.live_tracker import _insert_skipped_trade
    return await _insert_skipped_trade(*args, **kwargs)


async def submit_9m_day2_trade(*args, **kwargs):
    """9M Day-2 ORB entry submission (operator command + scheduler handoff)."""
    from agents.market_intelligence.broker.live_tracker import submit_9m_day2_trade as _f
    return await _f(*args, **kwargs)


# ── Operator commands (trade-state mutations) ────────────────────────────────

async def execute_partial_exit(*args, **kwargs):
    """Operator-confirmed partial exit (/partialnow, /timestop flows)."""
    from agents.market_intelligence.broker.order_manager import execute_partial_exit as _f
    return await _f(*args, **kwargs)


async def sync_positions(*args, **kwargs):
    """DB↔Alpaca position reconcile across all enabled modes."""
    from agents.market_intelligence.broker.order_manager import sync_positions as _f
    return await _f(*args, **kwargs)


async def sync_positions_for_mode(*args, **kwargs):
    """Single-mode position reconcile (operator '/syncnow paper|live')."""
    from agents.market_intelligence.broker.order_manager import _sync_positions_for_mode
    return await _sync_positions_for_mode(*args, **kwargs)


async def place_timestop_sell(ticker: str, qty, account_mode: str,
                              strategy_tag: str = "9m_day2_timestop"):
    """Market-on-open sell for an operator-confirmed time-stop. Owns the
    mode-bound client_order_id so callers can't mint a non-canonical COID."""
    from agents.market_intelligence.broker.alpaca_client import (
        make_client_order_id, place_market_on_open_sell)
    coid = make_client_order_id(account_mode, strategy_tag, ticker)
    return await place_market_on_open_sell(
        ticker, qty=qty, account_mode=account_mode, client_order_id=coid)


async def handle_confirm_callback(*args, **kwargs):
    """Telegram inline-button confirm/reject for staged trade proposals."""
    from agents.market_intelligence.broker.telegram_confirm import handle_callback
    return await handle_callback(*args, **kwargs)
