"""Every task must say what done means, and the close gate must judge against that same text.

WHY (operator 2026-09-10). After the close gate shipped he asked the question that found the hole
underneath it: *"is dod required for every task?"* It was not — 21 of 66 open tasks stated no
checkable criterion, two of them already marked `deployed`. A task with no DoD closes on
`NO-BAR-DECLARED` prose, which is the soft path the close gate exists to remove.

CLAUDE.md has demanded "a CLEAR OUTCOME AT CREATION" since 2026-06-20. Only project/ETA/status/title
were ever enforced; the OUTCOME half was prose, and prose has never held here.

⚠ ONE EXTRACTOR, deliberately: `close_bar_for` decides both what satisfies this gate and what a
close is judged against, so a task cannot satisfy one and fail the other.
"""
import pytest

from scripts.check_plan import close_bar_for


def _bar(line):
    b = close_bar_for(line)
    return None if b is None else b[1]


def test_a_task_with_no_criterion_is_caught():
    assert close_bar_for("build the widget, it is important and long overdue") is None


def test_dod_is_accepted():
    assert _bar("do the thing. DoD: the nightly job writes at least one row to mi_foo.")


def test_verify_live_is_accepted():
    assert _bar("shipped it. VERIFY-LIVE = the flag reads true on the running image.")


def test_a_dod_added_to_an_old_line_is_accepted():
    """The parenthetical form is what you write when retrofitting — it must not be invisible.

    This exact shape was silently rejected when the retrofit began, so five real DoDs did not
    register and the backfill looked like it had failed.
    """
    assert _bar("long history here. **DoD (written 2026-09-10): the two gates are re-derived "
                "and flag counts return to their pre-gate order of magnitude.**")


def test_a_dod_in_the_MIDDLE_of_a_long_line_is_found():
    """Real lines are thousands of characters; the criterion is rarely at the end.

    A 600-char capture bound made #466's DoD unreachable and inflated the "no criterion" count
    from 21 to 30 — a number I reported before checking the tool that produced it.
    """
    line = ("DoD: classify each of the 81 baseline swallows and drive the count to zero. "
            + "context " * 400 + " and more trailing prose")
    assert _bar(line)


def test_the_close_gate_and_this_gate_share_one_extractor():
    """If they diverged, a task could satisfy creation and then be unclosable, or vice versa."""
    import inspect

    from scripts import check_plan as cp
    assert "close_bar_for" in inspect.getsource(cp._dod_required_gate)
    assert "close_bar_for" in inspect.getsource(cp._close_evidence_gate)


def test_the_live_board_has_no_task_without_a_criterion():
    """The backfill is real, not aspirational — proof the gate was born green."""
    import pathlib

    from scripts.check_plan import _TASK
    missing = [m.group(1) for ln in pathlib.Path("PLAN.md").read_text(encoding="utf-8").splitlines()
               if (m := _TASK.match(ln)) and close_bar_for(m.group(4)) is None]
    assert not missing, f"tasks with no stated criterion: {missing}"
