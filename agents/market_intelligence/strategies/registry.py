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

⚠ THE CACHE IS PER PROCESS (#312 review, 2026-11-07). `update_strategy` runs in
the market agent (his Demote press, the typed `/strategy <id> demote|disable`)
and invalidates THAT process's cache; apollo-execution — the container that
submits orders — never sees the invalidation, so `get_strategy()` there served
the OLD phase / enabled flag / sizing knob to NEW entries until its next restart.
Every money-path read therefore uses `get_strategy_fresh()` — one primary-key
SELECT of the committed row, never the cache: the entry funnel
(`broker/entry_pipeline.py`, before its first step), the two paper lanes
(`lowcap_paper_entry`, `breakout_v1_entry`) and the label/dedup resolver
(`constants.resolve_strategy_mode_nonfatal`). `get_strategy()` / `should_run()`
stay the cached read for the scan-side enable flags.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from typing import Any

from agents.market_intelligence.db import get_pool, _jsonb_param

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
    # #65 per-strategy sizing knob, applied in entry_pipeline step 5b AFTER the builder's
    # 20%-cap-maximal spec: final_shares = floor(spec.shares × this × drawdown_tier_multiplier).
    # #628 (2026-09-07): this field did NOT EXIST from #65 (2026-05-10) until today — the
    # pipeline read it via `getattr(strategy, "position_size_multiplier", None) or 1.0`, so
    # the default fired on every entry and `mi_strategies.position_size_multiplier` governed
    # nothing while the column, the drift check and the docs all said it acted. The pipeline
    # now reads the attribute DIRECTLY (a missing field is an AttributeError, never a silent
    # 1.0) and tests/test_628_position_size_multiplier_wired.py pins the field's existence.
    # 1.0 = full sizing = the value every production row carries (read-only prod check
    # 2026-09-07: 8 rows, all 1.0), so wiring it changed no position size.
    position_size_multiplier: float = 1.0


_CACHE: dict[str, Strategy] | None = None


def _coerce_position_size_multiplier(raw: Any, strategy_id: str) -> float:
    """`mi_strategies.position_size_multiplier` (NUMERIC NOT NULL DEFAULT 1.0) → float.

    asyncpg hands NUMERIC back as `Decimal`; entry_pipeline multiplies it into `math.floor`.
    A value that cannot size a trade — NULL (the column forbids it, but a hand-migrated row
    or a test double might carry one), NaN / ±Inf (NUMERIC admits both, and
    `math.floor(shares * nan)` raises mid-pipeline), or non-numeric garbage — resolves to
    **1.0**: today's full sizing, the same answer the pre-#628 silent default gave. Any other
    resolution would CHANGE a position size on a configuration gap (THE LINE — sizing is the
    operator's alone), which would be a worse defect than the dead knob this replaces. The
    gap is logged at WARNING so it is visible rather than silent.

    Deliberately NOT clamped: 0.0 is a legitimate "size nothing" (it lands in the pipeline's
    size_too_small skip) and >1.0 is RED-3's clamp-to-baseline in
    `entry_pipeline._apply_composite_multiplier`. Coercion is wiring, not policy.
    """
    if raw is None:
        logger.warning(f"mi_strategies.{strategy_id}.position_size_multiplier is NULL — "
                       f"sizing at 1.0 (full) until the row is fixed")
        return 1.0
    try:
        val = float(raw)
    except (TypeError, ValueError):
        logger.warning(f"mi_strategies.{strategy_id}.position_size_multiplier={raw!r} is not "
                       f"numeric — sizing at 1.0 (full) until the row is fixed")
        return 1.0
    if not math.isfinite(val):
        logger.warning(f"mi_strategies.{strategy_id}.position_size_multiplier={raw!r} is not "
                       f"finite — sizing at 1.0 (full) until the row is fixed")
        return 1.0
    return val


def invalidate_cache() -> None:
    global _CACHE
    _CACHE = None


# The ONE column list a Strategy is built from — the SELECT in `_load_all` and the RETURNING of
# `update_strategy` both use it, so the row a writer hands back is the row a reader would load.
_STRATEGY_COLUMNS = ("strategy_id, name, family, phase, enabled, signal_type, outcomes_table, "
                     "promotion_model, promotion_thresholds, notes, live_real_enabled, "
                     "position_size_multiplier")


def _row_to_strategy(r) -> Strategy:
    thresholds = r["promotion_thresholds"]
    if isinstance(thresholds, str):
        thresholds = json.loads(thresholds)
    return Strategy(
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
        position_size_multiplier=_coerce_position_size_multiplier(
            r["position_size_multiplier"], r["strategy_id"]),
    )


async def _load_all() -> dict[str, Strategy]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"SELECT {_STRATEGY_COLUMNS} FROM mi_strategies")
    return {r["strategy_id"]: _row_to_strategy(r) for r in rows}


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
    """Fetch a single strategy FROM THE PROCESS CACHE. Returns None if not registered.

    Callers gating behavior on phase/enabled should treat None as
    fail-open (strategy not registered yet — pre-framework code path).

    ⚠ Not for a money-path decision: the cache is invalidated only by THIS process's
    `update_strategy`, and the phase writers run in the market agent, not in
    apollo-execution. An entry, a dedup book or a sizing read uses `get_strategy_fresh`.
    """
    by_id = await load_strategies()
    return by_id.get(strategy_id)


