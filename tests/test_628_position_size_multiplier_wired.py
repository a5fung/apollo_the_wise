"""#628 — the #65 per-strategy sizing knob was DEAD for four months; this pins its wiring.

`entry_pipeline.submit_trade_entry` step 5b read the knob as
`getattr(strategy, "position_size_multiplier", None) or 1.0`, and `registry.Strategy` never
carried the field — so the default fired on every entry and `mi_strategies.position_size_multiplier`
governed nothing while the column, the drift check and README.md all said it acted.

The fix is WIRING ONLY (operator-directed 2026-09-07; bug fix, not a criteria change): the
dataclass carries the field, the loader reads the column, the pipeline reads the attribute
directly. Every production row is 1.0 (read-only prod check 2026-09-07), so today's sizing is
byte-identical — `test_pipeline_at_one_is_byte_identical` is the test that says so.

Pipeline-level tests drive the REAL `submit_trade_entry` over the #461 SQL-shape-aware FakeDB
harness (imported rather than re-rolled — it already models every query step 6 issues). Step 5b
mutates the builder's `order_spec` dict IN PLACE and step 6 inserts that same dict, so each test
holds a reference to the spec and reads the final `shares` / `position_size` / `risk_dollars` /
`risk_dollars_actual` off it after the pipeline returns.

Mutation proofs (each test run against the named break, red, then restored): see the #628 commit.
"""
from __future__ import annotations

import dataclasses
import math
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.broker import entry_pipeline as ep
from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.strategies import registry
from agents.market_intelligence.strategies.registry import Strategy
from tests.conftest import make_mock_pool
from tests.test_461_cap_toctou_race import FakeDB, _TODAY, _wire


# ─── 1. The dataclass field — the thing whose absence made this silent ───────


def test_strategy_dataclass_carries_position_size_multiplier():
    """MUTATION TARGET: deleting `position_size_multiplier` from `registry.Strategy` (or
    renaming it) — the exact state that made the knob a silent 1.0 for four months. With a
    direct attribute read in the pipeline that deletion is an AttributeError on the money
    path at runtime; this test makes it a red build instead. The default must be exactly
    1.0 — full sizing — because that is what every production row carries."""
    names = {f.name for f in dataclasses.fields(Strategy)}
    assert "position_size_multiplier" in names, (
        "registry.Strategy lost position_size_multiplier — the #65 knob would silently "
        "revert to the pre-#628 dead state (or crash the entry path)"
    )
    default = next(f for f in dataclasses.fields(Strategy)
                   if f.name == "position_size_multiplier").default
    assert default == 1.0
    s = _strategy()  # constructed without the kwarg → the default
    assert s.position_size_multiplier == 1.0


# ─── 2. The loader — the column has to reach the dataclass ───────────────────


@pytest.mark.asyncio
async def test_load_all_reads_the_column_into_the_dataclass(monkeypatch):
    """MUTATION TARGET: `_load_all` dropping `position_size_multiplier` from its SELECT, or
    hard-coding 1.0 in the constructor call — either re-severs the table from the pipeline.
    asyncpg returns NUMERIC as Decimal; the dataclass must carry a plain float."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[_row("magna53", Decimal("0.5"))])
    monkeypatch.setattr(registry, "get_pool", AsyncMock(return_value=pool))

    out = await registry._load_all()

    sql = conn.fetch.await_args.args[0]
    assert "position_size_multiplier" in sql, "the loader's SELECT no longer names the column"
    assert out["magna53"].position_size_multiplier == 0.5
    assert isinstance(out["magna53"].position_size_multiplier, float)


@pytest.mark.parametrize("raw", [None, Decimal("NaN"), float("inf"), float("-inf"), "abc"])
@pytest.mark.asyncio
async def test_load_all_unsizeable_cell_resolves_to_one(monkeypatch, raw):
    """MUTATION TARGET: the coercer raising on NULL/NaN/garbage (a registry crash aborts
    EVERY entry, not just this strategy's) or resolving to anything but 1.0 (0.0 would
    silently size every entry to nothing; the pre-#628 default was 1.0 and a config gap
    must not change a position size — THE LINE)."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[_row("magna53", raw)])
    monkeypatch.setattr(registry, "get_pool", AsyncMock(return_value=pool))

    out = await registry._load_all()

    val = out["magna53"].position_size_multiplier
    assert val == 1.0 and math.isfinite(val)


