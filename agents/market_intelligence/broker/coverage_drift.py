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
       entry_order_id nor stop_order_id of ANY mi_live_trades row for this
       mode — ANY status, not just open. Order ids are unique broker UUIDs,
       so a terminal (cancelled/closed) row referencing an order_id
       definitively means that order is tracked; matching only OPEN rows
       falsely flagged the cancel window (CLSK 2026-07-07: broker order still
       open while the DB row was already `cancelled` by the 10:00 ET
       ORB-unfilled cleanup → false 🔴 "untracked open order").
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
from agents.market_intelligence.db import get_pool, log_audit_event, OPEN_POSITION_STATUSES
from agents.market_intelligence.integration.paper_alpaca import _HARNESS_COID_PREFIX

logger = logging.getLogger(__name__)

# mi_live_trades statuses that mean "this trade is currently open" — imported from
# db.OPEN_POSITION_STATUSES (the SINGLE source of truth also used by
# db.get_open_position_count + live_tracker._check_safeguards for
# MAX_CONCURRENT_LIVE_POSITIONS) so "open" can NEVER drift between the live cap
# safeguard and this detector. Inert `pending_confirmation` proposals are excluded
# there (#436 fork B) — so a stale staged-paper proposal no longer falsely trips
# D3_DB_OPEN_NO_BROKER every reconcile cycle (the 32-event/day noise on 2026-07-06).
_OPEN_TRADE_STATUSES = OPEN_POSITION_STATUSES

D1_UNTRACKED_POSITION = "D1_untracked_position"
D2_UNTRACKED_ORDER_HIGH = "D2_untracked_order_high"
D2_UNTRACKED_ORDER_INFO = "D2_untracked_order_info"
D3_DB_OPEN_NO_BROKER = "D3_db_open_no_broker"

_HIGH_CLASSES = frozenset({D1_UNTRACKED_POSITION, D2_UNTRACKED_ORDER_HIGH})

# Per-cycle Telegram cap (d3 review): a systemic mirror-gap event (many
# untracked positions after an outage) is exactly when this detector matters
# most — and exactly when one-message-per-ticker would hit Telegram's per-chat
# rate limit and start dropping alerts. First N fire individually; the rest
# roll into one summary line (grouped-digest house pattern). Every detection
# still writes its own audit row regardless.
_TELEGRAM_CAP_PER_CYCLE = 3


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


async def _fetch_all_known_order_ids(conn, account_mode: str) -> set[str]:
    """Every order_id referenced by ANY mi_live_trades row for this mode —
    entry_order_id ∪ stop_order_id, ANY status (open AND terminal).

    This is D2's tracking set ONLY. Order ids are unique broker UUIDs, so a
    terminal (cancelled/closed) row referencing an order_id definitively means
    that order is tracked — a broker order in its cancel window (still open at
    the broker, DB row already `cancelled` by the 10:00 ET ORB-unfilled
    cleanup) is NOT drift (the CLSK 2026-07-07 false positive). A genuine
    orphan — an apollo-prefixed order NO row references in any status — is
    unaffected and still fires D2 HIGH.

    D1/D3 deliberately do NOT use this: they key on OPEN rows/tickers
    (`_fetch_open_db_trades`) — a cancelled row has no live position, so a
    broker position for that ticker IS still untracked (D1 must fire).

    Read-only; unbounded on purpose (no time window) — a recency cut would
    reintroduce the false positive for orders referenced by older rows. Cheap:
    two columns off one mode's rows (idx_live_trades_account_mode), and the
    table is a personal trade log, not market data.

    ⚠ SECOND CONSUMER: order_ingest._fetch_claimed_order_ids reuses this as
    R2's tracking set — the SAME cleanup-window race false-fired D2 and R2
    together on CLSK 2026-07-14, and sharing the helper is what keeps
    detection's and ingest's notions of "tracked" from drifting apart again.
    Changes here change ingest's race guard too.

    #566 (2026-08-15): mi_live_orders.alpaca_order_id is UNIONED in. Managed
    exit orders — the resting +2R limit, the OCO parent, the OCO stop leg —
    are tracked ONLY there (the WS fill router keys on mi_live_orders.purpose;
    they are never a trade row's entry/stop pointer), so without this a
    perfectly-tracked resting GTC limit fired D2 HIGH "untracked open order"
    every 24h dedup window for as long as it rested. Mode-unfiltered on
    purpose (broker order ids are unique UUIDs — the same rationale as
    order_ingest's own union, which this now mirrors, keeping detection's and
    ingest's sets identical again)."""
    rows = await conn.fetch(
        """
        SELECT entry_order_id, stop_order_id
        FROM mi_live_trades
        WHERE account_mode = $1
          AND (entry_order_id IS NOT NULL OR stop_order_id IS NOT NULL)
        """,
        account_mode,
    )
    known: set[str] = set()
    for r in rows:
        if r["entry_order_id"]:
            known.add(r["entry_order_id"])
        if r["stop_order_id"]:
            known.add(r["stop_order_id"])
    order_rows = await conn.fetch(
        "SELECT alpaca_order_id FROM mi_live_orders WHERE alpaca_order_id IS NOT NULL"
    )
    known.update(r["alpaca_order_id"] for r in order_rows)
    return known


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


