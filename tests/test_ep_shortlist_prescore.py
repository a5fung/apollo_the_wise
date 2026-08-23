"""SHORTLIST PRE-SCORE (2026-08-22, operator-directed): behaviour + wiring pins.

The graded shortlist (top SHORTLIST_SIZE per tick) ranks by the three-term
pre-score (ep_rubric.SHORTLIST_WEIGHTS — liquidity 15x3 / flat gap 10x1 /
theme 10x1, composite 0..65), NOT by gap size — gap size runs BACKWARDS on real
EPs (AUC 0.34) and was deleted from the score the same day. ONE revert flag
(`ep_shortlist_prescore` / EP_SHORTLIST_PRESCORE_ENABLED, default ON): OFF must
restore gap-descending ordering EXACTLY.

Pins here:
  1. the weight table's literal values + the deliberately-excluded terms;
  2. the pre-score arithmetic incl. the composite_with_scaling-shaped
     missing-ADV rescale (P1: a data gap never sinks a candidate);
  3. the TIE-BREAK policy (Stage 0 measured a 9-way tie at the rank-20 cut:
     composite desc -> continuous ADV$ desc -> ticker asc, never gap);
  4. the REVERT: gap ordering is untouched by the ranking computation, and the
     only re-sort in run_ep_scan is guarded by the flag (source pins, the
     test_347 idiom used by test_533_separation_flip.py);
  5. the recorder: raw-inputs-only schema (#583 stale-derived-value class),
     fail-open, shadow-table-only (THE LINE).
"""
from __future__ import annotations

import inspect
import pathlib
import sys
from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from agents.market_intelligence import ep_detector
from agents.market_intelligence import ep_shortlist_shadow as esls
from agents.market_intelligence.ep_rubric import (
    SCORE_WEIGHTS, SHORTLIST_LIQUIDITY_TIERS, SHORTLIST_MAX_COMPOSITE,
    SHORTLIST_SIZE, SHORTLIST_WEIGHTS, shortlist_prescore, shortlist_sort_key)
from agents.market_intelligence.ep_shortlist_shadow import (
    build_shortlist_shadow_rows, compute_shortlist_ranking)

_REPO = pathlib.Path(__file__).resolve().parent.parent


# ── Part 1: the table — literal values, nothing smuggled in ───────────────────────────


def test_weight_table_is_exactly_the_signed_three_terms():
    assert SHORTLIST_WEIGHTS == {
        "liquidity":   (15, 3),
        "gap":         (10, 1),
        "theme_bonus": (10, 1),
    }
    assert SHORTLIST_MAX_COMPOSITE == 65
    assert SHORTLIST_SIZE == 20


def test_measured_noise_terms_stay_out_of_the_table():
    """extension / prior_3m / adv_trend / cooldown_proximity are excluded BY
    DESIGN: the prior-momentum penalty was deleted 2026-08-22 for firing on
    real EPs and junk at identical rates (31% vs 32%); the others are
    unmeasured. A term enters only with a measured direction."""
    for term in ("extension", "prior_3m", "adv_trend", "cooldown_proximity",
                 "float", "market_cap", "pm_rvol", "catalyst"):
        assert term not in SHORTLIST_WEIGHTS


def test_liquidity_ladder_mirrors_the_live_scores_adv_tiers_today():
    """Same values as SCORE_WEIGHTS['liquidity']['adv_tiers'] (AUC 0.72) as of
    2026-08-22 — but a SEPARATE constant, so either can be tuned without
    silently moving the other. This pins today's mirror; a signed sweep of
    either side updates its own pin."""
    assert SHORTLIST_LIQUIDITY_TIERS == [
        (500_000_000, 15),
        (250_000_000, 12),
        (100_000_000, 10),
        (50_000_000, 7),
    ]
    assert SHORTLIST_LIQUIDITY_TIERS == SCORE_WEIGHTS["liquidity"]["adv_tiers"]
    assert SHORTLIST_LIQUIDITY_TIERS is not SCORE_WEIGHTS["liquidity"]["adv_tiers"]


# ── Part 2: the pre-score arithmetic ──────────────────────────────────────────────────


def _pre(adv_dollar, in_theme=False, gap=10.0):
    return shortlist_prescore(
        adv_dollar=adv_dollar, gap_pct=gap, in_active_theme=in_theme)["composite"]


