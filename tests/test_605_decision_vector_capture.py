"""#605 (2026-08-29) — the decision-vector capture contract: a new gate or scoring
input CANNOT land without its value being logged, or this file goes red.

The operator's actual complaint was not any one missing column but the recurrence:
*"every time you say we're missing this or that, we patch it and next time we're
still missing stuff, I don't want to see this again."* Every arm here is decidable
from source (no DB, no network) and each failure message says what to do. The
registry being enforced is `agents/market_intelligence/ep_decision_vector.py` —
read its docstring for the contract; this file is the teeth.

Mutation-tested at ship time (2026-08-29), both directions:
  - a fake `_score_ep` parameter (unregistered scoring input) → arm 1 red;
  - a fake `continue` gate in run_ep_scan (silent kill, nothing logged) → arm 5 red.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

from agents.market_intelligence import ep_decision_vector as dv
from agents.market_intelligence import ep_detector
from agents.market_intelligence import ep_rubric
from agents.market_intelligence import db as mi_db
from agents.market_intelligence.broker import order_manager as om

_REPO = Path(__file__).resolve().parent.parent
_EP_SRC = (_REPO / "agents" / "market_intelligence" / "ep_detector.py").read_text()
_DB_SRC = (_REPO / "agents" / "market_intelligence" / "db.py").read_text()
_RUN_SRC = inspect.getsource(ep_detector.run_ep_scan)


def _cols(mapping: dict) -> set[str]:
    out: set[str] = set()
    for v in mapping.values():
        if isinstance(v, tuple):
            out.update(v)
    return out


# ── arm 1: every scoring input is registered (EXACT equality — stale entries flag too) ──

def test_score_ep_parameters_all_registered():
    params = set(inspect.signature(ep_detector._score_ep).parameters)
    registered = set(dv.SCORE_EP_INPUT_COLUMNS)
    assert params == registered, (
        f"_score_ep's inputs and the decision-vector registry disagree.\n"
        f"  unregistered params (ADD to SCORE_EP_INPUT_COLUMNS, wired to a logged "
        f"mi_ep_scan_log column — see ep_decision_vector.py): {sorted(params - registered)}\n"
        f"  stale registry entries (param gone — remove): {sorted(registered - params)}"
    )


def test_score_weight_components_all_registered():
    for table_name, table in (("SCORE_WEIGHTS", ep_rubric.SCORE_WEIGHTS),
                              ("SCORE_WEIGHTS_LEGACY", ep_rubric.SCORE_WEIGHTS_LEGACY)):
        components = set(table)
        registered = set(dv.SCORE_COMPONENT_COLUMNS)
        assert components == registered, (
            f"{table_name} components and SCORE_COMPONENT_COLUMNS disagree — a new score "
            f"component needs its input column logged AND registered.\n"
            f"  unregistered: {sorted(components - registered)}\n"
            f"  stale: {sorted(registered - components)}"
        )


def test_shortlist_inputs_all_registered():
    params = {p for p in inspect.signature(ep_rubric.shortlist_prescore).parameters}
    assert params == set(dv.SHORTLIST_INPUT_COLUMNS), (
        "shortlist_prescore inputs vs SHORTLIST_INPUT_COLUMNS: "
        f"{sorted(params ^ set(dv.SHORTLIST_INPUT_COLUMNS))}")
    assert set(ep_rubric.SHORTLIST_WEIGHTS) == set(dv.SHORTLIST_COMPONENT_COLUMNS), (
        "SHORTLIST_WEIGHTS components vs SHORTLIST_COMPONENT_COLUMNS: "
        f"{sorted(set(ep_rubric.SHORTLIST_WEIGHTS) ^ set(dv.SHORTLIST_COMPONENT_COLUMNS))}")


# ── arm 2: every registered column is wired end-to-end (row builder → INSERT → CREATE) ──

def _create_block_columns() -> set[str]:
    m = re.search(r"CREATE TABLE IF NOT EXISTS mi_ep_scan_log\s*\((.*?)\n\s{0,16}\);",
                  _DB_SRC, re.S)
    assert m, "mi_ep_scan_log CREATE block not found in db.py"
    cols = set()
    for line in m.group(1).splitlines():
        line = line.split("--")[0].strip().rstrip(",")
        if not line or line.upper().startswith(("UNIQUE", "PRIMARY", "CONSTRAINT")):
            continue
        cols.add(line.split()[0])
    return cols


def _insert_columns() -> set[str]:
    src = inspect.getsource(mi_db.log_ep_scan_candidates)
    m = re.search(r"INSERT INTO mi_ep_scan_log\s*\((.*?)\)\s*VALUES", src, re.S)
    assert m, "log_ep_scan_candidates INSERT column list not found"
    return {c.strip() for c in m.group(1).replace("\n", " ").split(",")}


def test_registered_columns_reach_the_database():
    create_cols = _create_block_columns()
    insert_cols = _insert_columns()
    for col in sorted(dv.all_registered_columns()):
        assert f'"{col}"' in _EP_SRC, (
            f"registered column {col!r} is never built into a scan_log row in "
            f"ep_detector.py (_scan_row / _pre_candidate_row) — the value is not captured.")
        assert col in insert_cols, (
            f"registered column {col!r} missing from log_ep_scan_candidates' INSERT — "
            f"built in the row dict but silently dropped at the write.")
        assert col in create_cols, (
            f"registered column {col!r} missing from the mi_ep_scan_log CREATE block — "
            f"add it there AND as an ALTER TABLE ... ADD COLUMN IF NOT EXISTS "
            f"(CREATE IF NOT EXISTS is a no-op on the existing prod table; "
            f"test_schema_alter_create_parity pins the mirror).")


def test_insert_placeholders_match_column_count():
    src = inspect.getsource(mi_db.log_ep_scan_candidates)
    m = re.search(r"INSERT INTO mi_ep_scan_log\s*\((.*?)\)\s*VALUES\s*\((.*?)\)\s*\"\"\"",
                  src, re.S)
    assert m, "INSERT statement shape not found"
    n_cols = len(m.group(1).split(","))
    n_params = len(re.findall(r"\$\d+", m.group(2)))
    assert n_cols == n_params, f"INSERT has {n_cols} columns but {n_params} placeholders"


# ── arm 3: every funnel stage literal is registered, and vice versa ─────────────────────

def _stage_literals() -> set[str]:
    found = set(re.findall(r'(?<![a-z_])stage="([a-z_0-9]+)"', _EP_SRC))
    found |= set(re.findall(r'"reject_stage":\s*"([a-z_0-9]+)"', _EP_SRC))
    found |= set(re.findall(r'\["reject_stage"\]\s*=\s*"([a-z_0-9]+)"', _EP_SRC))
    return found


def test_gate_stages_all_registered():
    literals = _stage_literals()
    registered = set(dv.GATE_VECTOR)
    assert literals == registered, (
        f"funnel stage literals in ep_detector.py and GATE_VECTOR disagree.\n"
        f"  unregistered stages (ADD to GATE_VECTOR with the columns that gate "
        f"compares): {sorted(literals - registered)}\n"
        f"  stale registry stages: {sorted(registered - literals)}"
    )


# ── arm 4: capture floors can never re-censor (the June/July 9-10% hole class) ─────────

def test_row_capture_floor_at_or_below_every_admission_floor():
    assert ep_detector.EP_CAPTURE_GAP_FLOOR <= ep_detector.MIN_GAP_PCT, (
        "EP_CAPTURE_GAP_FLOOR must sit at/below MIN_GAP_PCT — otherwise a floor cut "
        "has no captured history to be evaluated against (the June/July 2026 hole).")
    assert ep_detector.EP_CAPTURE_GAP_FLOOR <= ep_detector.EP_PASS1_SUPERSET_GAP_PCT, (
        "EP_CAPTURE_GAP_FLOOR must sit at/below the hybrid Pass-1 superset floor.")


def test_bar_capture_floor_at_or_below_admission_floor():
    assert om._PATH_CAPTURE_MIN_GAP <= ep_detector.MIN_GAP_PCT, (
        "order_manager._PATH_CAPTURE_MIN_GAP must sit at/below MIN_GAP_PCT — a floor "
        "cut below it would re-open the minute-bar coverage hole the 2026-08-29 "
        "1.1M-row backfill closed.")
    assert ep_detector.EP_CAPTURE_GAP_FLOOR <= om._PATH_CAPTURE_MIN_GAP, (
        "scan_log rows must cover at least the bar-capture band (rows are the index "
        "into the bars).")


# ── arm 5: tripwires — a NEW gate moves a count and must touch the registry ────────────

def test_no_unregistered_continue_in_run_ep_scan():
    n = len(re.findall(r"^\s+continue\b", _RUN_SRC, re.M))
    assert n == dv.EXPECTED_SCAN_CONTINUE_COUNT, (
        f"run_ep_scan now has {n} `continue` statements "
        f"(registry expects {dv.EXPECTED_SCAN_CONTINUE_COUNT}).\n"
        f"If you ADDED A GATE: log the candidate's decision vector at the kill point "
        f"(_log_filtered with a stage, or a _pre_candidate_row flush), register the "
        f"stage + its input columns in ep_decision_vector.GATE_VECTOR, and update "
        f"EXPECTED_SCAN_CONTINUE_COUNT in the same commit.\n"
        f"If this is a pure refactor: update the constant — that conscious touch is "
        f"the point (see ep_decision_vector.py §4)."
    )


def test_log_filtered_call_count_matches_registry():
    n = len(re.findall(r"_log_filtered\(", _RUN_SRC)) - len(
        re.findall(r"def _log_filtered\(", _RUN_SRC))
    assert n == dv.EXPECTED_LOG_FILTERED_CALLS, (
        f"run_ep_scan has {n} _log_filtered call sites "
        f"(registry expects {dv.EXPECTED_LOG_FILTERED_CALLS}) — a new logged gate "
        f"needs its stage + input columns registered in ep_decision_vector.GATE_VECTOR "
        f"and this count updated in the same commit."
    )


def test_every_log_filtered_call_names_a_stage():
    calls = re.findall(r"_log_filtered\((?!\s*c:\s)(.*?)\)\n", _RUN_SRC, re.S)
    for call in calls:
        assert 'stage="' in call, (
            f"_log_filtered call without an explicit stage= — every kill row must "
            f"stamp its funnel stage: {call[:120]!r}"
        )


# ── arm 6: the minute-bar population is candidate-driven, not alert-driven (#605.3) ────

def test_bar_capture_population_reads_the_scan_log():
    src = inspect.getsource(om.persist_alert_day_paths)
    assert "mi_ep_scan_log" in src, (
        "persist_alert_day_paths' population no longer reads mi_ep_scan_log — bars "
        "would silently shrink back to the alerted subset (the 14%-coverage failure).")
    assert "MAX(gap_pct)" in src, (
        "the scan_log arm must use the day-MAX gap so an intraday fade can't drop a "
        "name that WAS a candidate at some tick.")


# ── arm 7: the pre-candidate rows exist and carry their gate's compared values ─────────

def test_universe_floor_skip_carries_compared_values_as_columns():
    out = ep_detector._universe_floor_skip("CHEAP", 3.0, 100_000, 4.50)
    assert out is not None
    assert out["prev_day_volume"] == 100_000
    assert out["current_price"] == 4.50
    assert out["reject_stage"] == "universe_floor"


def test_snap_candidate_carries_prev_day_volume():
    snap = {"day": {"v": 500}, "min": {"av": 800}, "prevDay": {"v": 123}}
    out = ep_detector._snap_candidate("ABC", snap, 10.0, 11.0, 10.0, {}, None)
    assert out["prev_day_volume"] == 123


def test_below_floor_band_is_captured_in_the_scan_loop():
    # Source pin: the loop's sub-floor branch must build a capture row before its
    # `continue` (the floor-censorship fix itself). Behavioral coverage of the full
    # loop needs a live snapshot fixture; the branch is small enough to pin textually.
    assert "EP_CAPTURE_GAP_FLOOR" in _RUN_SRC
    assert re.search(
        r"if gap_pct >= EP_CAPTURE_GAP_FLOOR:.*?_below_floor_rows\.append", _RUN_SRC, re.S
    ), "the [EP_CAPTURE_GAP_FLOOR, admission floor) band is no longer recorded"
