"""#424 (ADR 0022 §1, operator-signed 2026-07-05/06): execute the standing
strategy deprecations — 9m_day2 and flag_continuation retired to a new
terminal `phase='deprecated'`; wick_fill stays a shadow "hold" (backlog
idea, never auto-flagged promotion-ready).

Three things this pins:
  1. The registry SEED sets the right phase for each of the three strategies,
     and ships an idempotent migration UPDATE so EXISTING prod rows (seeded
     under the old phases before this fix) converge too — the seed's
     `ON CONFLICT DO NOTHING` only applies on first insert.
  2. The weekly promotion checker excludes 'deprecated' strategies entirely
     (no metrics computed, no outcome-row DB query, never "✓ ready") instead
     of just falling through to the generic "already at top of ladder" path.
  3. The live entry gate (`entry_pipeline.submit_trade_entry`) blocks a
     'deprecated' strategy the same way it blocks 'shadow' — via the pure
     `_phase_gate_skip_reason` predicate — rather than falling through to
     `resolve_account_mode_for_strategy`, which raises ValueError for any
     phase other than 'paper'/'live' (a crash, not a clean skip).
"""
from __future__ import annotations

import asyncio

import pytest

from agents.market_intelligence.broker.entry_pipeline import _phase_gate_skip_reason
from agents.market_intelligence.broker.skip_reasons import (
    BLOCK_STRATEGY_DEPRECATED,
    BLOCK_STRATEGY_DISABLED,
    BLOCK_STRATEGY_IN_SHADOW,
)
from agents.market_intelligence.constants import resolve_account_mode_for_strategy
from agents.market_intelligence.db import _seed_strategies_registry
from agents.market_intelligence.strategies import promotion as promotion_mod
from agents.market_intelligence.strategies.registry import Strategy


def _strategy(strategy_id="x", phase="deprecated", enabled=True, promotion_model="unpaired_r"):
    return Strategy(
        strategy_id=strategy_id,
        name=strategy_id,
        family="orb_long",
        phase=phase,
        enabled=enabled,
        signal_type=strategy_id,
        outcomes_table="mi_live_trades",
        promotion_model=promotion_model,
        promotion_thresholds={},
    )


# ── 1. Registry seed ─────────────────────────────────────────────────────────


class _FakeConn:
    """Records executemany/execute calls; no real DB required."""

    def __init__(self):
        self.executemany_calls: list[tuple] = []
        self.execute_calls: list[tuple] = []

    async def executemany(self, query, args):
        self.executemany_calls.append((query, args))

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


def _run_seed() -> _FakeConn:
    conn = _FakeConn()
    asyncio.run(_seed_strategies_registry(conn))
    return conn


def test_seed_deprecates_9m_day2_and_flag_continuation():
    conn = _run_seed()
    _, seed_rows = conn.executemany_calls[0]
    by_id = {row[0]: row for row in seed_rows}  # row[0] = strategy_id, row[3] = phase
    assert by_id["9m_day2"][3] == "deprecated"
    assert by_id["flag_continuation"][3] == "deprecated"
    # wick_fill is the backlog "hold" — stays shadow, NOT deprecated.
    assert by_id["wick_fill"][3] == "shadow"


def test_wick_fill_review_required_blocks_auto_ready():
    """wick_fill must never auto-show '✓ ready' in the weekly checker — the
    telemetry_review evaluator always appends a blocking reason when
    review_required is True (or absent), regardless of metrics clearing."""
    conn = _run_seed()
    _, seed_rows = conn.executemany_calls[0]
    by_id = {row[0]: row for row in seed_rows}
    # row[7] = promotion_thresholds — a plain dict (#216: the jsonb codec encodes it
    # exactly once; json.loads()-ing it here would double-encode on write and is no
    # longer how the seed binds this param).
    thresholds = by_id["wick_fill"][7]
    assert isinstance(thresholds, dict)
    assert thresholds["shadow_to_paper"]["review_required"] is True