def test_stage0_reference_composites():
    """The Stage-0 worked examples (shortlist_survival_stage0_2026-08-22.md
    Result 2): SNDK 65 / MU 55 / QBTS 46 / ALGM 31."""
    assert _pre(13_100_000_000, in_theme=True) == 65    # SNDK: 45 + 10 + 10
    assert _pre(19_200_000_000) == 55                   # MU:   45 + 10
    assert _pre(278_000_000) == 46                      # QBTS: 36 + 10
    assert _pre(56_000_000) == 31                       # ALGM: 21 + 10
    assert _pre(40_000_000) == 10                       # below the $50M tier


def test_gap_is_flat_presence_not_magnitude():
    """Any qualifying gap earns the same credit — gap SIZE must buy nothing."""
    assert _pre(600_000_000, gap=9.1) == _pre(600_000_000, gap=35.0)


def test_unknown_adv_rescales_instead_of_sinking():
    """composite_with_scaling's shape: liquidity axis missing -> the composite
    rescales from the available axes. gap-only = 10 * 65/20 = 32.5; in-theme
    unknown-ADV reaches the full 65 (and then LOSES ties to verified-liquidity
    names — see the tie-break test)."""
    assert _pre(None) == 32.5
    assert _pre(None, in_theme=True) == 65
    # theme is never "missing" — not-in-theme is a real 0 reading, so an
    # out-of-theme name must NOT rescale to gap-only full marks:
    assert _pre(None, in_theme=False) != 65


def test_everything_missing_is_zero_not_an_error():
    r = shortlist_prescore(adv_dollar=None, gap_pct=None, in_active_theme=False)
    assert r["composite"] == 0.0


# ── Part 3: the tie-break (Stage 0's 9-way tie made a policy REQUIRED) ────────────────


def test_tiebreak_is_continuous_advdollar_then_ticker_never_gap():
    # equal composite: bigger ADV$ wins the slot
    assert shortlist_sort_key("AAA", 55.0, 1_000_000_000) < \
           shortlist_sort_key("BBB", 55.0, 600_000_000)
    # equal composite, unknown ADV loses to verified ADV
    assert shortlist_sort_key("AAA", 65.0, 900_000_000) < \
           shortlist_sort_key("ZZZ", 65.0, None)
    # equal composite + equal ADV$: ticker asc — a total order, deterministic
    assert shortlist_sort_key("AAA", 46.0, 278_000_000) < \
           shortlist_sort_key("BBB", 46.0, 278_000_000)


def test_nine_way_tie_resolves_deterministically():
    """The Stage-0 flood-board scenario: 9 names tied on composite at the
    rank-20 cut. The order must be a reproducible total order (here: ADV$
    desc then ticker asc), never an input-order lottery."""
    cands = [
        {"ticker": t, "gap_pct": 12.0, "prev_close": 10.0,
         "adv": 12_000_000, "adv_source": "rs_universe"}
        for t in ("TIE9", "TIE1", "TIE5", "TIE3", "TIE8", "TIE2", "TIE7",
                  "TIE6", "TIE4")
    ]  # all ADV$ $120M -> composite 40, identical
    _, ranks_a = compute_shortlist_ranking(cands, set())
    _, ranks_b = compute_shortlist_ranking(list(reversed(cands)), set())
    assert ranks_a == ranks_b, "rank must not depend on input order"
    ordered = sorted(ranks_a, key=ranks_a.get)
    assert ordered == sorted(ordered), "equal composite+ADV$ falls to ticker asc"


# ── Part 4: compute_shortlist_ranking semantics ───────────────────────────────────────


_BOARD = [
    # the killed-set shape: thin max-gap names outrank liquid real-EP profiles by gap
    {"ticker": "THIN", "gap_pct": 45.0, "prev_close": 6.0,
     "adv": 1_000_000, "adv_source": "rs_universe"},        # ADV$ $6M -> 10
    {"ticker": "SNDK", "gap_pct": 10.3, "prev_close": 40.0,
     "adv": 330_000_000, "adv_source": "rs_universe"},      # $13.2B -> 55 (+10 theme = 65)
    {"ticker": "PEND", "gap_pct": 20.0, "prev_close": 8.0,
     "adv": 5_555_555, "adv_source": "pending"},            # placeholder adv -> rescale 32.5
]


