"""#491 M2 — seeded assignment-pool exemption (2026-08-05, operator-approved D1).

WHY THIS EXISTS. A stock whose business has pivoted has, by construction, LOW trailing
RS — RS is a 1/3/6-month lookback. Measured in prod on 2026-08-04: every one of the ten
ex-miner names (RIOT 62 … BTDR 17) sat under the assignment pool's RS-70 floor while a
correct live AI theme ("AI GPU Compute Infrastructure & Cloud Services", Nascent) was
3 members wide on the board. The price-action lanes are the only signal with no RS lag
and they already carried the cohort's names (Lane-2 "Bitcoin miners pivoting to AI data
centers" {HUT, IREN} on 07-20; "AI Data Center Infrastructure Buildout" {BTDR, AMRC,
BLZE} on 08-04) — those names died in shadow rows the assignment pass never saw. M2 is
the connection: a SEEDED ticker is admitted to the ASSIGNMENT pool regardless of RS
floor and fetch rank, its score row fetched explicitly from mi_stock_scores.

⚠ FORK F-D — THE ONE RULED SCOPE (design doc 491_theme_migration_design_2026-08-05.md
§4.5): admission = named in an active Lane-2 narrative row or a reactivation seed —
NEVER a raw RS band. That scope is what keeps the exemption price-action-anchored and
bounded (~15/night by construction) instead of a back door around the floor. It is
pinned three ways below: the source tuple, the accessor's SQL, and the pure admission
function's RS-free signature. A future change that widens admission to an RS band must
fail here.

Every fixture is a REAL measured prod shape (2026-08-04/05 board + scores), not an
invention — including the two shapes the design doc got wrong: APLD is NOT homeless
(covered by the live AI theme), and HUT is still covered by the Fading crypto lineage.
Mirrors test_ecosystem_reactivation.py: pure decisions tested with zero mocking; the
db accessor's SQL is pinned by inspection (it was exercised for real against prod by
the #491 replay, not re-proven here).
"""
from __future__ import annotations

import inspect
from datetime import date

from agents.market_intelligence import db as dbmod
from agents.market_intelligence.db import SEEDED_ASSIGN_SOURCES
from agents.market_intelligence.theme_engine import _seeded_pool_admissions


# ── FORK F-D, pin 1: the source tuple IS the admission scope ────────────────────────────────────


def test_the_admission_scope_is_exactly_the_two_ruled_seed_sources():
    # Operator-ruled (F-D): active Lane-2 narrative rows + reactivation seeds, nothing else.
    # Adding a source here — or an RS band anywhere — re-opens the ruling. In particular these
    # must stay OUT: 'narrative_seed' (a 1-name watch row is a hook, not a narrative),
    # 'judge_inferred' / 'coverage_probe' (anti-circularity walls), 'narrative_cogap_backfill'
    # (hindsight population), 'shadow_v2' (retired lane).
    assert SEEDED_ASSIGN_SOURCES == ("narrative_cogap", "ecosystem_reactivation")


def test_the_accessor_filters_by_the_pinned_sources_and_reads_only():
    src = inspect.getsource(dbmod.get_seeded_assignment_tickers)
    # The SQL must be built FROM the pinned tuple (one place to widen = one place to catch),
    # and the window must be strictly prior-sessions (a same-day lane row can never be its
    # own admission ticket — tonight's rows are written after the assignment pass).
    assert "SEEDED_ASSIGN_SOURCES" in src
    assert "run_date < $2" in src
    # READ-ONLY: the exemption feeds a pool; it must never write anything anywhere.
    for verb in ("INSERT", "UPDATE", "DELETE"):
        assert verb not in src.upper().replace("NEVER WRITES", "")


def test_the_accessor_has_no_rs_input_at_all():
    # A raw-RS-band admission would need RS in the query. There is none, by design.
    src = inspect.getsource(dbmod.get_seeded_assignment_tickers)
    assert "rs_composite" not in src
    assert "mi_stock_scores" not in src  # scores are fetched by the CALLER, per admitted name


# ── FORK F-D, pin 2: the pure admission decision takes NO RS argument ───────────────────────────


def test_the_admission_function_signature_is_rs_free():
    # Admission is membership in seeded_triggers, full stop. Adding an rs/band/floor
    # parameter here is the exact widening F-D forbids.
    params = list(inspect.signature(_seeded_pool_admissions).parameters)
    assert params == ["seeded_triggers", "covered_tickers", "revalidated_out", "pool_tickers"]


def test_an_unseeded_name_cannot_be_admitted_no_matter_its_rs():
    # RS 69.9 (one tick under the floor) and unseeded → structurally invisible to M2.
    # There is no argument through which its RS could even be presented.
    admitted = _seeded_pool_admissions(
        seeded_triggers={},
        covered_tickers=set(),
        revalidated_out=set(),
        pool_tickers=set(),
    )
    assert admitted == []


# ── Pure decision: the real 2026-08-04/05 prod shapes ───────────────────────────────────────────

_BTDR_TRIGGER = {"source": "narrative_cogap",
                 "name": "AI Data Center Infrastructure Buildout",
                 "run_date": date(2026, 8, 4)}
_HUT_TRIGGER = {"source": "narrative_cogap",
                "name": "Bitcoin miners pivoting to AI data centers",
                "run_date": date(2026, 7, 20)}


