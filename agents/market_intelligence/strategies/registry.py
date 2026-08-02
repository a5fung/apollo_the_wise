"""Strategy registry — load + cache + lookup.

Every new strategy entry-point function MUST consult `get_strategy()`
before doing work. Three call sites today:

    1. broker/entry_pipeline.py::submit_trade_entry  (MAGNA53, 9M Day 2)
    2. broker/shadow_orb_tracker.py::run_shadow_pass (Shadow ORB 5m)
    3. parabolic_detector.py::run_parabolic_scan    (Parabolic Short)

Without a gate at every entry point, the registry's enable/disable
surface is a no-op for strategies that don't route through the live
pipeline.

The registry cache invalidates automatically on `update_strategy()`;
direct DB edits to `mi_strategies` won't be seen until process restart
or `invalidate_cache()`. Phase / enable changes from Telegram go through
`update_strategy()`.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Strategy:
    strategy_id: str
    name: str
    family: str
    phase: str               # constants.VALID_STRATEGY_PHASES: shadow|paper|live|deprecated
    enabled: bool
    signal_type: str
    outcomes_table: str
    promotion_model: str     # 'paired_r' | 'unpaired_r' | 'telemetry_review'
    promotion_thresholds: dict = field(default_factory=dict)
    notes: str | None = None
    # Per-strategy real-$ ramp gate. Independent from `phase`. When False AND
    # account_mode='live', proposals fire with a "🟡 STAGED-PAPER ramp" header
    # so user can stage strategies (MAGNA53 first, 9M Day 2 after N clean fills)
    # without flipping every strategy to real money on flip day.
    live_real_enabled: bool = False


_CACHE: dict[str, Strategy] | None = None


def invalidate_cache() -> None:
    global _CACHE
    _CACHE = None


async def _load_all() -> dict[str, Strategy]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT strategy_id, name, family, phase, enabled, signal_type,
                   outcomes_table, promotion_model, promotion_thresholds, notes,
                   live_real_enabled
            FROM mi_strategies
            """
        )
    out: dict[str, Strategy] = {}
    for r in rows:
        thresholds = r["promotion_thresholds"]
        if isinstance(thresholds, str):
            thresholds = json.loads(thresholds)
        out[r["strategy_id"]] = Strategy(
            strategy_id=r["strategy_id"],
            name=r["name"],
            family=r["family"],
            phase=r["phase"],
            enabled=r["enabled"],
            signal_type=r["signal_type"],
            outcomes_table=r["outcomes_table"],
            promotion_model=r["promotion_model"],
            promotion_thresholds=thresholds or {},
            notes=r["notes"],
            live_real_enabled=r["live_real_enabled"],
        )
    return out


def assert_no_deprecated_but_enabled(strategies: dict) -> None:
    """`phase='deprecated'` AND `enabled=true` must be IMPOSSIBLE, not merely currently-false.

    ⚠ Found 2026-08-02: ALL THREE deprecated strategies were sitting enabled — 9M Day 2 (since
    2026-07-06), Continuation Flag, and Fishhook. The phase gate blocks entries so nothing traded,
    which is exactly why it went unnoticed for 26 days: the rows kept their jobs registered and
    their code paths live while looking retired.

    That half-alive state has already cost something. 9M Day 2 stayed in the shared
    `submit_trade_entry` funnel long enough for #490's submission-time gap guard to come within one
    review of applying MAGNA53's 10% floor to a strategy whose own bar is 3%.

    RAISES — deliberately loud, like the scheduler's job-partition guard. A retired strategy that
    silently stays enabled is worse than one that fails the boot: the first is discovered by a
    defect, the second by a stack trace.
    """
    bad = sorted(
        s.name for s in strategies.values()
        if (s.phase or "").lower() == "deprecated" and s.enabled
    )
    if bad:
        raise RuntimeError(
            "mi_strategies: deprecated strategies are still enabled — "
            f"{', '.join(bad)}. `deprecated` is terminal (ADR 0022 §1): set enabled=false. "
            "A half-retired row keeps its jobs registered and its code paths live."
        )


async def load_strategies(force: bool = False) -> dict[str, Strategy]:
    """Return all strategies keyed by strategy_id. Cached process-wide."""
    global _CACHE
    if _CACHE is None or force:
        _CACHE = await _load_all()
        assert_no_deprecated_but_enabled(_CACHE)
    return _CACHE


async def get_strategy(strategy_id: str) -> Strategy | None:
    """Fetch a single strategy. Returns None if not registered.

    Callers gating behavior on phase/enabled should treat None as
    fail-open (strategy not registered yet — pre-framework code path).
    """
    by_id = await load_strategies()
    return by_id.get(strategy_id)


async def should_run(strategy_id: str) -> bool:
    """Enable-flag gate for single-call paths (shadow_orb / parabolic).

    Returns True if the strategy isn't registered (fail-open) or is
    enabled. Callers handle the phase semantics themselves — this only
    answers "is the master switch on?".
    """
    s = await get_strategy(strategy_id)
    return s is None or s.enabled


async def update_strategy(
    strategy_id: str,
    *,
    phase: str | None = None,
    enabled: bool | None = None,
    live_real_enabled: bool | None = None,
    promotion_thresholds: dict | None = None,
) -> Strategy | None:
    """Mutate a registered strategy. Invalidates cache and returns the
    fresh row. Returns None if strategy_id doesn't exist.
    """
    sets: list[str] = []
    args: list[Any] = []
    if phase is not None:
        if phase not in ("shadow", "paper", "live"):
            raise ValueError(f"invalid phase: {phase}")
        args.append(phase)
        sets.append(f"phase = ${len(args)}")
    if enabled is not None:
        args.append(enabled)
        sets.append(f"enabled = ${len(args)}")
    if live_real_enabled is not None:
        args.append(live_real_enabled)
        sets.append(f"live_real_enabled = ${len(args)}")
    if promotion_thresholds is not None:
        args.append(json.dumps(promotion_thresholds))
        sets.append(f"promotion_thresholds = ${len(args)}::jsonb")
    if not sets:
        raise ValueError("update_strategy requires at least one field to mutate")
    sets.append("updated_at = NOW()")
    args.append(strategy_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE mi_strategies SET {', '.join(sets)} "
            f"WHERE strategy_id = ${len(args)} RETURNING strategy_id",
            *args,
        )
    if not row:
        return None
    invalidate_cache()
    return await get_strategy(strategy_id)