def test_pending_adv_is_treated_as_missing_not_scored():
    """`adv_source='pending'` means the candidate dict holds the prevDay.v
    PLACEHOLDER — one day's volume is not liquidity evidence and must never
    earn liquidity points (it rescales instead)."""
    entries, ranks = compute_shortlist_ranking(_BOARD, {"SNDK"})
    by_t = {e["ticker"]: e for e in entries}
    assert by_t["PEND"]["adv_dollar"] is None
    assert by_t["PEND"]["composite"] == 32.5
    assert by_t["SNDK"]["composite"] == 65
    assert by_t["THIN"]["composite"] == 10
    assert ranks == {"SNDK": 1, "PEND": 2, "THIN": 3}


def test_ranking_does_not_mutate_the_candidates_list():
    """Load-bearing for the revert: with the flag OFF run_ep_scan computes the
    counterfactual ranking but never re-sorts, so the gap order must survive
    the computation untouched."""
    board = [dict(c) for c in _BOARD]
    order_before = [c["ticker"] for c in board]
    compute_shortlist_ranking(board, {"SNDK"})
    assert [c["ticker"] for c in board] == order_before


def test_shadow_rows_carry_raw_inputs_both_ranks_and_the_acting_key():
    entries, ranks = compute_shortlist_ranking(_BOARD, {"SNDK"})
    rank_by_gap = {"THIN": 1, "PEND": 2, "SNDK": 3}
    rows = build_shortlist_shadow_rows(
        entries, ranks, rank_by_gap, acting_key="prescore",
        minutes_since_open=5, shortlist_size=2)
    by_t = {r["ticker"]: r for r in rows}
    assert by_t["SNDK"]["rank_by_prescore"] == 1
    assert by_t["SNDK"]["rank_by_gap"] == 3
    assert by_t["SNDK"]["shortlisted_by_prescore"] is True
    assert by_t["THIN"]["shortlisted_by_prescore"] is False   # rank 3 > cap 2
    assert by_t["THIN"]["shortlisted_by_gap"] is True
    assert all(r["acting_key"] == "prescore" for r in rows)
    assert all(r["board_n"] == 3 for r in rows)
    # raw inputs present; computed points ABSENT (#583 stale-derived-value class)
    for r in rows:
        for k in ("gap_pct", "prev_close", "adv", "adv_source", "in_active_theme"):
            assert k in r
        assert "composite" not in r and "points" not in r


def test_boundary_flag_is_exact_at_the_cap():
    entries, ranks = compute_shortlist_ranking(
        [{"ticker": f"T{i:02d}", "gap_pct": 10.0, "prev_close": 10.0,
          "adv": (60 - i) * 10_000_000, "adv_source": "rs_universe"}
         for i in range(25)], set())
    rows = build_shortlist_shadow_rows(
        entries, ranks, {e["ticker"]: i + 1 for i, e in enumerate(entries)},
        acting_key="prescore", minutes_since_open=None)
    in_flags = [r for r in rows if r["shortlisted_by_prescore"]]
    assert len(in_flags) == SHORTLIST_SIZE
    assert all(r["rank_by_prescore"] <= SHORTLIST_SIZE for r in in_flags)


# ── Part 5: run_ep_scan wiring pins (test_347 idiom — a refactor cannot drop the flip) ─


def _scan_src() -> str:
    return inspect.getsource(ep_detector.run_ep_scan)


def test_the_one_toggle_default_on_guards_the_only_resort():
    src = _scan_src()
    assert ('"ep_shortlist_prescore", "EP_SHORTLIST_PRESCORE_ENABLED", '
            "default=True)") in src, "one instant-revert flag, default ON"
    assert 'candidates.sort(key=lambda c: c["gap_pct"], reverse=True)' in src, (
        "the gap sort must stay untouched — flag OFF restores it exactly")
    assert ("if _prescore_live:\n                candidates[:] = _pre_order") in src, (
        "the prescore re-order must be the flag-guarded one and only mutation")
    assert src.count("candidates[:] = ") == 1, "exactly one acting re-order"


def test_the_cap_literals_are_the_named_constants():
    src = _scan_src()
    assert "candidates[:SHORTLIST_SIZE]" in src
    assert "candidates[SHORTLIST_SIZE:]" in src
    assert "candidates[:ADV_BACKFILL_LIMIT]" in src
    assert "candidates[:20]" not in src and "candidates[20:]" not in src
    assert "candidates[:50]" not in src
    assert ep_detector.ADV_BACKFILL_LIMIT == 50


