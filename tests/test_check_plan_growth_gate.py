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


# ─── the quiet-skip case (operator 2026-07-31) ───────────────────────────────
# The OPEN ritual is triggered by hand ("start the day"), not by a hook. On a day
# it isn't run, yesterday's baseline file is still on disk: _growth_gate_error
# skips (correctly — the day was never armed) but the "no baseline" note does NOT
# fire, because the file exists. The gate was off and silent. It must be LOUD.

def test_stale_dated_baseline_still_skips_the_gate():
    """Skipping is right — an unarmed day must not be judged against yesterday's
    ceiling. This pins that the SKIP itself is unchanged; the fix is the warning."""
    from datetime import timedelta
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    assert _growth_gate_error(999, _base(1, pt_date=yesterday), TODAY) is None


def test_unarmed_day_WARNS_instead_of_passing_silently(monkeypatch, tmp_path, capsys):
    """The whole point: a day with no OPEN ritual must SAY the gate is off."""
    import json
    from datetime import timedelta
    from tests.test_check_plan_deployed import _run_main
    stale = json.dumps({"pt_date": (TODAY - timedelta(days=1)).isoformat(),
                        "baseline_count": 1, "carryover_allowance": 0, "carryover_reason": None})
    from tests.test_check_plan_deployed import FUTURE
    plan = (f"## Ops\n- #9901 | {FUTURE} | in_progress | build the widget -> tests green\n")
    rc = _run_main(monkeypatch, tmp_path, plan, baseline=stale)
    out = capsys.readouterr().out
    assert "NOT ARMED" in out, "an unarmed day passed without saying so"
    assert rc == 0, "the warning must not fail the commit — it is a notice, not a gate"
