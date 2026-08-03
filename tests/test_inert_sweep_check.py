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
"""
import inspect

from agents.market_intelligence import health_checks as hc


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


def test_the_verdict_is_zero_varied_not_low_variance():
    """Deliberate: 'some variants agree' is normal and common. Only NOT ONE subject differing is
    always a defect. Anything softer becomes wallpaper."""
    src = inspect.getsource(hc.run_inert_sweep_check)
    assert "varied == 0" in src


def test_each_lane_is_isolated_so_one_bad_table_cannot_blind_the_rest():
    src = inspect.getsource(hc.run_inert_sweep_check)
    body = src[src.index("for table"):]
    assert "except Exception" in body and '"errors"' in src


def test_a_missing_table_or_column_is_SKIPPED_not_reported_as_inert():
    """An absent lane must never read as 'measuring nothing' — that would be a false alarm with the
    same wording as the real one."""
    src = inspect.getsource(hc.run_inert_sweep_check)
    assert '"table absent"' in src and '"expected columns absent"' in src


def test_it_is_wired_into_the_nightly_audit_and_alerts():
    """A check nobody runs is a function. /audit and /crypto both shipped this week with working
    handlers and no registration."""
    sched = open("agents/market_intelligence/scheduler.py").read()
    assert "run_inert_sweep_check" in sched
    i = sched.index("run_inert_sweep_check")
    block = sched[i:i + 2000]
    assert "inert_sweep_detected" in block, "must leave an audit row"
    assert "send_telegram_message" in block, "must reach the operator, not just a log line"


def test_the_check_does_not_judge_plausibility():
    """Scope guard. The moment it starts opining on whether numbers look sensible it needs a domain
    model, and it becomes the kind of broad checker that gets switched off."""
    src = inspect.getsource(hc.run_inert_sweep_check)
    for overreach in ("mean", "median", "stddev", "outlier", "plausib"):
        assert overreach not in src.lower()


def test_the_alert_announces_ONCE_per_lane_not_nightly():
    """The condition persists until someone recomputes the stored rows, so an un-deduped alert
    would fire every night about a defect already known and already filed. That is how a real
    signal becomes wallpaper — the same failure the 7/17 budget-alarm re-fire fix addressed, and
    the reason the new-lane detector dedupes too. The audit log is the state; no new table."""
    sched = open("agents/market_intelligence/scheduler.py").read()
    i = sched.index("run_inert_sweep_check")
    block = sched[i:i + 2600]
    assert "inert_sweep_detected" in block
    assert "SELECT DISTINCT" in block, "must read prior announcements before alerting again"


def test_the_dedupe_fails_OPEN():
    """If the dedupe read breaks, the cost must be a duplicate alert — never a missed one. A
    health guard that goes quiet on its own error is the failure it exists to prevent."""
    sched = open("agents/market_intelligence/scheduler.py").read()
    i = sched.index("inert-sweep dedupe read failed")
    assert "will re-announce" in sched[i:i + 120]
