"""The unprotected-position alert must name a repair that can still happen.

WHY (2026-09-11, OKTA, live money). The alert ended *"Remediation runs at 4:05 PM ET — monitor"*
regardless of the hour, and it reached him at **16:45** — forty minutes after 16:05 had already
run. It named a repair that could not come, and he stood down on it. A message that promises a
repair which has already passed is worse than one that says nothing: in the reader's head it turns
an unprotected position into a handled one.

The repair times are facts about the schedule, so the sentence is computed rather than asserted.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence.broker.trade_stream import _next_repair_sentence

ET = ZoneInfo("America/New_York")


def _at(h, m, day=11):          # 2026-09-11 is a Friday
    return datetime(2026, 9, day, h, m, tzinfo=ET)


def test_the_okta_case_after_the_last_repair_it_says_so_loudly():
    """THE REGRESSION: 16:45 on a Friday. Nothing repairs this until Monday."""
    out = _next_repair_sentence(_at(16, 45))
    assert "4:05" not in out, "it still names a repair that has already run"
    assert "Monday" in out and "9:31" in out
    assert "NOT fix itself" in out


def test_inside_the_window_it_names_the_five_minute_job():
    assert "every 5 minutes" in _next_repair_sentence(_at(11, 0))


def test_before_the_open_it_names_the_start():
    assert "9:31" in _next_repair_sentence(_at(7, 30))


def test_between_the_window_closing_and_eod_it_still_names_4_05():
    """15:56 to 16:05 is the one window where the old sentence was true."""
    assert "4:05" in _next_repair_sentence(_at(16, 0))


def test_midweek_after_hours_says_tomorrow_not_monday():
    """Wednesday 2026-09-09 — the next session is the next day."""
    out = _next_repair_sentence(_at(18, 0, day=9))
    assert "tomorrow" in out and "Monday" not in out


@pytest.mark.parametrize("h,m", [(9, 30), (15, 56), (16, 6), (23, 59), (0, 1)])
def test_it_always_returns_a_sentence(h, m):
    """It sits on an alert path — it may never raise or return nothing."""
    assert _next_repair_sentence(_at(h, m)).strip()


# ── Pin the WIRING, not just the helper (2026-09-11) ─────────────────────────────────────────
#
# My own RED run caught this: reverting the CALL SITE to the hardcoded "Remediation runs at 4:05 PM
# ET" left all ten tests above green, because they exercise the helper in isolation. A correct
# function nobody calls is the same defect as no function — the #540 lesson, and the reason
# test_audit_detail_json_safe_truncation pins its call site too.

def test_the_alert_actually_calls_it():
    import inspect

    from agents.market_intelligence.broker import trade_stream
    src = inspect.getsource(trade_stream)
    # ⚠ anchor on the f-string in the ALERT, not on the first mention of the phrase — the words
    # "Position unprotected (N sh)" also appear in a COMMENT 465 lines earlier, and anchoring there
    # made this test fail against correct code. Found on its own first run.
    i = src.index("""f"Position unprotected ({stop_trade""")
    window = src[i:i + 400]
    assert "_next_repair_sentence(" in window, (
        "the unprotected alert stopped computing the repair time")
    assert "Remediation runs at 4:05 PM ET" not in window, (
        "the hardcoded repair hour is back in the alert")
