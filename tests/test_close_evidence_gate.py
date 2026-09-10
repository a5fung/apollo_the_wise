"""A task may not leave PLAN.md unless the close is judged against the task's OWN DoD.

WHY (operator 2026-09-10). He caught four bad calls in one morning and then asked the question this
gate answers: *"Do I need to ask you to double check all your work every time and re prompt you
after things are closed? You can expect me to do this every time. How do we solve this?"*

The worst of the four: #540 was CLOSED on a liveness heartbeat while its DoD demanded a non-null
`broker_reason` on a real rejection. The heartbeat fires on the branch with no tracked entry row, so
it carries no reason at all — a strictly weaker fact that happened to be true. The line held BOTH a
DoD and a later, narrower VERIFY sentence about that sub-feature, and the narrow one got matched.

**A close is the one irreversible act in this repo with nothing checking it**: the line vanishes from
PLAN.md and any unmet criterion vanishes with it. Hence a gate, not a resolution — every prose
commitment here has failed and been replaced by a gate, and this is that gate.

The cases below use the REAL #540 text.
"""
import pytest

from scripts.check_plan import close_bar_for, close_bar_matches

# The real shape: a DoD, then a later VERIFY sentence about one sub-feature.
_540 = (
    "**A live entry was rejected on a stock that ran +33%, and Alpaca had told us why.** "
    "DoD: the next broker cancel OR rejection carries a non-null `broker_reason` in its audit row "
    "and Telegram — proven on a real live event, not a replay.** This is the exact defect class the "
    "task exists to close. ▶ The heartbeat now fires inside `_handle_cancel_or_reject` on a buy-side "
    "order whose `entry_trade` lookup finds nothing, so the handler proves itself alive. "
    "▶ **VERIFY: a heartbeat row appears on the next buy-side cancel/reject.**"
)

_WHAT_I_CHECKED = "a heartbeat row appears on the next buy-side cancel/reject"
_THE_REAL_BAR = "the next broker cancel OR rejection carries a non-null broker_reason"


def test_the_dod_outranks_a_later_verify_sentence():
    """THE ORDERING IS THE POINT. A sub-feature's verify line must not become the closing bar."""
    kind, bar = close_bar_for(_540)
    assert kind == "DoD"
    assert "broker_reason" in bar
    assert "heartbeat" not in bar.lower(), (
        "close_bar_for picked the narrow VERIFY sentence over the DoD — the exact #540 mistake")


def test_the_actual_mistake_is_rejected():
    """Replay 2026-09-10: closing #540 on the heartbeat must FAIL."""
    _, bar = close_bar_for(_540)
    assert not close_bar_matches(_WHAT_I_CHECKED, bar), (
        "the gate accepted a heartbeat as evidence for a broker_reason DoD — it would not have "
        "caught the close it exists to catch")


def test_an_honest_close_is_accepted():
    """It must not block real work: quoting part of the DoD passes."""
    _, bar = close_bar_for(_540)
    assert close_bar_matches(_THE_REAL_BAR, bar)


def test_partial_quotes_and_markdown_do_not_decide_it():
    """A close quotes PART of a long DoD, and backticks/case must never be the deciding factor."""
    _, bar = close_bar_for(_540)
    assert close_bar_matches("carries a NON-NULL `broker_reason` in its audit row", bar)
    assert close_bar_matches("proven on a real live event, not a replay", bar)


def test_a_plausible_paraphrase_still_fails():
    """Restating the DoD in your own words is not quoting it — that is how substitution starts."""
    _, bar = close_bar_for(_540)
    assert not close_bar_matches("the rejection path emits a reason we can read", bar)


def test_verify_live_is_used_when_there_is_no_dod():
    """Older lines carry no DoD; VERIFY-LIVE is then the bar rather than nothing."""
    line = ("Phases 2-3 re-granularization. VERIFY-LIVE = `mi_themes.parent_theme` NON-NULL for the "
            "cyber-vuln child on Monday's row. ▶ next steps follow")
    kind, bar = close_bar_for(line)
    assert kind == "VERIFY-LIVE"
    assert close_bar_matches("mi_themes.parent_theme NON-NULL for the cyber-vuln child", bar)


def test_a_line_with_no_criterion_at_all_returns_none():
    """Then the ledger must carry NO-BAR-DECLARED — closing a task that never defined done."""
    assert close_bar_for("- some old line with no stated criterion whatsoever, just prose") is None


def test_empty_inputs_never_pass():
    assert not close_bar_matches("", "anything at all here")
    assert not close_bar_matches("something", "")
