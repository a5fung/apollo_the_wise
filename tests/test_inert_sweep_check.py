"""A study that varies a parameter must produce variation (#521, 2026-08-03).

WHY THIS EXISTS. `mi_orb_extension_shadow` swept six entry-cutoff times for **91 days** and every
one returned a byte-identical result for every trade. One word caused it — the simulator computed
its fill threshold from the STOP instead of the LIMIT — and nobody could see it until the review's
N>=20 threshold tripped on 2026-08-03. The answer it would have produced ("10:00 is already
optimal") was manufactured by the bug.

Operator: *"disappointing to have bad data for months, need to prevent this going forward."*

THE RULE, as narrow as it can be stated: if a sweep has >=2 variants and enough subjects, and not
one subject scores differently across them, the swept parameter is not reaching the code. That is
decidable from the data alone and needs no view on whether the numbers are *right*.

Measured against the real tables when it was built:
  * `mi_orb_extension_shadow` — 31 subjects, 31 multi-variant, **0 varied** → fires. Correct.
  * `mi_consolidation_entry_shadow` — 231 subjects, 23 multi-variant, **23 varied** → silent.
    Correct, and the reason this is not a guard that always fires.

⚠ It deliberately does NOT judge plausibility, ranges or units — those need a domain model and
would cry wolf. This fires only on a signature that is always a defect.

2026-09-13 (#653 cleanup): the three tests over an actually-observable BEHAVIOR (the
zero-vs-low-variance verdict, per-lane isolation, skip-reason classification) now call the REAL
`run_inert_sweep_check()` against a mocked asyncpg pool and assert on its RETURNED dict, instead
of grepping a source-text copy. The remaining four are TAGGED, not converted — each is either a
wiring check (the closed-list legitimate case in docs/testing/test_discipline.md) or control flow
inlined in `_post_nightly_audit_job`, a ~300-line orchestrator that awaits ~13 OTHER health checks
in sequence. No existing test in this repo drives that function end-to-end (every other test of it
also pins its source — see test_grading_health_543.py, test_detector_liveness_543.py,
test_capture_retention_2026_08_15.py) because each of those other checks binds its own `get_pool`
at ITS OWN module's import time: silencing them for real would mean refactoring scheduler.py to
add a testable seam (out of scope for a test-brittleness sweep) or leaving ~12 unrelated checks
free to attempt REAL network connections inside a unit test — a worse trade than a reviewed pin.
"""
import asyncio
import inspect
from unittest.mock import AsyncMock

import agents.market_intelligence.db as db_mod
from agents.market_intelligence import health_checks as hc
from tests.conftest import make_mock_pool


def test_the_registry_names_the_lane_that_actually_broke():
    tables = {lane[0] for lane in hc._SWEEP_LANES}
    assert "mi_orb_extension_shadow" in tables


def test_every_registry_row_is_well_formed():
    """A malformed row would silently skip a lane — the failure mode this file exists to stop."""
    for table, sweep_col, outcome_col, min_subjects in hc._SWEEP_LANES:
        assert table.startswith("mi_") and sweep_col and outcome_col
        assert isinstance(min_subjects, int) and min_subjects > 0


def test_it_covers_every_sweep_lane_known_at_build_time():
    """Measured 2026-08-03: exactly four shadow tables carry a swept-parameter column. A new sweep
    lane not added here is NOT checked — that cost is accepted and documented in the source."""
    tables = {lane[0] for lane in hc._SWEEP_LANES}
    assert tables == {
        "mi_orb_extension_shadow",
        "mi_giveback_shadow",
        "mi_htf_management_shadow",
        "mi_consolidation_entry_shadow",
    }


def test_a_minimum_subject_count_gates_every_lane():
    """Without it, a lane fires 'inert' on its first two rows — which is just 'not enough data yet'
    wearing an alarm."""
    assert all(lane[3] >= 10 for lane in hc._SWEEP_LANES)


# ── behavioral fixture: run the REAL run_inert_sweep_check against a mocked asyncpg pool ──────
# `run_inert_sweep_check` does `from agents.market_intelligence.db import get_pool` INSIDE the
# function body (a fresh lookup every call), so patching `hc.get_pool` (the name bound in
# health_checks.py's own namespace at ITS import time) would not reach it — the patch has to
# land on `db_mod.get_pool`, the actual name the local import re-reads at call time.

def _wire(monkeypatch, cols_by_table, fetchrow_by_table):
    pool, conn = make_mock_pool()

    async def _fetch(sql, table, *a, **k):
        if table in cols_by_table:
            v = cols_by_table[table]
            if isinstance(v, Exception):
                raise v
            return [{"column_name": c} for c in v]
        return []  # table absent from information_schema

    async def _fetchrow(sql, *a, **k):
        # every per-lane SELECT embeds its table name literally in the query text
        for table, row in fetchrow_by_table.items():
            if table in sql:
                return row
        return None

    conn.fetch = AsyncMock(side_effect=_fetch)
    conn.fetchrow = AsyncMock(side_effect=_fetchrow)
    monkeypatch.setattr(db_mod, "get_pool", AsyncMock(return_value=pool))


def _run():
    return asyncio.run(hc.run_inert_sweep_check())


