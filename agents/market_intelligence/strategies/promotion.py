"""Promotion eligibility check.

Manual promotion: this module flags eligibility; the user runs
`/strategy <id> promote` to actually flip the phase. Verdict shape and
gates dispatch on the strategy's `promotion_model` (one of
`paired_r` / `unpaired_r` / `telemetry_review`) so each strategy is
evaluated against the metrics that actually fit it.

Defaults are conservative — easy to override by editing
`mi_strategies.promotion_thresholds`.
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import date

from agents.market_intelligence.db import get_pool
from agents.market_intelligence.strategies.adapters import (
    OutcomeRow,
    get_outcomes,
)
from agents.market_intelligence.strategies.registry import (
    Strategy,
    get_strategy,
    load_strategies,
)

logger = logging.getLogger(__name__)

WINDOW_DAYS = 90  # promotion check window — wide enough to accumulate 30+ closed


@dataclass
class PromotionVerdict:
    strategy_id: str
    current_phase: str
    next_phase: str | None
    model: str
    eligible: bool
    metrics: dict = field(default_factory=dict)
    blocking_reasons: list[str] = field(default_factory=list)


def _next_phase(current: str) -> str | None:
    return {"shadow": "paper", "paper": "live", "live": None}.get(current)


def _gate_key(current: str) -> str | None:
    return {"shadow": "shadow_to_paper", "paper": "paper_to_live"}.get(current)


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


# ── Per-model evaluators ────────────────────────────────────────────────────


def _eval_unpaired_r(rows: list[OutcomeRow], thresholds: dict) -> tuple[dict, list[str]]:
    closed = [r for r in rows if r.status == "closed" and r.r_multiple is not None]
    n = len(closed)
    rs = [r.r_multiple for r in closed]
    pnls = [r.pnl for r in closed if r.pnl is not None]
    median_r = _median(rs)
    win_rate = (sum(1 for r in rs if r > 0) / n) if n else None
    metrics = {
        "n_closed": n,
        "median_r": round(median_r, 2) if median_r is not None else None,
        "win_rate": round(win_rate, 3) if win_rate is not None else None,
        "total_pnl": round(sum(pnls), 2) if pnls else 0.0,
    }
    blocking: list[str] = []
    min_closed = thresholds.get("min_closed", 30)
    if n < min_closed:
        blocking.append(f"need {min_closed} closed (have {n})")
    min_med = thresholds.get("min_median_r")
    if min_med is not None and (median_r is None or median_r < min_med):
        blocking.append(f"median R {median_r} < {min_med}")
    min_wr = thresholds.get("min_win_rate")
    if min_wr is not None and (win_rate is None or win_rate < min_wr):
        blocking.append(f"win rate {win_rate} < {min_wr}")
    max_dd = thresholds.get("max_drawdown_dollars")
    if max_dd is not None and pnls:
        running = 0.0
        peak = 0.0
        max_dd_seen = 0.0
        for p in pnls:
            running += p
            peak = max(peak, running)
            max_dd_seen = max(max_dd_seen, peak - running)
        metrics["max_drawdown_dollars"] = round(max_dd_seen, 2)
        if max_dd_seen > max_dd:
            blocking.append(f"drawdown ${max_dd_seen:.0f} > ${max_dd}")
    return metrics, blocking


async def _eval_paired_r(strategy_id: str, rows: list[OutcomeRow], thresholds: dict) -> tuple[dict, list[str]]:
    """Compare shadow strategy outcomes against the live counterpart on the
    same (ticker, alert_date). Today only `shadow_orb_5m` ↔ `mi_live_trades`
    is paired; if you add another paired strategy, extend this function.
    """
    paired_keys = {(r.ticker, r.alert_date) for r in rows if r.status == "closed"}
    if not paired_keys:
        return {"n_paired_closed": 0}, [
            f"need {thresholds.get('min_paired_closed', 30)} paired closed (have 0)"
        ]
    pool = await get_pool()
    async with pool.acquire() as conn:
        live_rows = await conn.fetch(
            """
            SELECT ticker, alert_date,
                   total_pnl, risk_dollars, status
            FROM mi_live_trades
            WHERE status = 'closed' AND risk_dollars > 0
              AND alert_date >= CURRENT_DATE - $1::int
            """,
            WINDOW_DAYS,
        )
    live_r: dict[tuple[str, date], float] = {}
    for lr in live_rows:
        if lr["total_pnl"] is None or not lr["risk_dollars"]:
            continue
        live_r[(lr["ticker"], lr["alert_date"])] = float(lr["total_pnl"]) / float(lr["risk_dollars"])

    deltas: list[float] = []
    shadow_wins = 0
    for r in rows:
        if r.status != "closed" or r.r_multiple is None:
            continue
        key = (r.ticker, r.alert_date)
        if key not in live_r:
            continue
        delta = r.r_multiple - live_r[key]
        deltas.append(delta)
        if delta > 0:
            shadow_wins += 1

    n = len(deltas)
    median_delta = _median(deltas)
    win_rate = (shadow_wins / n) if n else None
    metrics = {
        "n_paired_closed": n,
        "median_r_delta": round(median_delta, 2) if median_delta is not None else None,
        "win_rate": round(win_rate, 3) if win_rate is not None else None,
    }
    blocking: list[str] = []
    min_paired = thresholds.get("min_paired_closed", 30)
    if n < min_paired:
        blocking.append(f"need {min_paired} paired closed (have {n})")
    min_delta = thresholds.get("min_median_r_delta")
    if min_delta is not None and (median_delta is None or median_delta < min_delta):
        blocking.append(f"median R delta {median_delta} < {min_delta}")
    min_wr = thresholds.get("min_win_rate")
    if min_wr is not None and (win_rate is None or win_rate < min_wr):
        blocking.append(f"win rate {win_rate} < {min_wr}")
    return metrics, blocking


def _eval_telemetry_review(rows: list[OutcomeRow], thresholds: dict) -> tuple[dict, list[str]]:
    """Telemetry-only strategies. Configurable via thresholds:

        metric_key:      output metric name (default "n_climax_alerts")
        min_count:       minimum rows to clear (legacy "min_climax_alerts"
                         key still honored; default 20)
        min_fill_rate:   optional fill-rate gate; counts `extras.filled_wick`
                         truthy rows. Skipped when absent.
        review_required: append "manual review deferred" blocker (default True)
    """
    n = len(rows)
    metric_key = thresholds.get("metric_key", "n_climax_alerts")
    metrics: dict = {metric_key: n}
    blocking: list[str] = []

    min_count = thresholds.get("min_count", thresholds.get("min_climax_alerts", 20))
    if n < min_count:
        label = metric_key[2:] if metric_key.startswith("n_") else metric_key
        blocking.append(f"need {min_count} {label} (have {n})")

    min_fill = thresholds.get("min_fill_rate")
    if min_fill is not None and n > 0:
        filled = sum(1 for r in rows if (r.extras or {}).get("filled_wick"))
        fill_rate = filled / n
        metrics["fill_rate"] = round(fill_rate, 3)
        if fill_rate < min_fill:
            blocking.append(f"fill rate {fill_rate:.2f} < {min_fill}")

    if thresholds.get("review_required", True):
        blocking.append("manual review fields not yet captured — eligibility deferred")
    return metrics, blocking


# ── Public API ──────────────────────────────────────────────────────────────


async def check_promotion_eligibility(
    strategy_id: str,
    *,
    rows: list[OutcomeRow] | None = None,
) -> PromotionVerdict | None:
    """Eligibility check. Pass `rows` to skip the internal `get_outcomes`
    fetch when the caller already has them (e.g. /strategy <id> detail
    view, which renders recent closed rows from the same window).
    """
    strategy = await get_strategy(strategy_id)
    if strategy is None:
        return None
    next_p = _next_phase(strategy.phase)
    gate = _gate_key(strategy.phase)
    if next_p is None or gate is None:
        return PromotionVerdict(
            strategy_id=strategy_id,
            current_phase=strategy.phase,
            next_phase=None,
            model=strategy.promotion_model,
            eligible=False,
            blocking_reasons=["already at top of ladder"],
        )

    thresholds = (strategy.promotion_thresholds or {}).get(gate, {})
    if rows is None:
        rows = await get_outcomes(strategy_id, window_days=WINDOW_DAYS)

    if strategy.promotion_model == "unpaired_r":
        metrics, blocking = _eval_unpaired_r(rows, thresholds)
    elif strategy.promotion_model == "paired_r":
        metrics, blocking = await _eval_paired_r(strategy_id, rows, thresholds)
    elif strategy.promotion_model == "telemetry_review":
        metrics, blocking = _eval_telemetry_review(rows, thresholds)
    else:
        metrics, blocking = {}, [f"unknown promotion_model: {strategy.promotion_model}"]

    return PromotionVerdict(
        strategy_id=strategy_id,
        current_phase=strategy.phase,
        next_phase=next_p,
        model=strategy.promotion_model,
        eligible=(len(blocking) == 0),
        metrics=metrics,
        blocking_reasons=blocking,
    )


async def check_all_strategies() -> list[PromotionVerdict]:
    by_id = await load_strategies()
    out: list[PromotionVerdict] = []
    for sid in by_id:
        v = await check_promotion_eligibility(sid)
        if v:
            out.append(v)
    return out
