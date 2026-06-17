"""#256 W1/W2 — execution facade: THE seam between intelligence and execution.

Intelligence-side code (detection, scheduler intelligence jobs, operator
command handlers) reaches trade execution ONLY through these functions —
never by importing `broker.*` directly. Enforced statically by
scripts/check_execution_boundary.py (deploy gate [5j/7]).

Each cross-boundary function is factored into two parts:
  * `_<name>_inprocess(...)` — the broker-calling body (lazy function-local
    import, so intelligence never imports broker at module load). The
    apollo-execution HTTP routes call THESE directly (never the dispatcher, or
    we'd loop http→route→http).
  * `<name>(...)` — a thin dispatcher: `EXECUTION_MODE=http` AND a cross-listed
    fn → POST to apollo-execution; otherwise call the inprocess body. The
    44-site migration happened once (W1); the transport flip (commit 5a) is
    invisible to call sites.

NOT every facade fn crosses (advisor 6/13): `get_data_feed_name` is pure config
(reads an env var — kept local, no broker import), `verify_accounts` is
execution-only (gated off in intelligence), and `handle_confirm_callback` takes
a Telegram object (deferred, plan risk 2). These stay local passthroughs and
have no HTTP route.

A wire-hop failure RAISES `ExecutionUnreachable` — it is NEVER collapsed into a
broker empty/None default. "Couldn't reach execution" must stay distinct from
"execution answered: flat" (no_silent_trading_failures + ground_truth_verification).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime

logger = logging.getLogger(__name__)


class ExecutionUnreachable(RuntimeError):
    """Transport-level failure reaching apollo-execution over HTTP — DISTINCT
    from a broker empty/None default. A caller must NEVER treat this as "no
    positions / no account": that would turn an unreachable execution service
    into a silent false-flat. Reads that return [] / {} / None on a BROKER
    error keep doing so INSIDE execution (and serialize back honestly); only
    the wire hop raises this."""


# Functions that must run where the Alpaca creds + broker runtime state live.
# When EXECUTION_MODE=http these dispatch to apollo-execution; otherwise they run
# in-process. Pure-config / execution-only / Telegram-object fns are deliberately
# absent (see module docstring).
_CROSS_FNS = frozenset({
    "get_account", "get_position", "get_all_positions", "get_open_orders",
    "get_stream_status", "get_first_bar",
    "subscribe_orb_candidate", "reset_bar_stream_daily_state",
    "record_skipped_trade", "trigger_orb_entry",
    "submit_9m_day2_trade", "execute_partial_exit", "sync_positions",
    "sync_positions_for_mode", "place_timestop_sell",
})

# HTTP timeout is split by what the call DOES on the execution side, not one flat
# value (advisor 6/13). The trade-critical handoffs run heavy SYNCHRONOUS work in
# the execution route before responding: `trigger_orb_entry` runs the entire
# `_orb_monitor_job` (bar fetch + fade guard + Alpaca bracket submit + DB + Telegram,
# PER pending HIGH); the others do real broker round-trips / multi-mode loops. Prod
# `mi_job_runs` shows ep_scan (which wraps the orb monitor) at p95 64s / max 151s —
# a flat 15s would raise ExecutionUnreachable on intelligence WHILE execution may have
# already placed the bracket. That false-unreachable on the order path is exactly the
# silent-double/no-fire class the split must not introduce, so the command path gets
# generous headroom; only the fast reads keep the tight bound.
# CONNECT is always short: "execution is down" must fail fast (pre-open check, idle
# reads) rather than hang for the full command budget.
_HTTP_CONNECT_TIMEOUT_SECONDS = 5.0
_HTTP_READ_TIMEOUT_SECONDS = 15.0
_HTTP_COMMAND_TIMEOUT_SECONDS = 180.0

# Cross-fns that run heavy synchronous execution-side work → command (long) read
# budget. Everything else in _CROSS_FNS is a fast read/registration → read budget.
_SLOW_COMMAND_FNS = frozenset({
    "trigger_orb_entry", "submit_9m_day2_trade", "execute_partial_exit",
    "sync_positions", "sync_positions_for_mode", "place_timestop_sell",
})


def _wire_default(o):
    """JSON encoder hook — date/datetime args cross as ISO strings. This fires
    for dates ANYWHERE in the payload, including nested inside dict args (e.g.
    sugar_baby['alert_date']), so the RECEIVING `_*_inprocess` handler (or the
    DB-write it calls) MUST coerce str→date back. Do not assume a single dated
    arg — record_skipped_trade's `today` missed that and 500'd (LZB 2026-06-13)."""
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    raise TypeError(
        f"{type(o).__name__} is not JSON-serializable over the execution "
        f"wire: {o!r}")


async def _http_call(name: str, args, kwargs):
    """POST a facade call to apollo-execution. Fail LOUD on any transport error."""
    import httpx

    from agents.market_intelligence.constants import EXECUTION_SERVICE_URL
    from shared.secrets import get_secrets

    url = f"{EXECUTION_SERVICE_URL}/exec/{name}"
    body = json.dumps({"args": list(args), "kwargs": kwargs}, default=_wire_default)
    read_timeout = (_HTTP_COMMAND_TIMEOUT_SECONDS if name in _SLOW_COMMAND_FNS
                    else _HTTP_READ_TIMEOUT_SECONDS)
    timeout = httpx.Timeout(
        connect=_HTTP_CONNECT_TIMEOUT_SECONDS, read=read_timeout,
        write=_HTTP_CONNECT_TIMEOUT_SECONDS, pool=_HTTP_CONNECT_TIMEOUT_SECONDS)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                content=body,
                headers={
                    "X-Apollo-Secret": get_secrets().internal_api_secret,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return resp.json()["result"]
    except Exception as e:
        # Never swallow into a broker-empty default — see ExecutionUnreachable.
        raise ExecutionUnreachable(
            f"execution call {name!r} failed over HTTP: {type(e).__name__}: {e}"
        ) from e


async def _dispatch(name: str, inprocess_fn, args, kwargs):
    from agents.market_intelligence.constants import EXECUTION_MODE
    if EXECUTION_MODE == "http" and name in _CROSS_FNS:
        return await _http_call(name, args, kwargs)
    return await inprocess_fn(*args, **kwargs)


# ── Reads ────────────────────────────────────────────────────────────────────

async def _get_account_inprocess(*args, **kwargs):
    from agents.market_intelligence.broker import alpaca_client
    return await alpaca_client.get_account(*args, **kwargs)


async def get_account(*args, **kwargs):
    """Broker account snapshot (equity, buying power, blocked flags)."""
    return await _dispatch("get_account", _get_account_inprocess, args, kwargs)


async def _get_position_inprocess(*args, **kwargs):
    from agents.market_intelligence.broker import alpaca_client
    return await alpaca_client.get_position(*args, **kwargs)


async def get_position(*args, **kwargs):
    """Single open broker position for a ticker (None when flat)."""
    return await _dispatch("get_position", _get_position_inprocess, args, kwargs)


async def _get_all_positions_inprocess(*args, **kwargs):
    from agents.market_intelligence.broker import alpaca_client
    return await alpaca_client.get_all_positions(*args, **kwargs)


async def get_all_positions(*args, **kwargs):
    """All open broker positions (optionally per account_mode)."""
    return await _dispatch("get_all_positions", _get_all_positions_inprocess, args, kwargs)


async def _get_open_orders_inprocess(*args, **kwargs):
    from agents.market_intelligence.broker import alpaca_client
    return await alpaca_client.get_open_orders(*args, **kwargs)


async def get_open_orders(*args, **kwargs):
    """Open broker orders (optionally per account_mode)."""
    return await _dispatch("get_open_orders", _get_open_orders_inprocess, args, kwargs)


async def _get_first_bar_inprocess(ticker, trade_date, *args, **kwargs):
    from agents.market_intelligence.broker import alpaca_client
    # trade_date arrives as an ISO string over the wire; a date in-process.
    if isinstance(trade_date, str):
        trade_date = date.fromisoformat(trade_date)
    return await alpaca_client.get_first_bar(ticker, trade_date, *args, **kwargs)


async def get_first_bar(*args, **kwargs):
    """First minute bar for a ticker/date (ORB basis; health checks)."""
    return await _dispatch("get_first_bar", _get_first_bar_inprocess, args, kwargs)


async def _get_stream_status_inprocess(*args, **kwargs):
    from agents.market_intelligence.broker.trade_stream import get_stream_status as _f
    return _f(*args, **kwargs)


async def get_stream_status(*args, **kwargs):
    """Trade-stream health (per-mode connection state). Reads execution-local
    stream state, so it must run where the stream lives."""
    return await _dispatch("get_stream_status", _get_stream_status_inprocess, args, kwargs)


def get_data_feed_name() -> str:
    """Active market-data feed as a lowercase string ('iex' / 'sip'). PURE
    CONFIG (reads ALPACA_DATA_FEED) — never crosses the execution wire and needs
    no broker import, so the intelligence service can call it directly (advisor
    6/13). Mirrors broker.alpaca_client.get_data_feed()'s resolution."""
    raw = os.environ.get("ALPACA_DATA_FEED", "iex").strip().lower()
    return "sip" if raw == "sip" else "iex"


