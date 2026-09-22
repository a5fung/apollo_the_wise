"""`--carryover` could only ever LOOSEN the growth ceiling. He needed the other direction.

2026-09-21. I opened three tasks off a simplify review — after he had said "Do not file any new
tasks without consulting me" — taking the board 59 -> 62. He then ruled: *"If these are real issues
then fix it. When I ask for review of today's work it means find and fix any issues not filing and
deferring."* All three were built the same night and one closed, leaving 61. His answer to the
CLOSE report was one line: **"tmr's ceiling is 59"**.

Nothing in `check_plan.py` could express that. The day-start pin arms at whatever the board happens
to be, and `carryover_allowance` only ever adds — so the three tasks I should not have filed would
have silently bought tomorrow three tasks of headroom. That is the ratchet the growth gate exists
to prevent, arriving through the one door the gate did not watch.

`--set-ceiling N "<reason>"` is the mirror of `--carryover`:
  · it binds DOWNWARD only — the effective ceiling is `min(day-start pin, N)` — so it can never
    permit growth, only demand a burn-down;
  · it SURVIVES the next OPEN, unlike `carryover_allowance` which resets daily, because a
    tightened ceiling is a standing instruction rather than a one-off concession;
  · it CLEARS ITSELF once the board actually reaches it, so it cannot rot into a rule nobody can
    see. Clearing is the one direction that cannot hide growth.
"""
from __future__ import annotations

from datetime import date

import pytest

from scripts.check_plan import (_arm_from_watermark, _carry_operator_ceiling,
                                _growth_gate_error, _pin_daily_baseline, _write_baseline)

TODAY = date(2026, 9, 22)
YESTERDAY = date(2026, 9, 21)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Never touch the real `.apollo_session_baseline.json` — it arms the live gate."""
    import scripts.check_plan as cp
    monkeypatch.setattr(cp, "BASELINE", tmp_path / "baseline.json")


def _base(count: int, ceiling: int | None, day: date = TODAY, set_on: str = "2026-09-21") -> dict:
    b = {"pt_date": day.isoformat(), "baseline_count": count,
         "carryover_allowance": 0, "carryover_reason": None}
    if ceiling is not None:
        b["operator_ceiling"] = {"count": ceiling, "reason": "his ruling", "set_on": set_on}
    return b


def test_the_board_sitting_at_61_does_not_buy_tomorrow_a_ceiling_of_61():
    """The exact case. Day-start pin 61, his ceiling 59: committing at 61 must FAIL."""
    err = _growth_gate_error(61, _base(61, 59), TODAY)
    assert err and "ceiling 59" in err, err
    assert "set BY THE OPERATOR" in err, "the message does not say whose ceiling is binding"


def test_it_passes_once_the_two_are_actually_closed():
    assert _growth_gate_error(59, _base(61, 59), TODAY) is None


def test_it_can_only_ever_tighten_never_loosen():
    """A MIN, not an override. A ceiling ABOVE the day-start pin must change nothing — otherwise
    this becomes a second way to grow the board, which is the opposite of its purpose."""
    assert _growth_gate_error(62, _base(59, 99), TODAY), "a high operator ceiling loosened the gate"
    assert _growth_gate_error(59, _base(59, 99), TODAY) is None


def test_a_carryover_cannot_climb_back_over_it():
    """`--carryover` raises `carryover_allowance`; the operator ceiling still binds. Otherwise the
    escape hatch reopens the door he just shut."""
    b = _base(61, 59)
    b["carryover_allowance"], b["carryover_reason"] = 5, "necessary growth"
    assert _growth_gate_error(61, b, TODAY), "a carryover climbed back over the operator's ceiling"
    assert _growth_gate_error(59, b, TODAY) is None


def test_it_survives_the_next_OPEN_unlike_a_carryover():
    """`carryover_allowance` resets daily on purpose — a one-off concession. A tightened ceiling is
    a STANDING instruction; if it evaporated overnight the pin would re-arm at 61 and the ruling
    would have lasted exactly one day."""
    _write_baseline(_base(61, 59, YESTERDAY))
    pinned = _pin_daily_baseline(61, TODAY)
    assert pinned["operator_ceiling"]["count"] == 59, "the ceiling did not survive the OPEN pin"
    assert pinned["carryover_allowance"] == 0, "a carryover survived the day, which it must not"
    assert _growth_gate_error(61, pinned, TODAY), "the carried ceiling is not binding"


def test_it_survives_a_SKIPPED_open_too():
    """The carry path is a separate code path from the pin, and a rule that held on one but not the
    other would be worse than no rule — it would depend on whether I remembered to run OPEN."""
    prev = _base(61, 59, YESTERDAY)
    prev.update(last_seen_date=YESTERDAY.isoformat(), last_seen_count=61)
    _write_baseline(prev)
    armed = _arm_from_watermark(prev, TODAY)
    assert armed and armed["operator_ceiling"]["count"] == 59
    assert _growth_gate_error(61, armed, TODAY)


def test_it_clears_itself_once_the_board_reaches_it():
    """Self-clearing, so it cannot rot into an invisible standing rule. Once the board is at or
    below it the day-start pin is the tighter of the two anyway."""
    assert _carry_operator_ceiling(_base(61, 59), 59) is None, "a reached ceiling was kept"
    assert _carry_operator_ceiling(_base(61, 59), 58) is None, "a beaten ceiling was kept"
    assert _carry_operator_ceiling(_base(61, 59), 60)["count"] == 59, "an unmet ceiling was dropped"


def test_a_malformed_ceiling_is_ignored_rather_than_crashing_the_gate():
    """This runs in the pre-commit hook. A hand-edited baseline file must never be able to take
    every commit down, and must never be able to silently DISABLE the gate either."""
    for junk in ({"count": "fifty-nine"}, {"reason": "no count"}, "59", None, []):
        b = _base(61, None)
        b["operator_ceiling"] = junk
        assert _growth_gate_error(62, b, TODAY), f"{junk!r} disabled the growth gate"
        assert _growth_gate_error(61, b, TODAY) is None, f"{junk!r} tightened the gate by accident"
        assert _carry_operator_ceiling(b, 61) is None


def test_it_does_not_bind_on_the_day_it_was_SET():
    """He said "TMR's ceiling is 59". The day it is set has already been worked and closed under
    the ceiling that was in force then, so binding it retroactively would rewrite a finished day —
    and would block the very commit that records the instruction, which is a neat way to make a
    rule impossible to land."""
    same_day = _base(61, 59, day=YESTERDAY, set_on=YESTERDAY.isoformat())
    assert _growth_gate_error(61, same_day, YESTERDAY) is None, (
        "the ceiling bound on the day it was set — it is tomorrow's ceiling, not today's"
    )
    # ...and it bites the very next day.
    next_day = _base(61, 59, day=TODAY, set_on=YESTERDAY.isoformat())
    assert _growth_gate_error(61, next_day, TODAY), "it never started binding at all"
