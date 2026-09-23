"""A `deployed` task may not rest on an absence alone — a dead system passes that.

WHY (operator 2026-09-10). He asked whether the day's pending verifies were "looking for the right
conditions to be confirmed". Three of four were not, and all three would have been reported as
passes:

  #632  "no page on a sub-P95 night"       — true of an ordinary quiet night that never engages
                                             the guard at all
  #630  "no fallback row on an ordinary morning" — produced IDENTICALLY by the broken code
  #631  "the audit row shows 12 arms considered" — the wrong number; reads 0 when it all works

Only the first class is decidable from text, so only it is gated. The escape is `WOULD-FAIL-IF:` —
saying what a real failure would look like — which is precisely the sentence that was missing from
all three. An alarm that can only be checked by an absence is legitimate; it just has to say so.

⚠ These tests drive the SHIPPED `verify_is_absence_only`, not a copy of its condition — the whole
point of the week that produced them.
"""
import pytest

from scripts.check_plan import verify_is_absence_only


# The real text I shipped on 2026-09-10, before he asked.
_632_AS_SHIPPED = "the nightly audit runs and cooldowns_per_day does not page on a sub-P95 night"
_632_CORRECTED = ("cooldowns_per_day does not page on a sub-P95 night, while an L3 row still "
                  "records the value")


def test_the_condition_i_actually_shipped_is_rejected():
    """Replay the real one. If this passes, the gate would not have caught its own reason to exist."""
    assert verify_is_absence_only(_632_AS_SHIPPED)


def test_adding_the_positive_half_makes_it_acceptable():
    """The fix is not more words — it is an observable that ABSENCE cannot satisfy."""
    assert not verify_is_absence_only(_632_CORRECTED)


def test_a_row_appearing_is_a_positive_observable():
    assert not verify_is_absence_only("a heartbeat row appears on the next buy-side cancel/reject")


def test_a_named_number_is_a_positive_observable():
    assert not verify_is_absence_only("the first fill's risk_dollars reads full size, ~$37")


def test_zero_rows_alone_is_not_enough():
    """"Still zero" is the shape that reads a dead job as a healthy one."""
    assert verify_is_absence_only("no sizing_regime_fallback audit row at 9:31")
    assert verify_is_absence_only("the shadow writes zero rows and nothing is skipped")


def test_empty_text_is_not_flagged():
    """No criterion at all is a different failure, handled by the close ledger's NO-BAR path."""
    assert not verify_is_absence_only("")