def test_btdr_the_acceptance_case_is_admitted():
    # THE cohort case this mechanism exists for: BTDR (RS 16.9, universe rank 2015 — the
    # deepest-buried ex-miner) was named in the 08-04 Lane-2 row; its own newborn died
    # Retired the same day, so it is UNCOVERED on 08-05, with the correct live AI theme
    # on the board. M2 admits it; the assignment LLM decides the rest.
    admitted = _seeded_pool_admissions(
        seeded_triggers={"BTDR": _BTDR_TRIGGER},
        covered_tickers={"APLD", "CBRS", "CRWV"},  # the live AI theme's members
        revalidated_out=set(),
        pool_tickers=set(),
    )
    assert admitted == ["BTDR"]


def test_a_covered_seeded_name_is_not_admitted_covered_exclusivity_is_not_bypassed():
    # HUT was named in the 07-20 Lane-2 row BUT was covered by the incumbent crypto theme
    # (Fading rows keep tickers covered — deliberate, theme_engine covered_tickers).
    # Moving a member OUT of an incumbent is the custody verb (M-CORE), not M2 — the
    # design's B1 blocker stands. The fixture must NOT assume the cohort is homeless:
    # measured 08-05, APLD is covered by the live AI theme and HUT/CIFR by the Fading
    # crypto lineage; only the genuinely uncovered names are admissible.
    admitted = _seeded_pool_admissions(
        seeded_triggers={"HUT": _HUT_TRIGGER, "IREN": _HUT_TRIGGER},
        covered_tickers={"HUT"},  # crypto incumbent still holds it
        revalidated_out=set(),
        pool_tickers=set(),
    )
    assert admitted == ["IREN"]  # the uncovered half of the 07-20 row


def test_a_just_revalidated_out_name_is_not_readmitted_same_run():
    # The same-run re-assignment guard every pool obeys: a name validation-removed
    # tonight must not walk straight back in through the exemption.
    admitted = _seeded_pool_admissions(
        seeded_triggers={"WULF": _HUT_TRIGGER},
        covered_tickers=set(),
        revalidated_out={"WULF"},
        pool_tickers=set(),
    )
    assert admitted == []


def test_a_name_already_in_the_pool_is_not_duplicated():
    # A seeded name that cleared the floor on its own merit is already in the pool —
    # admitting it again would put the same ticker in front of the LLM twice.
    admitted = _seeded_pool_admissions(
        seeded_triggers={"AMRC": _BTDR_TRIGGER, "BTDR": _BTDR_TRIGGER},
        covered_tickers=set(),
        revalidated_out=set(),
        pool_tickers={"AMRC"},
    )
    assert admitted == ["BTDR"]


def test_admissions_are_deterministically_ordered():
    trig = {"ZBRA": _BTDR_TRIGGER, "AEIS": _BTDR_TRIGGER, "BLZE": _BTDR_TRIGGER}
    assert _seeded_pool_admissions(trig, set(), set(), set()) == ["AEIS", "BLZE", "ZBRA"]


# ── Wiring: assignment-only, windowed, fail-open, observable ────────────────────────────────────


def _m2_block() -> str:
    src = open("agents/market_intelligence/theme_engine.py").read()
    i = src.index("#491 M2: seeded assignment-pool exemption")
    return src[i:i + 4200]


def test_the_engine_wires_m2_between_pool_build_and_assignment():
    block = _m2_block()
    assert "_seeded_pool_admissions" in block
    assert "get_seeded_assignment_tickers" in block
    # Window: LANE2_WINDOW_TRADING_DAYS trading days, prior sessions only — the same
    # horizon the Lane-2 registry itself uses (_lane2_window_start).
    assert "_lane2_window_start(today)" in block


def test_m2_touches_the_assignment_pool_only_never_discovery():
    # Discovery stays top-40 untouched (§4.2) — an admitted name must never leak into
    # the `uncovered` discovery pool or any lane's candidate table.
    block = _m2_block()
    assert "assignment_pool.append" in block
    assert "uncovered.append" not in block
    for verb in ("INSERT INTO mi_themes", "UPDATE mi_themes", "DELETE FROM mi_themes",
                 "mi_theme_candidates_shadow"):
        assert verb not in block


def test_m2_fails_open_a_broken_read_costs_one_night_not_the_run():
    block = _m2_block()
    assert "no M2 exemption this run" in block


def test_m2_admissions_are_observable_and_the_rate_bound_is_loud_not_silent():
    # §4.4: ~15/night by construction. A fat lane night is a FINDING to surface —
    # never a silent cap, never dropped names. One audit row per run carries the
    # per-ticker trigger pointers (the operator's "why is this name here").
    block = _m2_block()
    assert "seeded_pool_admission" in block
    assert "> 15" in block and "bound" in block
    assert "cap" not in block.replace("silently cap", "")  # no capping code, only the warning


def test_scores_are_fetched_explicitly_for_admitted_names():
    # The exemption's mechanism: "its score row fetched explicitly from mi_stock_scores"
    # (§4.2) — via get_rs_for_tickers, never via the leaders fetch it exists to bypass.
    block = _m2_block()
    assert "get_rs_for_tickers" in block
    assert "get_rs_leaders" not in block