def test_coercer_does_not_clamp_zero_or_above_one():
    """MUTATION TARGET: a "helpful" clamp in the coercer. 0.0 is a legitimate size-nothing
    (the pipeline's size_too_small skip owns it) and >1.0 is RED-3's clamp-to-baseline in
    `_apply_composite_multiplier` — bounding here would be policy, not wiring."""
    assert registry._coerce_position_size_multiplier(Decimal("0"), "x") == 0.0
    assert registry._coerce_position_size_multiplier(Decimal("2.0"), "x") == 2.0
    assert registry._coerce_position_size_multiplier(Decimal("0.25"), "x") == 0.25


# ─── 3. The pipeline — the value has to ACT ───────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_halves_shares_at_half(monkeypatch):
    """MUTATION TARGET: the pre-#628 line (`getattr(..., None) or 1.0` — passes on a real
    Strategy only because the field now exists, so this test pairs with the loud-not-silent
    test below) and the cruder break `strategy_multiplier = 1.0` unconditionally. 0.5 on 10
    shares → 5, and position_size / risk_dollars / risk_dollars_actual (#571 lockstep) all
    follow the FINAL share count."""
    db = FakeDB()
    _, audit = _wire(monkeypatch, db)
    _register(monkeypatch, _strategy(position_size_multiplier=0.5))
    spec, builder = _spec(shares=10)

    result = await ep.submit_trade_entry(**_call(builder))

    assert result["action"] == ep.ACTION_AUTO_ENTERED, result
    assert spec["shares"] == 5
    assert spec["position_size"] == round(5 * spec["entry_price"], 2)
    assert spec["risk_dollars"] == round(5 * spec["risk_per_share"], 2)
    assert spec["risk_dollars_actual"] == spec["risk_dollars"]
    msgs = [c.args[1] for c in audit.await_args_list if c.args[0] == "per_strategy_sizing_applied"]
    assert len(msgs) == 1 and "strategy 0.50x" in msgs[0] and "shares=5" in msgs[0]


@pytest.mark.asyncio
async def test_pipeline_at_one_is_byte_identical(monkeypatch):
    """MUTATION TARGET: any wiring that makes 1.0 act differently from the dead path —
    a coercer that does not return EXACTLY 1.0 for a 1.0 cell, or the step-5b gate running
    at identity. This is the "no live size changes today" proof: every production row is
    1.0, so shares stay at the builder's count and NO sizing event fires."""
    db = FakeDB()
    _, audit = _wire(monkeypatch, db)
    _register(monkeypatch, _strategy(position_size_multiplier=1.0))
    spec, builder = _spec(shares=10)

    result = await ep.submit_trade_entry(**_call(builder))

    assert result["action"] == ep.ACTION_AUTO_ENTERED, result
    assert spec["shares"] == 10
    assert spec["risk_dollars_actual"] == 8.0  # the builder's own number, untouched
    fired = {c.args[0] for c in audit.await_args_list}
    assert "per_strategy_sizing_applied" not in fired
    assert "sizing_multiplier_clamped" not in fired


@pytest.mark.asyncio
async def test_pipeline_composes_with_drawdown_tier(monkeypatch):
    """MUTATION TARGET: composition dropping a leg (0.5 alone → 5 shares) or adding instead
    of multiplying (0.5 + 0.5 = 1.0 → 10). The constants.py:375 worked example: strategy
    0.5× × REDUCE 0.5× = 0.25× → floor(10 × 0.25) = 2."""
    db = FakeDB()
    _, audit = _wire(monkeypatch, db)
    monkeypatch.setattr(lt, "_check_safeguards", AsyncMock(return_value=(True, "ok", 0.5)))
    _register(monkeypatch, _strategy(position_size_multiplier=0.5))
    spec, builder = _spec(shares=10)

    result = await ep.submit_trade_entry(**_call(builder))

    assert result["action"] == ep.ACTION_AUTO_ENTERED, result
    assert spec["shares"] == 2
    msgs = [c.args[1] for c in audit.await_args_list if c.args[0] == "per_strategy_sizing_applied"]
    assert len(msgs) == 1 and "composite=0.25x" in msgs[0]
    assert "strategy 0.50x × drawdown 0.50x" in msgs[0]