def test_beyond_cap_reason_keeps_the_classifier_substring_on_both_sides():
    """missed_outcomes / ep_selectivity_breakdowns / ep_latency_audit key on
    'outside top-20' — both the prescore and the revert-side reason must keep
    it, and the revert-side string is byte-identical to the pre-change one."""
    src = _scan_src()
    assert 'f"outside top-{SHORTLIST_SIZE} shortlist "' in src
    assert 'f"outside top-{SHORTLIST_SIZE} gap cap (gap {c[\'gap_pct\']:.1f}%)"' in src
    assert SHORTLIST_SIZE == 20  # keeps 'top-20' rendering for the classifiers


def test_shadow_dispatch_is_wired_fire_and_forget():
    src = _scan_src()
    assert "record_ep_shortlist_shadow(" in src
    assert '"prescore" if _prescore_live else "gap"' in src, (
        "the acting key is stamped explicitly — never inferred from dates")


def test_fail_direction_is_gap_ordering_loudly():
    src = _scan_src()
    assert "gap ordering acts this tick" in src


# ── Part 6: the recorder — raw inputs only, fail-open, shadow-table-only ──────────────


_ROWS = [{
    "ticker": "SNDK", "gap_pct": 10.3, "prev_close": 40.0,
    "adv": 330_000_000.0, "adv_source": "rs_universe", "in_active_theme": True,
    "rank_by_prescore": 1, "rank_by_gap": 3,
    "shortlisted_by_prescore": True, "shortlisted_by_gap": True,
    "acting_key": "prescore", "board_n": 3, "minutes_since_open": 5,
}]


@pytest.mark.asyncio
async def test_recorder_writes_only_the_shadow_table(monkeypatch):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    executed = []

    async def _executemany(sql, argrows):
        executed.append((sql, argrows))
    conn.executemany = _executemany
    monkeypatch.setattr(esls, "get_pool", AsyncMock(return_value=pool))
    n = await esls.record_ep_shortlist_shadow(
        _ROWS, date(2026, 8, 22), datetime(2026, 8, 22, 9, 35))
    assert n == 1 and len(executed) == 1
    sql, argrows = executed[0]
    assert "INSERT INTO mi_ep_shortlist_shadow" in sql
    assert "mi_ep_alerts" not in sql and "mi_live_trades" not in sql
    assert "prescore" in argrows[0]  # acting_key rides along explicitly


@pytest.mark.asyncio
async def test_recorder_is_fail_open_on_pool_failure(monkeypatch):
    monkeypatch.setattr(esls, "get_pool", AsyncMock(side_effect=RuntimeError("db down")))
    n = await esls.record_ep_shortlist_shadow(
        _ROWS, date(2026, 8, 22), datetime(2026, 8, 22, 9, 35))
    assert n == 0  # never raises — telemetry must never jeopardize the scan


@pytest.mark.asyncio
async def test_recorder_empty_inputs_is_a_noop():
    assert await esls.record_ep_shortlist_shadow(
        [], date(2026, 8, 22), datetime(2026, 8, 22, 9, 35)) == 0


def test_shadow_table_ddl_stores_raw_inputs_never_points():
    """#583 stale-derived-value class: the table must hold raw inputs + the
    decision record (ranks/flags/acting_key), NEVER computed points — points
    go stale the moment a weight is swept."""
    db_src = (_REPO / "agents" / "market_intelligence" / "db.py").read_text()
    assert "CREATE TABLE IF NOT EXISTS mi_ep_shortlist_shadow" in db_src
    ddl = db_src.split("CREATE TABLE IF NOT EXISTS mi_ep_shortlist_shadow", 1)[1]
    ddl = ddl.split(");", 1)[0]
    for col in ("gap_pct", "prev_close", "adv", "adv_source", "in_active_theme",
                "rank_by_prescore", "rank_by_gap", "shortlisted_by_prescore",
                "shortlisted_by_gap", "acting_key", "board_n"):
        assert col in ddl, f"missing column {col}"
    assert "composite" not in ddl and "points" not in ddl


def test_liveness_registry_watches_the_new_writer():
    from agents.market_intelligence.health_checks import _DETECTOR_LIVENESS_TABLES
    assert any(t[0] == "mi_ep_shortlist_shadow" for t in _DETECTOR_LIVENESS_TABLES)
