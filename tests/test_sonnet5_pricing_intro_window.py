"""8% of the bill the operator was watching rise was an accounting error (2026-08-07).

He said: *"spend increase is concerning, it keeps going up but you keep saying it's one off or
normal."* Part of the increase was not spend at all.

`claude-sonnet-5` was missing from `PRICING_PER_MTOK` and fell through to the sonnet-TIER rate
of $3/$15. That is its standard rate — but Anthropic is running an introductory $2/$10 through
2026-08-31, so every sonnet-5 call was billed to us at 150% of its real cost. Sonnet-5 is
**24.7% of the 7-day bill**, and **$1.84 of $22.30 was pure mis-pricing** — on a model that got
CHEAPER, while the reported number went up.

The fix is a DATE CHECK, not a constant someone flips on 09-01. A calendar task to change a
number is a task nobody actions, and this repo has the scar tissue: a hand-pinned model rotted
on 4-6 until the operator ruled that pinning itself was the problem.
"""
from datetime import date

import pytest

from shared import llm_models as m


def test_the_intro_rate_applies_today():
    """Through 2026-08-31 sonnet-5 costs $2/$10, not the $3/$15 the tier fallback assumed."""
    if not m._sonnet_5_intro_active():
        pytest.skip("past the intro window — covered by the post-window test below")
    assert m.pricing_for(m.SONNET_5) == {"input": 2.00, "output": 10.00}


def test_it_reverts_to_standard_by_itself(monkeypatch):
    """No calendar task, no constant to flip. On 09-01 the same code returns the standard rate."""
    monkeypatch.setattr(m, "_sonnet_5_intro_active", lambda: False)
    assert m.pricing_for(m.SONNET_5) == {"input": 3.00, "output": 15.00}


def test_a_broken_clock_over_states_rather_than_under_states(monkeypatch):
    """Direction matters. Over-stating spend is visible and annoying; UNDER-stating it hides
    growth, which is the exact thing being watched for."""
    monkeypatch.setattr(m, "_ET_TZ", None)   # what a stripped image without tzdata looks like
    assert m._sonnet_5_intro_active() is False
    assert m.pricing_for(m.SONNET_5)["input"] == 3.00


def test_the_window_boundary_is_inclusive():
    """'Through 2026-08-31' includes the 31st."""
    assert m._SONNET_5_INTRO_UNTIL == date(2026, 8, 31)


def test_sonnet_5_no_longer_falls_through_to_the_tier_fallback():
    """The fallback logs a WARNING every call precisely so a missing rate does not stay silent.
    It logged on every sonnet-5 call for days and nobody read it — an explicit table entry is
    the fix, the warning was only ever the smoke alarm."""
    assert m.SONNET_5 in m.PRICING_PER_MTOK, (
        "claude-sonnet-5 is back to being priced by the tier fallback")


def test_other_models_are_untouched():
    """A dated special case must not leak into anything else."""
    assert m.pricing_for("claude-sonnet-4-6") == {"input": 3.00, "output": 15.00}
    assert m.pricing_for("claude-opus-5") == {"input": 5.00, "output": 25.00}
    assert m.pricing_for("claude-haiku-4-5-20251001") == {"input": 1.00, "output": 5.00}