# The one-row read `get_strategy_fresh` makes — the same column list the cache is built from,
# so a fresh row and a cached row are the same shape.
_SELECT_ONE_SQL = f"SELECT {_STRATEGY_COLUMNS} FROM mi_strategies WHERE strategy_id = $1"


async def get_strategy_fresh(strategy_id: str) -> Strategy | None:
    """The strategy row AS COMMITTED NOW — one primary-key SELECT, never the process cache
    (#312 review, 2026-11-07: his Demote press commits in the market agent; apollo-execution's
    cache never learns of it, so a cached read at 09:31 would route a NEW entry on the OLD phase).

    Returns None for an unregistered id (the same fail-open the cached read gives a pre-seed
    strategy). RAISES on a DB error — deliberately no fallback to the cache or to a process
    default: the caller decides what a missing answer means (the entry funnel skips
    `infra:strategy_unreadable` and pages; the paper lanes refuse to order; the label resolver
    says "mode unknown"). Reads the cache for nothing and writes it with nothing.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SELECT_ONE_SQL, strategy_id)
    return _row_to_strategy(row) if row else None


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
    expect_phase: str | None = None,
    conn=None,
) -> Strategy | None:
    """Mutate a registered strategy — THE one phase writer. Invalidates the process cache and
    returns the fresh row (from the UPDATE's own RETURNING, so no second read is needed).
    Returns None if `strategy_id` doesn't exist — or, with `expect_phase`, if the row's phase
    is no longer the one the caller saw.

    `expect_phase` (#312, 2026-11-07) — a compare-and-set: `... AND phase = <expect_phase>` on
    the WHERE, so a press on the ladder's breach page moves the strategy only from the rung
    the page SHOWED. A typed `/strategy <id> promote|demote` passes none and behaves as before.

    `conn` — a caller that ALREADY HOLDS a connection inside its own transaction (the ladder
    press locks its page row, reads the phase, writes the phase and records the decision as
    ONE unit) hands it over instead of asking the pool for a second one (the 2026-09-17
    nested-acquire deadlock class). The cache is still invalidated; the fresh row comes from
    RETURNING on that same connection, never from a second acquire.
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
        # #216: get_pool's jsonb codec already encodes this param — pre-dumping
        # here double-encodes it into a JSON string. _jsonb_param matches the
        # db.py write-path fix (do NOT json.dumps before binding).
        args.append(_jsonb_param(promotion_thresholds))
        sets.append(f"promotion_thresholds = ${len(args)}::jsonb")
    if not sets:
        raise ValueError("update_strategy requires at least one field to mutate")
    sets.append("updated_at = NOW()")
    args.append(strategy_id)
    where = f"WHERE strategy_id = ${len(args)}"
    if expect_phase is not None:
        args.append(expect_phase)
        where += f" AND phase = ${len(args)}"
    sql = f"UPDATE mi_strategies SET {', '.join(sets)} {where} RETURNING {_STRATEGY_COLUMNS}"
    if conn is not None:
        row = await conn.fetchrow(sql, *args)
    else:
        pool = await get_pool()
        async with pool.acquire() as c:
            row = await c.fetchrow(sql, *args)
    if not row:
        return None
    invalidate_cache()
    return _row_to_strategy(row)