def test_the_verdict_is_zero_varied_not_low_variance(monkeypatch):
    """MUTATION TARGET: 'varied == 0' loosened to a threshold (e.g. varied <= 1), so a sweep
    where only ONE of many subjects varied would ALSO be flagged inert. Deliberate: 'some
    variants agree' is normal and common — only NOT ONE subject differing is always a defect."""
    cols = {"mi_orb_extension_shadow": ["trade_id", "cutoff_minute", "total_pnl"]}

    _wire(monkeypatch, cols,
          {"mi_orb_extension_shadow": {"subjects": 31, "multi_variant_subjects": 31, "varied": 0}})
    assert any(r["table"] == "mi_orb_extension_shadow" for r in _run()["inert"]), \
        "zero varied across 31 multi-variant subjects must fire"

    _wire(monkeypatch, cols,
          {"mi_orb_extension_shadow": {"subjects": 31, "multi_variant_subjects": 31, "varied": 1}})
    assert not any(r["table"] == "mi_orb_extension_shadow" for r in _run()["inert"]), \
        "ONE subject varying is low variance, not the zero-variance defect signature"


def test_each_lane_is_isolated_so_one_bad_table_cannot_blind_the_rest(monkeypatch):
    """MUTATION TARGET: the per-lane try/except removed, so one bad table's exception
    propagates out of the loop and the OTHER three lanes are never even reached."""
    _wire(monkeypatch, {"mi_orb_extension_shadow": RuntimeError("boom: query failed")}, {})
    result = _run()
    assert any(e["table"] == "mi_orb_extension_shadow" for e in result["errors"]), \
        "the broken lane must be recorded as an error, not silently dropped"
    skipped = {s["table"] for s in result["skipped"]}
    assert skipped == {"mi_giveback_shadow", "mi_htf_management_shadow",
                        "mi_consolidation_entry_shadow"}, \
        "a bad table's exception must not stop the OTHER lanes from being reached"


def test_a_missing_table_or_column_is_SKIPPED_not_reported_as_inert(monkeypatch):
    """MUTATION TARGET: an absent lane must never read as 'measuring nothing' — that would be a
    false alarm with the same wording as a real defect. Two distinct absence shapes: the table
    itself missing (schema probe returns no columns) vs the table existing but missing the
    swept/outcome column this lane expects."""
    cols = {
        "mi_orb_extension_shadow": [],                       # table itself absent
        "mi_giveback_shadow": ["trade_id", "arm"],            # exists, missing realized_r
    }
    _wire(monkeypatch, cols, {})
    result = _run()
    reasons = {s["table"]: s["why"] for s in result["skipped"]}
    assert reasons["mi_orb_extension_shadow"] == "table absent"
    assert reasons["mi_giveback_shadow"] == "expected columns absent"
    assert "mi_htf_management_shadow" in reasons and "mi_consolidation_entry_shadow" in reasons
    assert result["inert"] == [], "an absent lane must never be reported as inert"


def test_it_is_wired_into_the_nightly_audit_and_alerts():
    """A check nobody runs is a function. /audit and /crypto both shipped this week with working
    handlers and no registration."""
    # source-pin-ok: wiring check (the closed-list legitimate case) that the guard is actually
    # called from the nightly job and reaches both the audit log and Telegram — see the file
    # docstring for why _post_nightly_audit_job cannot be driven end-to-end in this suite.
    sched = open("agents/market_intelligence/scheduler.py").read()
    assert "run_inert_sweep_check" in sched
    i = sched.index("run_inert_sweep_check")
    block = sched[i:i + 2000]
    assert "inert_sweep_detected" in block, "must leave an audit row"
    assert "send_telegram_message" in block, "must reach the operator, not just a log line"


def test_the_check_does_not_judge_plausibility():
    """Scope guard. The moment it starts opining on whether numbers look sensible it needs a
    domain model, and it becomes the kind of broad checker that gets switched off."""
    # source-pin-ok: banned-keyword scope guard, the closed-list "ban on X" legitimate case —
    # the SQL already returns only counts (never raw outcome values) so there is no behavioral
    # input that could exercise a magnitude judgment that structurally cannot exist yet; this
    # only stops someone from WIDENING the query to add one.
    src = inspect.getsource(hc.run_inert_sweep_check)
    for overreach in ("mean", "median", "stddev", "outlier", "plausib"):
        assert overreach not in src.lower()


def test_the_alert_announces_ONCE_per_lane_not_nightly():
    """The condition persists until someone recomputes the stored rows, so an un-deduped alert
    would fire every night about a defect already known and already filed. That is how a real
    signal becomes wallpaper — the same failure the 7/17 budget-alarm re-fire fix addressed, and
    the reason the new-lane detector dedupes too. The audit log is the state; no new table."""
    # source-pin-ok: the dedupe read is inline in _post_nightly_audit_job (see file docstring —
    # ~300-line orchestrator, ~13 other health checks, none driven end-to-end by any test here).
    sched = open("agents/market_intelligence/scheduler.py").read()
    i = sched.index("run_inert_sweep_check")
    block = sched[i:i + 2600]
    assert "inert_sweep_detected" in block
    assert "SELECT DISTINCT" in block, "must read prior announcements before alerting again"


def test_the_dedupe_fails_OPEN():
    """If the dedupe read breaks, the cost must be a duplicate alert — never a missed one. A
    health guard that goes quiet on its own error is the failure it exists to prevent."""
    # source-pin-ok: same inline-control-flow reasoning as the dedupe-once test above — no seam
    # to call this in isolation without refactoring scheduler.py's orchestration function.
    sched = open("agents/market_intelligence/scheduler.py").read()
    i = sched.index("inert-sweep dedupe read failed")
    assert "will re-announce" in sched[i:i + 120]
