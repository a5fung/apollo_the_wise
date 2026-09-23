"""#448 — the rubric must record its axes when it PASSES a name, not only when it kills one.

Only the downgrade path wrote an audit row, so every axis-vs-outcome measurement was
restricted to composite < 22 — the bottom of the range. That made "does axis N point the
way we assume" unanswerable across the full range. This pins the other half.

⚠ Telemetry only. These assertions also pin that the row is written WITHOUT touching the
verdict — a logging change must never move a grade.
"""
import json
import re

SRC = "agents/market_intelligence/ep_detector.py"


def _src() -> str:
    with open(SRC, encoding="utf-8") as fh:
        return fh.read()


def test_the_pass_branch_exists_and_is_guarded_against_a_missing_composite():
    src = _src()
    assert "CATALYST_RUBRIC_PASSED" in src, "the pass-side telemetry is not wired"
    # The branch must be `elif _composite is not None`, never a bare `else`: a bare else
    # also catches the rubric FAILING to score (composite None), which is not a pass.
    assert re.search(
        r"if _composite is not None and _composite < CATALYST_RUBRIC_MIN_COMPOSITE:"
        r".*?elif _composite is not None:",
        src, re.DOTALL,
    ), "the pass branch must be `elif _composite is not None`, not a bare `else`"


def test_the_pass_row_carries_the_axes_and_the_composite():
    """The whole point is the axes. A row without them answers nothing."""
    src = _src()
    start = src.index("CATALYST_RUBRIC_PASSED")
    block = src[start:start + 2000]
    for needed in ('"axes_scored"', '"composite_scaled"', '"ticker"', '"alert_date"'):
        assert needed in block, f"the pass telemetry row is missing {needed}"


def test_the_telemetry_cannot_break_an_alert():
    """It runs inside its own try/except — a logging failure must not cost us an alert."""
    src = _src()
    start = src.index("# #448 (2026-09-05, operator-directed): the PASS side.")
    block = src[start:start + 3000]  # the row is verbose; the except sits ~2.6k in
    assert "try:" in block and "except Exception as _e:" in block, \
        "the pass telemetry must fail open"
    assert "rubric-pass telemetry failed" in block


def test_it_does_not_mutate_the_verdict():
    """No assignment to the downgrade decision inside the pass branch."""
    src = _src()
    start = src.index("# #448 (2026-09-05, operator-directed): the PASS side.")
    block = src[start:start + 3000]
    assert "_downgrade_reason =" not in block, \
        "the pass-side telemetry must not touch the verdict"


def test_the_event_name_is_registered():
    with open("agents/market_intelligence/audit_events.py", encoding="utf-8") as fh:
        events = fh.read()
    assert 'CATALYST_RUBRIC_PASSED = "catalyst_rubric_passed"' in events
