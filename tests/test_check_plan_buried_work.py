"""Buried-work tripwire in check_plan.py (operator 2026-06-17): a task that NAMES critical-path /
blocker build work in its description must IMMEDIATELY reference the #task that does it — never
describe undone work inline (the #326/#327 miss, where Step 3 was buried in #326's prose and never
filed as its own task). Pins that the gate catches the original shape and doesn't false-positive."""
import re

from scripts.check_plan import _BURIED_WORK


def _flagged(text: str):
    """Mirror the gate's per-phrase check: a buried-work phrase with no #id immediately after it."""
    for m in _BURIED_WORK.finditer(text):
        if not re.match(r"[\s:=(\[–—-]{0,8}#\d+", text[m.end(): m.end() + 12]):
            return m.group(0)
    return None


def test_catches_the_original_buried_326():
    # build described in prose, no #id right after the phrase → the exact failure that shipped.
    orig = ("CRITICAL-PATH BUILD (the only real blocker, integration not from-scratch): wire 9M "
            "sugar babies into the consolidation universe = #270 Step 3 / #311")
    assert _flagged(orig) == "CRITICAL-PATH BUILD"


def test_passes_when_phrase_points_straight_at_a_task():
    assert _flagged("CRITICAL-PATH BUILD = #327 (consolidation entry-watch + 9M feed)") is None
    assert _flagged("the only blocker #327 — wire it") is None
    assert _flagged("critical path = #327") is None


def test_no_false_positive_on_normal_task():
    # ordinary tasks that legitimately mention building something must NOT trip it.
    assert _flagged("build the consolidation entry-watch detector + 13 tests, deploy market-agent") is None
    assert _flagged("RS liquidity floor — raise floor / cap-floor (gated)") is None


def test_incidental_ref_does_not_satisfy_the_gate():
    # the hole in a naive 'has a #ref somewhere' check: an incidental ref must NOT excuse the phrase.
    assert _flagged("CRITICAL-PATH BUILD: wire it — reuse #270 recorder (LIVE)") == "CRITICAL-PATH BUILD"
