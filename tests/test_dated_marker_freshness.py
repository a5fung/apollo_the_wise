"""Two dated markers in check_plan.py had drifted, and the older one had a real hole.

Found 2026-08-07 by the /simplify reuse + altitude passes, independently. `check_plan.py` carries
two `<name>:YYYY-MM-DD` markers that mute a surface or a gate:

  `swept:`       — mutes the advisory LIKELY-BUILT surface (added 2026-08-06)
  `revalidated:` — satisfies the stale-block gate, which HARD-FAILS the commit

Both parsed a date and compared an age to a threshold, written independently. They had already
diverged: the newer one bounded `0 <= age`, the older one did not. So a `revalidated:2099-01-01`
produced a NEGATIVE age, satisfied `<= _REVALIDATE_MAX_AGE`, and read as FRESH — indefinite
silence on the one gate here that actually blocks commits, bought by typing a future date.

No board task was ever future-dated (checked before the fix), so this pins hardening rather than
a live break. Both markers now share `_marker_age_days`, which returns None for anything
untrustworthy — absent, malformed, or ahead of today.
"""
from datetime import date, timedelta

import pytest

from scripts.check_plan import (
    _REVALIDATE_MAX_AGE,
    _REVALIDATED,
    _SWEPT,
    _marker_age_days,
)

TODAY = date(2026, 8, 7)


@pytest.mark.parametrize("pattern,name", [(_REVALIDATED, "revalidated"), (_SWEPT, "swept")])
def test_a_future_dated_marker_is_untrusted_on_BOTH_markers(pattern, name):
    """The hole, and the reason the helper is shared: fixing one marker and not the other is
    exactly how this drift happened in the first place."""
    assert _marker_age_days(pattern, f"{name}:2099-01-01", TODAY) is None


@pytest.mark.parametrize("pattern,name", [(_REVALIDATED, "revalidated"), (_SWEPT, "swept")])
def test_a_malformed_date_is_untrusted_on_BOTH_markers(pattern, name):
    for bad in ("2026-13-45", "not-a-date", "26-08-07"):
        assert _marker_age_days(pattern, f"{name}:{bad}", TODAY) is None, bad


@pytest.mark.parametrize("pattern,name", [(_REVALIDATED, "revalidated"), (_SWEPT, "swept")])
def test_an_absent_marker_is_untrusted(pattern, name):
    assert _marker_age_days(pattern, "a task with no marker at all", TODAY) is None


def test_today_is_age_zero_not_rejected():
    """Off-by-one guard: a marker written TODAY is the commonest case and must be trusted."""
    assert _marker_age_days(_REVALIDATED, f"revalidated:{TODAY.isoformat()}", TODAY) == 0


def test_age_is_measured_in_days():
    d = TODAY - timedelta(days=17)
    assert _marker_age_days(_REVALIDATED, f"revalidated:{d.isoformat()}", TODAY) == 17


def test_the_stale_block_gate_actually_uses_the_shared_helper():
    """Guard the guard. The helper could be correct while the gate kept its own inline copy —
    which is the state this fix removed, so a regression to it must fail loudly rather than
    leave these tests passing against unused code."""
    import inspect

    from scripts.check_plan import _stale_block_gate
    src = inspect.getsource(_stale_block_gate)
    assert "_marker_age_days" in src, (
        "the stale-block gate no longer routes through _marker_age_days — if it went back to an "
        "inline date parse, the future-date hole is open again")
    assert "date.fromisoformat" not in src, (
        "the stale-block gate is parsing a date inline again; that is the duplication whose "
        "drift caused the future-date hole")


def test_mutation_dropping_the_lower_bound_reopens_the_hole():
    """Executable proof the future-date tests are load-bearing: the pre-fix logic
    (`age <= MAX`, no lower bound) accepts a marker dated 73 years out."""
    naive_age = (TODAY - date(2099, 1, 1)).days          # negative
    assert naive_age <= _REVALIDATE_MAX_AGE, "fixture no longer reproduces the old logic"
    assert _marker_age_days(_REVALIDATED, "revalidated:2099-01-01", TODAY) is None, (
        "the real implementation must reject what the old logic accepted")