# (per-signature send helper folded into detect_coverage_drift's _alert
#  closure when the per-cycle cap landed — d3 review, 2026-07-05)


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
        f"DB trade row — any status — references it as an entry or stop.\n\n"
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
            # D2 tracking set — ANY-status rows, same degraded guard: a failed
            # read here must never be interpreted as "nothing tracked" (that
            # would mass-false-fire D2 HIGH — the #137 class).
            known_order_ids = await _fetch_all_known_order_ids(conn, account_mode)
        except Exception as e:
            logger.error(f"coverage_drift[{account_mode}]: DB read failed, skipping this cycle: {e}")
            await log_audit_event(
                COVERAGE_DRIFT_CHECK_DEGRADED,
                f"coverage-drift check degraded ({account_mode}): DB read failed",
                f"account_mode={account_mode} error={e!r}",
            )
            result["degraded"] = True
            return result

        overflow: list[str] = []  # capped alerts, rolled into one summary send

        async def _alert(signature: str, message: str, label: str) -> None:
            """Send (or roll up past the cap) + write the 24h dedup marker.
            The marker is written for rolled-up items too — the rollup IS
            their alert; they shouldn't individually re-fire next cycle."""
            if await _already_alerted(conn, signature):
                result["deduped"] += 1
                return
            if result["alerted"] < _TELEGRAM_CAP_PER_CYCLE:
                await send_telegram_message(message)
                result["alerted"] += 1
            else:
                overflow.append(label)
            await log_audit_event(COVERAGE_DRIFT_ALERTED, signature, "")

        # D1/D3 stay keyed on OPEN rows only — a cancelled row has no live
        # position, so D1 must still fire on a broker position for its ticker.
        # known_order_ids (D2 only) was fetched above from ALL-status rows.
        db_open_tickers = {r["ticker"] for r in db_rows}

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
            await _alert(signature, _format_d1_message(account_mode, p), ticker)

        # ── D2 — open order not referenced by ANY DB row (any status) ───────
        for o in open_orders:
            order_id = o["id"]
            if order_id in known_order_ids:
                continue
            ticker = o["symbol"]
            coid = o.get("client_order_id") or ""
            # #439: an integration-test harness order (`apollo_paper_integration_test_*`) starts
            # with the `apollo_paper_` prefix but is KNOWN test cruft (the paper-exercise scripts),
            # never a real mirror gap → classify INFO (audit-only), never a D2-HIGH Telegram.
            is_ours = (coid.startswith(f"apollo_{account_mode}_")
                       and not coid.startswith(_HARNESS_COID_PREFIX))
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
                await _alert(signature, _format_d2_message(account_mode, o),
                             f"{ticker} order {order_id[:8]}")
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

        if overflow:
            result["overflowed"] = len(overflow)
            shown = ", ".join(overflow[:10]) + ("…" if len(overflow) > 10 else "")
            await send_telegram_message(
                f"{mode_prefix(account_mode)}🔴 *Coverage drift: {len(overflow)} more "
                f"untracked item(s)* — {shown}\n"
                f"_Individual alerts capped at {_TELEGRAM_CAP_PER_CYCLE}/cycle; "
                f"full detail via /audit (coverage_drift_detected rows)._"
            )

    # ── Broker→DB mirror REPAIR (#184b, ADR 0008 inc-2b) — runs AFTER detection completes, in its
    # OWN guard: a throw in ingest must NEVER abort the FL-4-load-bearing detection above. Reuses
    # this cycle's already-fetched broker/DB reads. Dark by default (fail-CLOSED toggle → 'off').
    try:
        from agents.market_intelligence.broker.order_ingest import run_ingest
        await run_ingest(account_mode, positions, open_orders, db_rows)  # logs+audits its own actions
    except Exception as e:  # loud-ok (#381): surface + continue; detection result already stands
        logger.error(f"coverage_drift[{account_mode}]: ingest step failed (detection unaffected): {e}",
                     exc_info=True)
        await log_audit_event("ingest_error", f"ingest step raised ({account_mode})",
                              json.dumps({"account_mode": account_mode, "error": repr(e)}))

    return result