async def verify_accounts(*args, **kwargs):
    """Boot-time smoke of every configured Alpaca account (per-mode result).
    Execution-only (the boot caller is gated on runs_execution_jobs); never
    crosses — stays a local passthrough."""
    from agents.market_intelligence.broker.alpaca_client import verify_dual_account_clients
    return await verify_dual_account_clients(*args, **kwargs)


# ── Detection → entry handoffs ───────────────────────────────────────────────

async def _trigger_orb_entry_inprocess(trigger: str = "cron"):
    from agents.market_intelligence.scheduler import _orb_monitor_job
    return await _orb_monitor_job(trigger=trigger)


async def trigger_orb_entry(trigger: str = "cron"):
    """Fire the ORB entry monitor (process pending HIGH alerts → place ORB
    bracket orders) — the ONE trade-critical action that, pre-split, ran INLINE
    inside the intelligence-side ep_scan job (scheduler.py). Routing it through
    the facade is what lets the split hand it to the execution service without
    touching the call site again (#256 W2 — the silent-no-fire seam).

    inprocess → direct `_orb_monitor_job` call (byte-identical). http → POST to
    apollo-execution, whose route runs `_orb_monitor_job` THERE (creds + broker
    live in execution)."""
    return await _dispatch("trigger_orb_entry", _trigger_orb_entry_inprocess,
                           (), {"trigger": trigger})


