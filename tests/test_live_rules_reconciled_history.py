"""The `⚠now` reconciliation annotation must not silently swallow real drift.

WHY THIS EXISTS
`live_rules.py` gained a skip path on 2026-08-29: a finding may keep its historical number if it
is annotated with the acting one — `MAX_EXTENSION_PCT=75.0 ⚠now 50.0`. Rewriting a finding's
number would falsify the record of what it decided ON; annotating it does not.

But a skip path inside a detector is the most dangerous thing you can add to it. If the regex
OVER-matches, real drift is suppressed and the failure is SILENT — the checker reports clean
while the docs lie, which is worse than having no checker. The advisor flagged that the 18 tests
shipped that day covered the nightly job and not this, and that two brittleness points had
already surfaced while writing it (markdown backticks sitting between the value and the marker;
a case-sensitive `is\\s+on` failing to match `is ON`). That is evidence the notation is fragile,
not evidence it is safe.

So these tests pin the two directions that matter:
  - a STALE annotation must still report drift (the silent-suppression failure)
  - a CORRECT annotation must reconcile, including across the markdown that wraps real docs
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("lr", _REPO / "scripts" / "live_rules.py")
    mod = importlib.util.module_from_spec(spec)
    # Register BEFORE exec: live_rules defines dataclasses, and dataclasses resolve their own
    # module out of sys.modules at class-creation time. Skip this and construction fails with a
    # bare AttributeError on NoneType that says nothing about the real cause.
    sys.modules["lr"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def lr():
    return _load()


def _drift_for(lr, line: str, name: str, actual: float) -> list:
    """Run the value-mismatch rule over a single synthetic line."""
    doc = lr.DocFile(
        path=_REPO / "docs" / "analysis" / "_synthetic.md",
        lines=[line],
        fence_mask=[False], historical_mask=[False],
        line_date=[None],
        changelog_entries=[],
    )

    class _R:
        def const(self, n):
            return lr.Resolved(actual, "test", True) if n == name else None

    return [r for r in lr.scan_value_mismatches([doc], _R()) if r.rule == "value-mismatch"]


def test_a_stale_annotation_still_reports_drift(lr):
    """THE failure that matters: the annotation says 60 but the acting value is 50."""
    rows = _drift_for(lr, "`MAX_EXTENSION_PCT = 75.0` ⚠now 60.0", "MAX_EXTENSION_PCT", 50.0)
    assert rows, (
        "a STALE ⚠now annotation was treated as reconciled — this is the silent-suppression "
        "failure the notation must never have. The annotation is a claim about NOW and has to "
        "keep earning it: when the acting value moves, the annotation goes stale and drift must "
        "fire again."
    )


def test_an_unannotated_stale_value_still_reports_drift(lr):
    """The baseline behaviour must be unchanged by the skip path."""
    assert _drift_for(lr, "`MAX_EXTENSION_PCT = 75.0`", "MAX_EXTENSION_PCT", 50.0)


def test_a_correct_annotation_reconciles(lr):
    assert not _drift_for(lr, "`MAX_EXTENSION_PCT = 75.0` ⚠now 50.0", "MAX_EXTENSION_PCT", 50.0)


@pytest.mark.parametrize("line", [
    "`MAX_EXTENSION_PCT = 75.0` ⚠now 50.0",       # backtick between value and marker
    "**MAX_EXTENSION_PCT=75.0** ⚠now 50.0",        # bold
    "MAX_EXTENSION_PCT=75.0 ⚠now 50.0",            # bare
    "(MAX_EXTENSION_PCT=75.0) ⚠now 50.0",          # parenthesised
    "`MAX_EXTENSION_PCT = 75.0`⚠now 50.0",         # no space
])
def test_the_marker_survives_the_markdown_real_docs_use(lr, line):
    """Both brittleness points found by hand on 2026-08-29 were markup-shaped."""
    assert not _drift_for(lr, line, "MAX_EXTENSION_PCT", 50.0), f"failed to reconcile: {line}"


def test_an_integer_annotation_matches_a_float_acting_value(lr):
    """`⚠now 50` against an acting 50.0 is the same number, and must reconcile."""
    assert not _drift_for(lr, "MAX_EXTENSION_PCT=75.0 ⚠now 50", "MAX_EXTENSION_PCT", 50.0)


def test_the_annotation_does_not_leak_to_a_different_constant(lr):
    """A marker after one constant must not reconcile a DIFFERENT stale constant on the line."""
    rows = _drift_for(lr, "MIN_GAP_PCT=10.0 and MAX_EXTENSION_PCT=75.0 ⚠now 50.0",
                      "MIN_GAP_PCT", 9.0)
    assert rows, "the ⚠now marker suppressed drift on an unrelated constant"