def test_seed_migration_update_converges_existing_prod_rows():
    """The seed's INSERT is ON CONFLICT DO NOTHING — an existing prod row
    (9m_day2 seeded 'paper', flag_continuation seeded 'shadow' before this
    fix) would never see the new phase. A committed, idempotent UPDATE must
    run alongside the seed so prod converges on next boot without a manual
    SQL step."""
    conn = _run_seed()
    assert conn.execute_calls, "expected an idempotent phase-convergence UPDATE"
    query, _ = conn.execute_calls[0]
    assert "UPDATE mi_strategies" in query
    assert "'deprecated'" in query
    assert "9m_day2" in query
    assert "flag_continuation" in query
    # Idempotency guard — must not unconditionally stomp updated_at every boot.
    assert "!=" in query


# ── 2. Promotion checker excludes deprecated ────────────────────────────────


@pytest.mark.asyncio
async def test_check_promotion_eligibility_excludes_deprecated(monkeypatch):
    strat = _strategy(strategy_id="9m_day2", phase="deprecated")

    async def _fake_get_strategy(sid):
        return strat

    async def _fail_get_outcomes(*a, **k):
        raise AssertionError("get_outcomes must not be queried for a deprecated strategy")

    monkeypatch.setattr(promotion_mod, "get_strategy", _fake_get_strategy)
    monkeypatch.setattr(promotion_mod, "get_outcomes", _fail_get_outcomes)

    verdict = await promotion_mod.check_promotion_eligibility("9m_day2")

    assert verdict is not None
    assert verdict.current_phase == "deprecated"
    assert verdict.next_phase is None
    assert verdict.eligible is False
    assert any("deprecated" in r for r in verdict.blocking_reasons)


@pytest.mark.asyncio
async def test_check_promotion_eligibility_paper_still_evaluates(monkeypatch):
    """Regression guard: the new deprecated short-circuit must not swallow
    normal (non-deprecated) strategies — paper/shadow still reach the real
    evaluator and DO query outcomes."""
    strat = _strategy(strategy_id="magna53", phase="paper")
    called = {"n": 0}

    async def _fake_get_strategy(sid):
        return strat

    async def _fake_get_outcomes(*a, **k):
        called["n"] += 1
        return []

    monkeypatch.setattr(promotion_mod, "get_strategy", _fake_get_strategy)
    monkeypatch.setattr(promotion_mod, "get_outcomes", _fake_get_outcomes)

    verdict = await promotion_mod.check_promotion_eligibility("magna53")

    assert called["n"] == 1
    assert verdict.next_phase == "live"
    assert verdict.eligible is False  # 0 closed trades — correctly blocked, not skipped


# ── 3. Entry gate resolves deprecated to no-submit ──────────────────────────


@pytest.mark.parametrize(
    "phase,enabled,expected",
    [
        ("deprecated", True, BLOCK_STRATEGY_DEPRECATED),
        ("shadow", True, BLOCK_STRATEGY_IN_SHADOW),
        ("paper", True, None),
        ("live", True, None),
        ("deprecated", False, BLOCK_STRATEGY_DISABLED),  # disabled checked first
        ("paper", False, BLOCK_STRATEGY_DISABLED),
    ],
)
def test_phase_gate_skip_reason(phase, enabled, expected):
    assert _phase_gate_skip_reason(_strategy(phase=phase, enabled=enabled)) == expected


def test_resolve_account_mode_raises_for_deprecated():
    """Defense in depth: even if a deprecated strategy somehow reached the
    account-mode resolver (it shouldn't — _phase_gate_skip_reason short-
    circuits first), it must fail LOUD (ValueError), never silently resolve
    to a submit-capable mode."""
    with pytest.raises(ValueError):
        resolve_account_mode_for_strategy(_strategy(phase="deprecated"))
