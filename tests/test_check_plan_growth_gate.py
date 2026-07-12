"""Session growth gate in check_plan.py (operator 2026-07-12, HARD): a session may NOT end with
more open tasks than the PT-day began with. After a month of fake burndown (PLAN.md 99->116 across
four 'exercises'), only a mechanical gate holds. `--today` pins the day-start count; the plain gate
fails any commit that ends the day above it; the sole escape is an operator-signed carryover.
Pins the pure ceiling-check across the cases that matter."""
from datetime import date

from scripts.check_plan import _growth_gate_error

TODAY = date(2026, 7, 12)
ISO = TODAY.isoformat()


def _base(count, allowance=0, reason=None, pt_date=ISO):
    return {"pt_date": pt_date, "baseline_count": count,
            "carryover_allowance": allowance, "carryover_reason": reason}


def test_at_baseline_passes():
    assert _growth_gate_error(116, _base(116), TODAY) is None


def test_below_baseline_passes():
    # real burndown — ended lower than it began
    assert _growth_gate_error(114, _base(116), TODAY) is None


def test_above_baseline_fails():
    err = _growth_gate_error(117, _base(116), TODAY)
    assert err is not None
    assert "SESSION GROWTH GATE" in err and "ceiling 116" in err and "117 open tasks" in err


def test_carryover_raises_ceiling():
    # operator signed +2 → 118 is allowed, 119 is not
    assert _growth_gate_error(118, _base(116, allowance=2, reason="fable block cards"), TODAY) is None
    err = _growth_gate_error(119, _base(116, allowance=2, reason="fable block cards"), TODAY)
    assert err is not None and "+2 carryover: fable block cards" in err


def test_no_baseline_skips():
    # gate un-armed (no --today yet) → never blocks a commit
    assert _growth_gate_error(999, None, TODAY) is None


def test_stale_baseline_skips():
    # yesterday's baseline is not today's — a new day re-arms via --today, not this gate
    assert _growth_gate_error(999, _base(116, pt_date="2026-07-11"), TODAY) is None
