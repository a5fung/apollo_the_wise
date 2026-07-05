"""Read-only DB<->broker coverage-drift detector (#184, ADR 0008 increment 2).

ADR 0008 (docs/decisions/0008-trade-state-broker-source-of-truth.md) established
Alpaca as the single source of truth for trade state; the DB is a read-through
mirror. Increment 1 (write-side regression fence) shipped 2026-06-06. This
module is increment 2: OBSERVE-ONLY drift detection between the DB mirror and
the broker's actual book. Increment 3 (guarded auto-correction) is explicitly
OUT OF SCOPE — this module NEVER mutates trade state, never cancels/submits
an order, never touches mi_live_trades. Its only writes are `mi_audit_log`
rows (via log_audit_event) and Telegram messages (via send_telegram_message).

Three drift classes:
  D1 — UNTRACKED BROKER POSITION: broker holds a position with no open DB row
       for that ticker+mode. Severity HIGH — this is the `a41e7c6a` mirror-gap
       class from the 2026-06-04 FPS false-naked incident (a stop that was
       live at the broker but had never been written to the DB at all).
  D2 — UNTRACKED OPEN ORDER: an open broker order whose id is neither the
       entry_order_id nor stop_order_id of any open DB row.
         client_order_id matches our `apollo_{mode}_` prefix → HIGH
           (system-created, then lost track of).
         anything else → INFO (the operator may trade manually in the same
           Alpaca account — not a mirror defect).
  D3 — DB-OPEN-WITHOUT-BROKER-PRESENCE: an open DB row whose ticker has no
       broker position AND no live entry order at the broker. INFO only —
       the existing sync_positions / order_status_reconcile machinery owns
       closing this direction; this module surfaces it for mirror-completeness
       telemetry, not as a fresh alarm.

Degraded-read guard (#137 class — "an empty broker read must never be
interpreted as 'everything untracked'"): this function passes
`raise_on_error=True` to the alpaca_client wrappers, so a genuine broker-read
failure RAISES instead of silently degrading to `[]`. On that raise (or a DB
read failure), this function logs `coverage_drift_check_degraded` and returns
WITHOUT reporting any drift for that mode's cycle.

Dedup is DB-sourced (mi_audit_log `coverage_drift_alerted` rows), never
module-level state — containers restart; in-process dedup state would
silently reset on the next deploy (feedback_scheduler_aggregators_db_sourced).
"""
from __future__ import annotations

import json
import logging

from agents.market_intelligence.audit_events import (
    COVERAGE_DRIFT_ALERTED,
    COVERAGE_DRIFT_CHECK_DEGRADED,
    COVERAGE_DRIFT_DETECTED,
)
from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.broker import alpaca_client as alpaca
from agents.market_intelligence.constants import mode_prefix
from agents.market_intelligence.db import get_pool, log_audit_event

logger = logging.getLogger(__name__)

# mi_live_trades statuses that mean "this trade is currently open" — the SAME
# vocabulary order_manager._check_safeguards / db.get_open_position_count use
# for MAX_CONCURRENT_LIVE_POSITIONS, reused verbatim here so "open" can never
# drift between the live safeguard's definition and this detector's.
_OPEN_TRADE_STATUSES = ("filled", "order_placed", "pending_confirmation", "confirmed")

D1_UNTRACKED_POSITION = "D1_untracked_position"
D2_UNTRACKED_ORDER_HIGH = "D2_untracked_order_high"
D2_UNTRACKED_ORDER_INFO = "D2_untracked_order_info"
D3_DB_OPEN_NO_BROKER = "D3_db_open_no_broker"

_HIGH_CLASSES = frozenset({D1_UNTRACKED_POSITION, D2_UNTRACKED_ORDER_HIGH})


async def _fetch_open_db_trades(conn, account_mode: str) -> list:
    """Open (per _OPEN_TRADE_STATUSES) mi_live_trades rows for this mode."""
    placeholders = ", ".join(f"'{s}'" for s in _OPEN_TRADE_STATUSES)
    return await conn.fetch(
        f"""
        SELECT id, ticker, entry_order_id, stop_order_id, status
        FROM mi_live_trades
        WHERE account_mode = $1
          AND status IN ({placeholders})
        """,
        account_mode,
    )


