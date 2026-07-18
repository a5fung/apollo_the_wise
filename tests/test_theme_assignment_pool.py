"""#476 (2026-07-17) — the assignment pool uses an RS-LEVEL floor, not a fixed
top-40 count. A fixed count floats the effective quality bar with how crowded
the RS top is (needed RS 98.4 on a bunched day), shutting genuinely-strong
uncovered names out of assignment to the existing themes they fit. Pins the
`_build_theme_pools` split: discovery stays top-40; assignment = RS≥floor among
the top-ceiling leaders; assignment ⊇ discovery.
"""
from __future__ import annotations

from agents.market_intelligence.theme_engine import (
    _build_theme_pools, ASSIGN_POOL_RS_FLOOR, ASSIGN_POOL_CEILING, THEME_RS_MIN,
)


def _mk(n, rs):
    return {"ticker": f"T{n:03d}", "rs_composite": rs}


def test_crowded_top_admits_strong_names_below_top40():
    # 50 names at RS 98-100 (crowded top) then strong biotech at RS 90-96 at
    # ranks 51-60 — the exact scenario that shut the elite out under top-40.
    leaders = [_mk(i, 99.0) for i in range(50)] + [_mk(50 + j, 96 - j) for j in range(10)]
    uncovered, assign = _build_theme_pools(leaders, set(), set())

    disc = {s["ticker"] for s in uncovered}
    asg = {s["ticker"] for s in assign}
    # discovery = top-40 only
    assert disc == {f"T{i:03d}" for i in range(40)}
    # the RS 90-96 names at ranks 51-60 are EXCLUDED from discovery but INCLUDED in assignment
    strong_below40 = {f"T{50 + j:03d}" for j in range(7)}  # RS 96..90
    assert strong_below40 & disc == set()
    assert strong_below40 <= asg
    # assignment ⊇ discovery
    assert disc <= asg


def test_below_floor_names_excluded_from_assignment():
    # names at RS 85-89 (below the 90 floor) must NOT enter the assignment pool
    leaders = [_mk(i, 99.0) for i in range(40)] + [_mk(100 + j, 89 - j) for j in range(5)]
    _, assign = _build_theme_pools(leaders, set(), set())
    asg = {s["ticker"] for s in assign}
    assert all(f"T{100 + j:03d}" not in asg for j in range(5))  # RS 89..85 excluded


def test_covered_and_revalidated_excluded_from_both():
    leaders = [_mk(i, 99.0) for i in range(45)]
    covered = {"T000"}
    reval = {"T001"}
    uncovered, assign = _build_theme_pools(leaders, covered, reval)
    for pool in (uncovered, assign):
        tks = {s["ticker"] for s in pool}
        assert "T000" not in tks and "T001" not in tks


def test_quiet_day_top40_below_floor_still_assignable():
    # quiet tape: the whole top-40 is RS 60-88 (below the 90 floor). The union
    # tail must keep them assignable (they're still the strongest names today).
    leaders = [_mk(i, 88 - i * 0.5) for i in range(40)]  # RS 88 down to ~68.5
    uncovered, assign = _build_theme_pools(leaders, set(), set())
    # nothing clears the RS90 floor, but the top-40 (>= THEME_RS_MIN=50) still
    # populate assignment via the union
    assert len(uncovered) == 40
    assert {s["ticker"] for s in uncovered} <= {s["ticker"] for s in assign}


def test_ceiling_bounds_the_pool():
    # 500 names all at RS 95 — the assignment pool must not exceed the ceiling
    leaders = [_mk(i, 95.0) for i in range(500)]
    _, assign = _build_theme_pools(leaders, set(), set())
    assert len(assign) == ASSIGN_POOL_CEILING  # euphoric-tape backstop holds
