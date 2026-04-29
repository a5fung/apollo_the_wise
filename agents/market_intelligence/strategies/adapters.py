"""Per-strategy outcome adapters.

Each adapter reads a strategy's existing outcome table and maps rows to
the canonical `OutcomeRow` shape. This isolates the framework's promotion
checker / aggregators from the underlying schema differences.

Convention: adapters return rows with `alert_date >= today - window_days`.
Status values are drawn from a fixed vocabulary so callers can filter
without knowing per-strategy enum subtleties:

    'closed'        — trade exited, R/PnL final
    'open'          — trade entered, position still live
    'no_entry'      — alert valid but didn't trigger entry
    'gate_blocked'  — alert valid but blocked by safeguard/gate
    'pending'       — initial state pre-9:31 ORB
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import partial
from typing import Awaitable, Callable

from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutcomeRow:
    strategy_id: str
    ticker: str
    alert_date: date
    status: str
    r_multiple: float | None
    pnl: float | None
    hold_days: int | None
    closed_at: datetime | None
    extras: dict = field(default_factory=dict)


def _normalize_live_status(status: str | None) -> str:
    """Map mi_live_trades.status → canonical status enum."""
    if not status:
        return "pending"
    if status == "closed":
        return "closed"
    if status in ("skipped",):
        return "gate_blocked"
    if status in ("traded", "confirmed", "filled", "order_placed"):
        return "open"
    if status in ("pending_confirmation", "proposed", "pending"):
        return "pending"
    return status


async def _adapter_live_trades(window_days: int, *, signal_type: str) -> list[OutcomeRow]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ticker, alert_date, status, total_pnl, risk_dollars,
                   hold_days, closed_at, score_tier, catalyst_quality, skip_reason
            FROM mi_live_trades
            WHERE signal_type = $1
              AND alert_date >= CURRENT_DATE - $2::int
            """,
            signal_type, window_days,
        )
    out: list[OutcomeRow] = []
    for r in rows:
        risk = float(r["risk_dollars"] or 0)
        pnl = float(r["total_pnl"]) if r["total_pnl"] is not None else None
        r_mult = (pnl / risk) if (pnl is not None and risk > 0) else None
        out.append(OutcomeRow(
            strategy_id=signal_type,
            ticker=r["ticker"],
            alert_date=r["alert_date"],
            status=_normalize_live_status(r["status"]),
            r_multiple=r_mult,
            pnl=pnl,
            hold_days=r["hold_days"],
            closed_at=r["closed_at"],
            extras={
                "score_tier": r["score_tier"],
                "catalyst_quality": r["catalyst_quality"],
                "skip_reason": r["skip_reason"],
            },
        ))
    return out


async def _adapter_shadow_orb_5m(window_days: int) -> list[OutcomeRow]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ticker, alert_date, status, total_pnl, risk_dollars,
                   hold_days, closed_at, signal_type AS underlying_signal,
                   shape_tag, score_tier
            FROM mi_orb_shadow_trades
            WHERE bar_size_minutes = 5
              AND alert_date >= CURRENT_DATE - $1::int
            """,
            window_days,
        )
    out: list[OutcomeRow] = []
    for r in rows:
        risk = float(r["risk_dollars"] or 0)
        pnl = float(r["total_pnl"]) if r["total_pnl"] is not None else None
        r_mult = (pnl / risk) if (pnl is not None and risk > 0) else None
        out.append(OutcomeRow(
            strategy_id="shadow_orb_5m",
            ticker=r["ticker"],
            alert_date=r["alert_date"],
            status=r["status"] or "pending",
            r_multiple=r_mult,
            pnl=pnl,
            hold_days=r["hold_days"],
            closed_at=r["closed_at"],
            extras={
                "underlying_signal": r["underlying_signal"],
                "shape_tag": r["shape_tag"],
                "score_tier": r["score_tier"],
            },
        ))
    return out


async def _adapter_parabolic(window_days: int) -> list[OutcomeRow]:
    """Parabolic Short is telemetry-only — no PnL, no R.

    Each climax row represents a setup the system flagged. Promotion uses
    the `telemetry_review` model: forward-return + manual-review pass rate.
    Status maps every climax to 'closed' (the alert itself is the outcome
    unit) so the n_closed counter is meaningful.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ticker, scan_date, stage, score, prior_move_pct,
                   roc_5d, roc_20d, excluded_reason, excluded_source
            FROM mi_parabolic_candidates
            WHERE stage = 'climax'
              AND scan_date >= CURRENT_DATE - $1::int
            """,
            window_days,
        )
    out: list[OutcomeRow] = []
    for r in rows:
        out.append(OutcomeRow(
            strategy_id="parabolic_short",
            ticker=r["ticker"],
            alert_date=r["scan_date"],
            status="closed",
            r_multiple=None,
            pnl=None,
            hold_days=None,
            closed_at=None,
            extras={
                "stage": r["stage"],
                "score": r["score"],
                "prior_move_pct": float(r["prior_move_pct"]) if r["prior_move_pct"] is not None else None,
                "roc_5d": float(r["roc_5d"]) if r["roc_5d"] is not None else None,
                "roc_20d": float(r["roc_20d"]) if r["roc_20d"] is not None else None,
                "excluded_reason": r["excluded_reason"],
                "excluded_source": r["excluded_source"],
            },
        ))
    return out


_ADAPTERS: dict[str, Callable[[int], Awaitable[list[OutcomeRow]]]] = {
    "magna53":         partial(_adapter_live_trades, signal_type="magna53"),
    "9m_day2":         partial(_adapter_live_trades, signal_type="9m_day2"),
    "shadow_orb_5m":   _adapter_shadow_orb_5m,
    "parabolic_short": _adapter_parabolic,
}


async def get_outcomes(strategy_id: str, window_days: int = 30) -> list[OutcomeRow]:
    """Dispatch to the strategy's adapter. Returns [] if no adapter is
    registered (graceful — promotion checker treats this as "no data yet").
    """
    fn = _ADAPTERS.get(strategy_id)
    if fn is None:
        logger.warning(f"no adapter registered for strategy_id={strategy_id}")
        return []
    return await fn(window_days)