def _signature(account_mode: str, drift_class: str, ticker: str, order_id: str | None) -> str:
    """Drift-instance identity used for both the SELECT dedup check and the
    marker row written on send — mode+class+ticker+order_id, per spec."""
    return f"{account_mode}|{drift_class}|{ticker}|{order_id or ''}"


async def _already_alerted(conn, signature: str) -> bool:
    existing = await conn.fetchval(
        """
        SELECT 1 FROM mi_audit_log
        WHERE event_type = $1
          AND summary = $2
          AND created_at > NOW() - INTERVAL '24 hours'
        LIMIT 1
        """,
        COVERAGE_DRIFT_ALERTED,
        signature,
    )
    return bool(existing)


async def _maybe_telegram(conn, signature: str, message: str) -> bool:
    """Send + write the dedup marker unless a marker with this signature was
    already written in the last 24h. Returns True if sent, False if deduped."""
    if await _already_alerted(conn, signature):
        return False
    await send_telegram_message(message)
    await log_audit_event(COVERAGE_DRIFT_ALERTED, signature, "")
    return True


def _format_d1_message(account_mode: str, position: dict) -> str:
    ticker = position.get("symbol", "?")
    qty = position.get("qty")
    avg = position.get("avg_entry_price")
    return (
        f"{mode_prefix(account_mode)}🔴 *Untracked broker position — {ticker}*\n"
        f"Alpaca {account_mode} holds an open position with no matching open "
        f"trade row in the DB.\n\n"
        f"Qty: `{qty}`  Avg entry: `${avg}`\n\n"
        f"_Observe-only (ADR 0008 increment 2) — no auto-action taken. "
        f"Verify manually via /trades or the Alpaca dashboard._"
    )


def _format_d2_message(account_mode: str, order: dict) -> str:
    ticker = order.get("symbol", "?")
    order_id = order.get("id") or ""
    coid = order.get("client_order_id") or ""
    side = order.get("side", "?")
    otype = order.get("type", "?")
    return (
        f"{mode_prefix(account_mode)}🔴 *Untracked open order — {ticker}*\n"
        f"Alpaca {account_mode} has an open order Apollo appears to have placed "
        f"(client_order_id carries our `apollo_{account_mode}_` prefix) but no "
        f"open DB row references it as an entry or stop.\n\n"
        f"Order: `{side} {otype}`  ID: `{order_id[:12]}…`\n"
        f"Client order ID: `{coid}`\n\n"
        f"_Observe-only (ADR 0008 increment 2) — no auto-cancel. "
        f"Verify via /trades or the Alpaca dashboard._"
    )