async def _subscribe_orb_candidate_inprocess(*args, **kwargs):
    from agents.market_intelligence.broker import bar_stream
    return await bar_stream.subscribe_ep_candidate(*args, **kwargs)


async def subscribe_orb_candidate(*args, **kwargs):
    """Register a pre-market HIGH with the bar stream for first-bar ORB entry."""
    return await _dispatch("subscribe_orb_candidate", _subscribe_orb_candidate_inprocess, args, kwargs)


async def _reset_bar_stream_daily_state_inprocess(*args, **kwargs):
    from agents.market_intelligence.broker import bar_stream
    return bar_stream.reset_daily_state(*args, **kwargs)  # sync


async def reset_bar_stream_daily_state(*args, **kwargs):
    """Clear the bar stream's per-day subscription/processed state (7 AM prep).
    The bar stream runs in the EXECUTION service, so this MUST reach execution —
    pre-split it ran inline in the intelligence ep_scan_start job against the
    intelligence process's own (post-split, inert) copy, never the live stream
    (#256 W2 seam item 1)."""
    return await _dispatch("reset_bar_stream_daily_state",
                           _reset_bar_stream_daily_state_inprocess, args, kwargs)


async def _record_skipped_trade_inprocess(*args, **kwargs):
    from agents.market_intelligence.broker.live_tracker import _insert_skipped_trade
    return await _insert_skipped_trade(*args, **kwargs)