@pytest.mark.asyncio
async def test_pipeline_unregistered_strategy_sizes_at_one(monkeypatch):
    """MUTATION TARGET: the `strategy is None` branch resolving to anything but 1.0. A
    strategy absent from `mi_strategies` (legacy / pre-seed path) must size exactly as the
    dead path did — full — never on a different default."""
    db = FakeDB()
    _, audit = _wire(monkeypatch, db)
    _register(monkeypatch, None)
    spec, builder = _spec(shares=10)

    result = await ep.submit_trade_entry(**_call(builder))

    assert result["action"] == ep.ACTION_AUTO_ENTERED, result
    assert spec["shares"] == 10
    assert "per_strategy_sizing_applied" not in {c.args[0] for c in audit.await_args_list}


@pytest.mark.asyncio
async def test_pipeline_missing_attribute_is_loud_not_silent(monkeypatch):
    """MUTATION TARGET: reintroducing `getattr(strategy, "position_size_multiplier", <default>)`
    — the exact shape that hid this for four months. A strategy object WITHOUT the field must
    raise (the caller's orb_pipeline_crash path takes it — loud), never size at a default."""
    from types import SimpleNamespace
    db = FakeDB()
    _wire(monkeypatch, db)
    _register(monkeypatch, SimpleNamespace(
        enabled=True, phase="live", live_real_enabled=True, strategy_id="magna53"))
    _, builder = _spec(shares=10)

    with pytest.raises(AttributeError, match="position_size_multiplier"):
        await ep.submit_trade_entry(**_call(builder))


# ─── helpers ──────────────────────────────────────────────────────────────────


def _strategy(**overrides) -> Strategy:
    """A REAL registry.Strategy (not a SimpleNamespace) so the pipeline reads the actual field."""
    base = dict(
        strategy_id="magna53", name="MAGNA53 EP", family="ep", phase="live", enabled=True,
        signal_type="magna53", outcomes_table="mi_live_trades", promotion_model="paired_r",
        promotion_thresholds={}, live_real_enabled=True,
    )
    base.update(overrides)
    return Strategy(**base)


def _row(strategy_id: str, multiplier) -> dict:
    """One `mi_strategies` row as `_load_all` sees it (asyncpg Record-shaped)."""
    return {
        "strategy_id": strategy_id, "name": "MAGNA53 EP", "family": "ep", "phase": "live",
        "enabled": True, "signal_type": "magna53", "outcomes_table": "mi_live_trades",
        "promotion_model": "paired_r", "promotion_thresholds": {}, "notes": None,
        "live_real_enabled": True, "position_size_multiplier": multiplier,
    }


def _register(monkeypatch, strategy) -> None:
    """Replace the #461 harness's SimpleNamespace strategy with ours (or None = unregistered)."""
    monkeypatch.setattr(registry, "get_strategy", AsyncMock(return_value=strategy))


def _spec(shares: int):
    """A builder returning a spec dict the TEST holds a reference to — step 5b mutates it in
    place and step 6 inserts the same dict, so the final numbers are read straight off it."""
    spec = {
        "orb_high": 10.5, "orb_low": 9.8, "entry_price": 10.55, "stop_loss_price": 9.75,
        "shares": shares, "position_size": round(shares * 10.55, 2),
        "risk_dollars": 8.0, "risk_per_share": 0.8, "risk_dollars_actual": 8.0,
    }

    async def builder(alert_ctx, orb_bar, regime, account_mode):
        return spec, None

    return spec, builder


def _call(builder) -> dict:
    return dict(
        alert_context={"ticker": "AAA", "ep_score": 71, "catalyst_quality": "strong",
                       "gap_pct": 10.0},
        spec_builder=builder, regime_record=None, strategy_label="ORB",
        signal_type="magna53", today=_TODAY, atr_14=1.0, fade_midpoint_ratio=None,
    )