async def detect_coverage_drift(account_mode: str) -> dict:
    """Compare the DB mirror against the broker's actual book for `account_mode`
    and surface drift. READ-ONLY — see module docstring for the full contract.

    Returns a summary dict: {account_mode, degraded, d1_count, d2_high_count,
    d2_info_count, d3_count, alerted, deduped}.
    """
    result = {
        "account_mode": account_mode,
        "degraded": False,
        "d1_count": 0,
        "d2_high_count": 0,
        "d2_info_count": 0,
        "d3_count": 0,
        "alerted": 0,
        "deduped": 0,
    }

    # Broker ground truth first. raise_on_error=True: a genuine read failure
    # MUST surface as "we don't know" — never silently degrade to [] and then
    # read that empty list as "broker holds nothing" (#137 mass-close class).
    try:
        positions = await alpaca.get_all_positions(account_mode=account_mode, raise_on_error=True)
        open_orders = await alpaca.get_open_orders(account_mode=account_mode, raise_on_error=True)
    except Exception as e:
        logger.error(f"coverage_drift[{account_mode}]: broker read failed, skipping this cycle: {e}")
        await log_audit_event(
            COVERAGE_DRIFT_CHECK_DEGRADED,
            f"coverage-drift check degraded ({account_mode}): broker read failed",
            f"account_mode={account_mode} error={e!r}",
        )
        result["degraded"] = True
        return result

    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            db_rows = await _fetch_open_db_trades(conn, account_mode)
        except Exception as e:
            logger.error(f"coverage_drift[{account_mode}]: DB read failed, skipping this cycle: {e}")
            await log_audit_event(
                COVERAGE_DRIFT_CHECK_DEGRADED,
                f"coverage-drift check degraded ({account_mode}): DB read failed",
                f"account_mode={account_mode} error={e!r}",
            )
            result["degraded"] = True
            return result

        db_open_tickers = {r["ticker"] for r in db_rows}
        known_order_ids = set()
        for r in db_rows:
            if r["entry_order_id"]:
                known_order_ids.add(r["entry_order_id"])
            if r["stop_order_id"]:
                known_order_ids.add(r["stop_order_id"])

        position_tickers = {p["symbol"] for p in positions}
        open_order_ids = {o["id"] for o in open_orders}

        # ── D1 — broker position with no open DB row ────────────────────────
        for p in positions:
            ticker = p["symbol"]
            if ticker in db_open_tickers:
                continue
            result["d1_count"] += 1
            await log_audit_event(
                COVERAGE_DRIFT_DETECTED,
                f"D1 untracked position {ticker} ({account_mode})",
                json.dumps({
                    "class": D1_UNTRACKED_POSITION, "severity": "HIGH",
                    "mode": account_mode, "ticker": ticker,
                    "qty": p.get("qty"), "avg_entry_price": p.get("avg_entry_price"),
                }),
            )
            signature = _signature(account_mode, D1_UNTRACKED_POSITION, ticker, None)
            if await _maybe_telegram(conn, signature, _format_d1_message(account_mode, p)):
                result["alerted"] += 1
            else:
                result["deduped"] += 1

        # ── D2 — open order not referenced by any open DB row ───────────────
        for o in open_orders:
            order_id = o["id"]
            if order_id in known_order_ids:
                continue
            ticker = o["symbol"]
            coid = o.get("client_order_id") or ""
            is_ours = coid.startswith(f"apollo_{account_mode}_")
            drift_class = D2_UNTRACKED_ORDER_HIGH if is_ours else D2_UNTRACKED_ORDER_INFO
            severity = "HIGH" if is_ours else "INFO"
            if is_ours:
                result["d2_high_count"] += 1
            else:
                result["d2_info_count"] += 1
            await log_audit_event(
                COVERAGE_DRIFT_DETECTED,
                f"{drift_class} {ticker} order={order_id[:8]} ({account_mode})",
                json.dumps({
                    "class": drift_class, "severity": severity,
                    "mode": account_mode, "ticker": ticker,
                    "order_id": order_id, "client_order_id": coid,
                    "side": o.get("side"), "type": o.get("type"),
                }),
            )
            if is_ours:
                signature = _signature(account_mode, D2_UNTRACKED_ORDER_HIGH, ticker, order_id)
                if await _maybe_telegram(conn, signature, _format_d2_message(account_mode, o)):
                    result["alerted"] += 1
                else:
                    result["deduped"] += 1
            # D2 INFO (foreign/manual order): audit-only, no Telegram — the
            # operator may be trading manually in the same Alpaca account.

        # ── D3 — open DB row absent from the broker's book ──────────────────
        for r in db_rows:
            ticker = r["ticker"]
            entry_order_id = r["entry_order_id"]
            if ticker in position_tickers:
                continue
            if entry_order_id and entry_order_id in open_order_ids:
                continue
            result["d3_count"] += 1
            await log_audit_event(
                COVERAGE_DRIFT_DETECTED,
                f"D3 db-open-no-broker {ticker} trade={r['id']} ({account_mode})",
                json.dumps({
                    "class": D3_DB_OPEN_NO_BROKER, "severity": "INFO",
                    "mode": account_mode, "ticker": ticker, "trade_id": r["id"],
                    "entry_order_id": entry_order_id, "stop_order_id": r["stop_order_id"],
                    "status": r["status"],
                }),
            )
            # INFO-only — sync_positions / order_status_reconcile own closing
            # this direction; no Telegram, per spec (mirror-completeness only).

    return result
