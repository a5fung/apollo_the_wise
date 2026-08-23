"""#533 — the SEPARATION change (2026-08-22, operator-signed): behaviour + wiring pins.

Three coupled parts, ONE revert flag (`ep_score_separation` / EP_SCORE_SEPARATION_ENABLED,
default ON): (1) the gap ladder is FLAT — every qualifying gap pays 10; (2) conviction-floor
branches 1-3 are DELETED, branch 4 (gap>=10 + game_changer -> 60) SURVIVES BY DESIGN — it is
the 2026-04-14 dead-zone fix for a real EP (BE) and what fires MRNA HIGH at its 10% gap read;
(3) the HIGH bar is uniform 40 instead of the per-regime 65/70/75/80.

The revert side (flag OFF) is pinned byte-for-byte by the 69-case boundary sweep in
tests/test_ep_score_stage2_refactor.py (which now scores with SCORE_WEIGHTS_LEGACY — the
fixture was captured from the true pre-change code). This file pins the LIVE side, the
MRNA guard case, the bar switch, and the run_ep_scan wiring (test_347-pattern source pins,
same idiom as test_533_catalyst_tier_flip.py).
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import sys
from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from agents.market_intelligence import ep_detector
from agents.market_intelligence import ep_score_shadow as ess
from agents.market_intelligence.ep_detector import _score_ep
from agents.market_intelligence.ep_rubric import (
    SCORE_WEIGHTS, SCORE_WEIGHTS_LEGACY, SEPARATION_BAR,
    resolve_ep_bar, resolve_score_weights,
)

_REPO = pathlib.Path(__file__).resolve().parent.parent

_BASE = dict(rel_volume=1.8, profile={}, regime_multiplier=1.0,
             vol_percentile=50.0, adv_dollar=300_000_000)


def _score(**kw):
    return _score_ep(**{**_BASE, **kw})


# ── Part 1: the gap ladder is FLAT ────────────────────────────────────────────────────


def test_every_qualifying_gap_pays_the_same_flat_10():
    """Gap size is admission evidence, not ranking points — it ran BACKWARDS on
    real EPs (AUC 0.34; their median gap is 9.9% vs ordinary gappers' 12%+)."""
    for gap in (8.0, 9.5, 10.0, 12.0, 15.0, 20.0, 35.0):
        _, bd = _score(gap_pct=gap, catalyst_quality="routine")
        assert bd["gap"] == 10, f"gap {gap}% must pay flat 10, paid {bd['gap']}"


def test_below_the_qualifying_cut_still_pays_zero():
    """The 8% cut is unchanged — WHAT qualifies did not move, what it PAYS did."""
    _, bd = _score(gap_pct=7.9, catalyst_quality="routine")
    assert bd["gap"] == 0


def test_a_20pct_gapper_no_longer_outscores_a_10pct_gapper_on_gap_alone():
    big = _score(gap_pct=20.5, catalyst_quality="strong")[0]
    small = _score(gap_pct=10.5, catalyst_quality="strong")[0]
    assert big == small, "the ladder (and the floor back door) must both be gone"


# ── Part 2: floor branches 1-3 deleted, branch 4 kept ─────────────────────────────────


def test_branch_4_is_the_only_surviving_floor_rule_exactly():
    """⚠ Branch 4 MUST SURVIVE: built 2026-04-14 (ed3e514e) as the dead-zone fix
    FOR a real EP (BE); deleting it gains 0.008 AUC and re-kills the reference EP."""
    assert SCORE_WEIGHTS["conviction_floor"]["rules"] == [
        {"min_gap": 10, "catalyst": "game_changer", "floor": 60},
    ]


def test_MRNA_guard_case_still_clears_at_its_10pct_read():
    """THE reference real EP: MRNA @ 10.04% gap, game_changer under the live
    lattice, liquid. Floor 60 x1.2 Bull = 72 — HIGH at the uniform bar 40 (and
    it would clear even the old Bull 65). This input shape must NEVER stop
    alerting under the live table."""
    score, bd = _score(gap_pct=10.04, catalyst_quality="game_changer",
                       regime_multiplier=1.2)
    assert "conviction_floor" in bd, "branch 4 must bind on the MRNA shape"
    assert score == 72.0
    assert score >= SEPARATION_BAR
    assert score >= 65  # even the old Bull bar — the guard case is not bar-dependent


def test_MRNA_guard_case_clears_outside_bull_too():
    """No multiplier (non-Bull): floor 60 >= bar 40 — the class alerts in every regime."""
    score, bd = _score(gap_pct=10.04, catalyst_quality="game_changer")
    assert "conviction_floor" in bd and score == 60.0 and score >= SEPARATION_BAR


def test_deleted_branches_no_longer_lift_ordinary_big_gappers():
    """The back door: 20%+strong -> 80 / 15%+strong -> 70 / 15%+gc -> 80 kept
    paying for gap size after the ladder flattened. All three must be dead."""
    _, bd_20s = _score(gap_pct=20.5, catalyst_quality="strong")
    assert "conviction_floor" not in bd_20s, "20%+strong->80 must be deleted"
    _, bd_15s = _score(gap_pct=15.5, catalyst_quality="strong")
    assert "conviction_floor" not in bd_15s, "15%+strong->70 must be deleted"
    # 15%+gc now falls through to branch 4 (floor 60), never the old 80:
    score_15gc, bd_15gc = _score(gap_pct=15.5, catalyst_quality="game_changer")
    assert bd_15gc.get("conviction_floor", 0) + sum(
        v for k, v in bd_15gc.items() if k != "conviction_floor") == 60
    assert score_15gc == 60.0, "a 15% game_changer floors at 60 (branch 4), not 80"


# ── Part 3: the uniform bar ───────────────────────────────────────────────────────────


def test_separation_bar_is_uniform_40_across_all_regimes():
    for regime_bar in (65, 70, 75, 80):
        assert resolve_ep_bar(True, regime_bar) == 40


def test_bar_40_was_the_volume_neutral_choice():
    """40 is the ONLY setting that holds today's alert volume (1.78/day modeled
    vs 1.81; -1 alert/month) while all 18 floor-alive real EPs stay reachable —
    and it is ONE number to change if the operator wants fewer alerts."""
    assert SEPARATION_BAR == 40


# ── The revert flag restores ALL THREE parts together ─────────────────────────────────


def test_revert_restores_the_old_weight_table_identically():
    assert resolve_score_weights(False) is SCORE_WEIGHTS_LEGACY
    assert resolve_score_weights(True) is SCORE_WEIGHTS
    assert SCORE_WEIGHTS_LEGACY["gap"]["tiers"] == [(20, 25), (15, 20), (10, 15), (8, 10)]
    assert SCORE_WEIGHTS_LEGACY["conviction_floor"]["rules"] == [
        {"min_gap": 15, "catalyst": "game_changer", "floor": 80},
        {"min_gap": 20, "catalyst": "strong", "floor": 80},
        {"min_gap": 15, "catalyst": "strong", "floor": 70},
        {"min_gap": 10, "catalyst": "game_changer", "floor": 60},
    ]


def test_revert_restores_old_scoring_behaviour_end_to_end():
    """Flag OFF -> the old ladder pays gap size and the old floors act. (The full
    69-case byte-identical sweep is test_ep_score_stage2_refactor.py; this is the
    smoke pin that the two sides really diverge where the change says they do.)"""
    legacy = SCORE_WEIGHTS_LEGACY
    _, bd = _score(gap_pct=20.5, catalyst_quality="routine", weights=legacy)
    assert bd["gap"] == 25
    score_20s, bd_20s = _score(gap_pct=20.5, catalyst_quality="strong",
                               regime_multiplier=1.2, weights=legacy)
    assert "conviction_floor" in bd_20s and score_20s == 96.0  # floor 80 x1.2 — the old back door
    # and the same input under the live table: flat 10, no floor
    score_live, bd_live = _score(gap_pct=20.5, catalyst_quality="strong",
                                 regime_multiplier=1.2)
    assert "conviction_floor" not in bd_live and score_live < score_20s


def test_revert_restores_the_per_regime_bar():
    assert resolve_ep_bar(False, 65) == 65
    assert resolve_ep_bar(False, 75) == 75


def test_components_the_change_never_ruled_on_are_shared_not_forked():
    """Liquidity / catalyst / float / vol_conviction / theme_bonus must be the SAME
    objects on both sides — a future tweak to them can never silently split the
    acting and revert sides."""
    for comp in ("liquidity", "catalyst", "float", "vol_conviction", "theme_bonus"):
        assert SCORE_WEIGHTS_LEGACY[comp] is SCORE_WEIGHTS[comp]


# ── run_ep_scan wiring pins (test_347 pattern — a refactor cannot drop the flip) ──────


def _scan_src() -> str:
    return inspect.getsource(ep_detector.run_ep_scan)


def test_all_three_parts_hang_off_the_one_toggle():
    src = _scan_src()
    assert '"ep_score_separation", "EP_SCORE_SEPARATION_ENABLED", default=True)' in src, (
        "the one instant-revert flag, default ON — the whole safety story")
    assert "resolve_score_weights(_sep_live)" in src
    assert "resolve_ep_bar(_sep_live, _regime_bar)" in src, (
        "weights AND bar must derive from the SAME flag read — they revert together")


def test_acting_and_counterfactual_sides_both_run_through_the_real_scorer():
    src = _scan_src()
    assert "weights=_act_weights," in src
    assert "weights=_cf_weights," in src, (
        "the operator's keep-tracking-existing condition: the OTHER side is computed "
        "by the SAME _score_ep, never a reimplementation")


def test_record_carries_constant_column_semantics_and_live_side():
    src = _scan_src()
    assert '"live_side": "separation" if _sep_live else "legacy",' in src, (
        "the acting side is stamped explicitly — never inferred from dates")
    assert '"legacy_bar": _regime_bar,' in src
    assert '"sep_bar": SEPARATION_BAR,' in src
    assert "record_ep_score_shadow(_score_shadow_inputs" in src


def test_boost_shadow_compare_stays_on_the_acting_side():
    src = _scan_src()
    assert "weights=_act_weights,  # #533: boost-off compare stays on the acting side" in src


def test_high_decision_outranks_the_cutline_and_the_cutline_value_is_untouched():
    """The priced bar-40 policy counts 40-49 scores as HIGHs (1.78/day); a
    cutline-first skip would silently ship the bar-50 row (-77% alerts). So the
    HIGH decision runs first, while the cutline keeps its value (50) and its
    MODERATE role — with the legacy bars (65-80) `< bar and < 50` is
    byte-identical to the old `< 50`, so revert restores the old skip exactly."""
    src = _scan_src()
    assert "if ep_score < 50 and ep_score < ep_threshold:" in src, (
        "a bar-clearing score must never die on the (unruled) 50 cutline")
    # legacy equivalence, stated as arithmetic: for every legacy bar the new
    # condition degenerates to the old one.
    for bar in (65, 70, 75, 80):
        for score in (0, 39.9, 40, 45, 49.9, 50, 60, bar, 96):
            assert (score < 50 and score < bar) == (score < 50)


def test_bar_40_semantics_a_45_score_is_HIGH_not_skipped():
    """The tier expressions recorded per side implement the same semantics: HIGH
    is checked before the cutline. 45 @ bar 40 -> HIGH; 45 @ legacy bar 65 ->
    below the cutline -> no tier (skipped); 60 @ bar 65 -> MODERATE."""
    def tier(score, bar):
        return "HIGH" if score >= bar else "MODERATE" if score >= 50 else None
    assert tier(45.0, 40) == "HIGH"
    assert tier(39.9, 40) is None
    assert tier(45.0, 65) is None
    assert tier(60.0, 65) == "MODERATE"


def test_score_shadow_table_is_declared_with_both_sides_and_live_side():
    db_src = (_REPO / "agents" / "market_intelligence" / "db.py").read_text()
    assert "CREATE TABLE IF NOT EXISTS mi_ep_score_shadow" in db_src
    for col in ("sep_score_first", "legacy_score_first", "sep_tier_last",
                "legacy_tier_last", "sep_bar", "legacy_bar", "live_side"):
        assert col in db_src


# ── the recorder: fail-open, shadow-table-only (THE LINE) ─────────────────────────────

_ROW = {"ticker": "MRNA", "sep_score": 72.0, "sep_tier": "HIGH",
        "legacy_score": 56.4, "legacy_tier": "MODERATE",
        "sep_bar": 40, "legacy_bar": 65, "live_side": "separation",
        "gap_pct": 10.04, "catalyst_quality": "game_changer"}


@pytest.mark.asyncio
async def test_recorder_writes_only_the_shadow_table(monkeypatch):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    executed = []

    async def _execute(sql, *args):
        executed.append((sql, args))
        return "INSERT 0 1"
    conn.execute = _execute
    monkeypatch.setattr(ess, "get_pool", AsyncMock(return_value=pool))
    n = await ess.record_ep_score_shadow(
        [_ROW], date(2026, 8, 22), datetime(2026, 8, 22, 7, 5))
    assert n == 1 and len(executed) == 1
    sql, args = executed[0]
    assert "INSERT INTO mi_ep_score_shadow" in sql
    assert "ON CONFLICT (scan_date, ticker)" in sql
    assert "mi_ep_alerts" not in sql and "mi_live_trades" not in sql
    assert "separation" in args  # live_side rides along explicitly


@pytest.mark.asyncio
async def test_recorder_is_fail_open_on_pool_failure(monkeypatch):
    monkeypatch.setattr(ess, "get_pool", AsyncMock(side_effect=RuntimeError("db down")))
    n = await ess.record_ep_score_shadow(
        [_ROW], date(2026, 8, 22), datetime(2026, 8, 22, 7, 5))
    assert n == 0  # never raises — telemetry must never jeopardize the scan


@pytest.mark.asyncio
async def test_recorder_empty_inputs_is_a_noop():
    assert await ess.record_ep_score_shadow(
        [], date(2026, 8, 22), datetime(2026, 8, 22, 7, 5)) == 0
