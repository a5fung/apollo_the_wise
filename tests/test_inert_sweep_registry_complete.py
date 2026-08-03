"""A NEW sweep study cannot exist without being checked (operator 2026-08-03).

The inert-sweep check (#521) catches a study whose varied setting isn't reaching the code. Its
registry is hand-written, which left an obvious hole: *a new study that nobody adds is never
checked* — the same silence that let `mi_orb_extension_shadow` run degenerate for 91 days.

Operator: *"make sure new studies must be added to activate."*

So this test DISCOVERS candidate sweep lanes from the schema source of truth (`db.py`, per
CLAUDE.md) and fails if any discovered lane is in neither list:
  * `_SWEEP_LANES`      — checked nightly, or
  * `_NOT_SWEEP_PARAMS` — declared not-a-study-parameter, WITH a reason.

Same shape as the scheduler's role-partition omission guard, which refuses to boot on a registered
job that is in neither ownership set. Everything discovered must be classified; silence is not an
option. Adding a study now costs one line, and forgetting costs a red build instead of three months
of meaningless data.
"""
import re

from agents.market_intelligence import health_checks as hc

_DB = open("agents/market_intelligence/db.py").read()

# A column whose NAME suggests a varied experimental setting.
_PARAM_LIKE = re.compile(
    r"^\s*(\w*(?:variant|cutoff|arm|band|rule|mode|width|tier)\w*)\s+", re.I | re.M)


def discovered_lanes() -> dict:
    """{table: [param-like columns]} for every shadow table declared in db.py."""
    out = {}
    for table, body in re.findall(
            r"CREATE TABLE IF NOT EXISTS (mi_\w*shadow\w*)\s*\((.*?)\n\s*\)\s*;", _DB, re.S):
        cols = sorted(set(_PARAM_LIKE.findall(body)))
        if cols:
            out[table] = cols
    return out


def test_discovery_finds_something():
    """Guard the guard: if the regex ever stops matching db.py's shape, every check below passes
    vacuously — which is precisely the failure mode this file exists to prevent."""
    found = discovered_lanes()
    assert len(found) >= 4, f"only discovered {found} — the schema parser is broken"


def test_every_discovered_sweep_is_either_CHECKED_or_DECLARED_NOT_A_SWEEP():
    """THE gate. A new study must be classified, one way or the other, or this fails."""
    checked = {(t, c) for t, c, _o, _m in hc._SWEEP_LANES}
    unclassified = []
    for table, cols in discovered_lanes().items():
        for col in cols:
            if (table, col) in checked or col in hc._NOT_SWEEP_PARAMS:
                continue
            unclassified.append(f"{table}.{col}")
    assert not unclassified, (
        "sweep-like column(s) in neither list: " + ", ".join(unclassified) + "\n"
        "Add to health_checks._SWEEP_LANES to have it checked nightly, or to _NOT_SWEEP_PARAMS "
        "with a reason. An unclassified study is one nobody is watching — that is how "
        "mi_orb_extension_shadow ran degenerate for 91 days.")


def test_every_not_a_sweep_declaration_carries_a_reason():
    """An empty reason turns this list into a mute suppression list."""
    for col, why in hc._NOT_SWEEP_PARAMS.items():
        assert len(why) > 30, f"{col} needs a real reason, not '{why}'"


def test_the_checked_registry_only_names_real_tables():
    """A typo'd table name would be silently skipped as 'table absent' at runtime."""
    declared = set(re.findall(r"CREATE TABLE IF NOT EXISTS (mi_\w+)", _DB))
    for table, *_ in hc._SWEEP_LANES:
        assert table in declared, f"{table} is not declared in db.py — typo?"


def test_the_lane_that_broke_is_still_checked():
    assert any(t == "mi_orb_extension_shadow" for t, *_ in hc._SWEEP_LANES)