async def record_skipped_trade(*args, **kwargs):
    """Persist a terminal skipped-trade row (e.g. WINDOW_OUT_OF_ORB) so every
    HIGH alert has a durable state for /why + the evening brief."""
    return await _dispatch("record_skipped_trade", _record_skipped_trade_inprocess, args, kwargs)


async def _submit_9m_day2_trade_inprocess(*args, **kwargs):
    from agents.market_intelligence.broker.live_tracker import submit_9m_day2_trade as _f
    return await _f(*args, **kwargs)


async def submit_9m_day2_trade(*args, **kwargs):
    """9M Day-2 ORB entry submission (operator command + scheduler handoff)."""
    return await _dispatch("submit_9m_day2_trade", _submit_9m_day2_trade_inprocess, args, kwargs)


# ── Operator commands (trade-state mutations) ────────────────────────────────

async def _execute_partial_exit_inprocess(*args, **kwargs):
    from agents.market_intelligence.broker.order_manager import execute_partial_exit as _f
    return await _f(*args, **kwargs)


async def execute_partial_exit(*args, **kwargs):
    """Operator-confirmed partial exit (/partialnow, /timestop flows)."""
    return await _dispatch("execute_partial_exit", _execute_partial_exit_inprocess, args, kwargs)


async def _sync_positions_inprocess(*args, **kwargs):
    from agents.market_intelligence.broker.order_manager import sync_positions as _f
    return await _f(*args, **kwargs)


async def sync_positions(*args, **kwargs):
    """DB↔Alpaca position reconcile across all enabled modes."""
    return await _dispatch("sync_positions", _sync_positions_inprocess, args, kwargs)


async def _sync_positions_for_mode_inprocess(*args, **kwargs):
    from agents.market_intelligence.broker.order_manager import _sync_positions_for_mode
    return await _sync_positions_for_mode(*args, **kwargs)


async def sync_positions_for_mode(*args, **kwargs):
    """Single-mode position reconcile (operator '/syncnow paper|live')."""
    return await _dispatch("sync_positions_for_mode", _sync_positions_for_mode_inprocess, args, kwargs)


async def _place_timestop_sell_inprocess(ticker: str, qty, account_mode: str,
                                         strategy_tag: str = "9m_day2_timestop"):
    from agents.market_intelligence.broker.alpaca_client import (
        make_client_order_id, place_market_on_open_sell)
    coid = make_client_order_id(account_mode, strategy_tag, ticker)
    return await place_market_on_open_sell(
        ticker, qty=qty, account_mode=account_mode, client_order_id=coid)


async def place_timestop_sell(ticker: str, qty, account_mode: str,
                              strategy_tag: str = "9m_day2_timestop"):
    """Market-on-open sell for an operator-confirmed time-stop. Owns the
    mode-bound client_order_id so callers can't mint a non-canonical COID."""
    return await _dispatch(
        "place_timestop_sell", _place_timestop_sell_inprocess,
        (ticker, qty, account_mode), {"strategy_tag": strategy_tag})


async def handle_confirm_callback(*args, **kwargs):
    """Telegram inline-button confirm/reject for staged trade proposals.
    DEFERRED from HTTP (plan risk 2): the arg is a Telegram callback object, not
    JSON-serializable. Stays a local passthrough until the confirm-callback
    routing is designed (W2 step 5)."""
    from agents.market_intelligence.broker.telegram_confirm import handle_callback
    return await handle_callback(*args, **kwargs)
