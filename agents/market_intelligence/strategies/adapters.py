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


async def _adapter_wick_fill(window_days: int) -> list[OutcomeRow]:
    """Wick-fill (P22) is telemetry-only — no PnL, no R. Each row is a
    candidate; `extras.filled_wick` drives the promotion fill-rate gate.
    Status maps every row to 'closed' (the candidate IS the outcome unit)
    so the n_candidates counter matches what the telemetry_review evaluator
    expects.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ticker, alert_date, close_in_range_pct, prior_high,
                   prev_5d_pct, prev_vs_sma10, prev_vs_sma50, sma50_slope_pct,
                   filled_wick, fill_date,
                   fwd_1d_from_high_pct, fwd_3d_from_high_pct, fwd_10d_from_high_pct,
                   fwd_1d_from_close_pct, fwd_3d_from_close_pct, fwd_10d_from_close_pct
            FROM mi_wick_candidates
            WHERE alert_date >= CURRENT_DATE - $1::int
            """,
            window_days,
        )
    out: list[OutcomeRow] = []
    for r in rows:
        out.append(OutcomeRow(
            strategy_id="wick_fill",
            ticker=r["ticker"],
            alert_date=r["alert_date"],
            status="closed",
            r_multiple=None,
            pnl=None,
            hold_days=None,
            closed_at=None,
            extras={
                "close_in_range_pct": float(r["close_in_range_pct"]) if r["close_in_range_pct"] is not None else None,
                "prior_high": float(r["prior_high"]) if r["prior_high"] is not None else None,
                "prev_5d_pct": float(r["prev_5d_pct"]) if r["prev_5d_pct"] is not None else None,
                "prev_vs_sma10": float(r["prev_vs_sma10"]) if r["prev_vs_sma10"] is not None else None,
                "prev_vs_sma50": float(r["prev_vs_sma50"]) if r["prev_vs_sma50"] is not None else None,
                "sma50_slope_pct": float(r["sma50_slope_pct"]) if r["sma50_slope_pct"] is not None else None,
                "filled_wick": r["filled_wick"],
                "fill_date": r["fill_date"],
                "fwd_1d_from_high_pct": float(r["fwd_1d_from_high_pct"]) if r["fwd_1d_from_high_pct"] is not None else None,
                "fwd_3d_from_high_pct": float(r["fwd_3d_from_high_pct"]) if r["fwd_3d_from_high_pct"] is not None else None,
                "fwd_10d_from_high_pct": float(r["fwd_10d_from_high_pct"]) if r["fwd_10d_from_high_pct"] is not None else None,
                "fwd_1d_from_close_pct": float(r["fwd_1d_from_close_pct"]) if r["fwd_1d_from_close_pct"] is not None else None,
                "fwd_3d_from_close_pct": float(r["fwd_3d_from_close_pct"]) if r["fwd_3d_from_close_pct"] is not None else None,
                "fwd_10d_from_close_pct": float(r["fwd_10d_from_close_pct"]) if r["fwd_10d_from_close_pct"] is not None else None,
            },
        ))
    return out


_ADAPTERS: dict[str, Callable[[int], Awaitable[list[OutcomeRow]]]] = {
    "magna53":         partial(_adapter_live_trades, signal_type="magna53"),
    "9m_day2":         partial(_adapter_live_trades, signal_type="9m_day2"),
    "shadow_orb_5m":   _adapter_shadow_orb_5m,
    "parabolic_short": _adapter_parabolic,
    "wick_fill":       _adapter_wick_fill,
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
