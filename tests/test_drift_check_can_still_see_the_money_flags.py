"""The nightly drift check went blind to the kill switch, and its report said "0 findings".

FOUND 2026-09-21 by an adversarial review of that evening's own work, hours after the change that
caused it. #681 replaced ~30 hand-rolled `os.environ.get(V,"false").lower()=="true"` expressions
with `shared.env_flags.env_is_true(V, default=...)`. Every migrated site was byte-identical at
runtime — and `scripts/live_rules._classify_value` recognised boolean env constants by exactly ONE
AST shape: an `ast.Compare` over a `.lower()` call. The new shape is an `ast.Call`, so it matched
nothing and **nine flags silently left the fact index**, among them `LIVE_TRADING_ENABLED` (the
master kill switch), `ENABLE_LIVE_MODE` and `REGIME_SIZING_ENABLED`.

That index is not a report-only convenience. `_identifier_states` drops a missing fact with a bare
`continue`, and the PRODUCTION nightly job `health_checks.run_drift_check` builds its prod-env
snapshot from the same index — so the container stopped reading those variables out of its own
environment at all. The observer built after the 2026-08-23 stale-doc incident, specifically to
catch a doc claiming a flag was off while prod had it on, could no longer see the two flags that
incident was about.

⚠ AND IT READ GREEN. `live_rules.py --drift-only` printed "0 finding(s) — every checked claim
matches the acting state", which is the identical line a fully working checker prints. That is a
NON-DISCRIMINATING pass: it is what the BROKEN system produces too, which is exactly why the
session-open check that morning sailed through. [[never-let-him-be-the-check]]

This test is offline and derives from the real modules. `--selftest` case 2 replays the 2026-08-23
incident end-to-end and did regress PASS -> FAIL, but it resolves against the LIVE container
environment over SSH, so it cannot be the gate. Naming the members here can.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.live_rules import parse_module_constants

REPO = Path(__file__).resolve().parents[1]

#: Flags whose disappearance from the index makes the drift check blind to something that moves
#: real money, or gates a live detection path. NAMED, never counted — a count floor cannot catch
#: a population defect, which is the lesson from the job-date gate that saw 46 of 60 jobs.
#: [[derive-the-population-never-hand-list-it]]
MUST_BE_VISIBLE = {
    "agents/market_intelligence/constants.py": [
        "LIVE_TRADING_ENABLED",           # the master kill switch
        "ENABLE_LIVE_MODE",               # dual-account routing
        "REGIME_SIZING_ENABLED",          # position sizing — the 2026-08-23 incident flag
        "CRYPTO_RS_ENABLED",
        "EARNINGS_REVENUE_GATE_ENABLED",
        "CATALYST_RUBRIC_GATE_ENABLED",
    ],
    "agents/market_intelligence/ep_detector.py": [
        "EP_RT_PASS2_ENABLED",
        "EP_RT_UNIVERSE_ENABLED",
        "EP_RT_MISS_WATCHDOG_ENABLED",
    ],
}


def _facts(rel: str) -> dict:
    return parse_module_constants((REPO / rel).read_text(encoding="utf-8"), Path(rel).stem)


@pytest.mark.parametrize("rel,names", sorted(MUST_BE_VISIBLE.items()))
def test_every_money_flag_is_still_in_the_drift_checkers_fact_index(rel, names):
    """The regression itself. Revert `_classify_value`'s `env_is_true` branch and this names every
    flag that vanished, instead of the tool printing a confident "0 findings"."""
    facts = _facts(rel)
    missing = [n for n in names if n not in facts]
    assert not missing, (
        f"{len(missing)} flag(s) in {rel} are invisible to `live_rules.py`, so the nightly drift "
        f"check can no longer tell whether a doc claiming they are off matches prod: {missing}. "
        f"`_classify_value` most likely does not recognise however they are now written."
    )


@pytest.mark.parametrize("rel,names", sorted(MUST_BE_VISIBLE.items()))
def test_each_one_is_read_as_a_boolean_env_flag_with_the_right_default(rel, names):
    """Present is not enough — it has to be classified as an ENV BOOL, and the DEFAULT has to be
    right, or the drift check compares the doc against the wrong baseline. `ENABLE_LIVE_MODE` and
    the three gate flags default ON; the rest default OFF."""
    facts = _facts(rel)
    for n in names:
        fact = facts[n]
        assert fact.kind == "env", f"{n} is classified {fact.kind!r}, not an env flag"
        assert fact.cast == "bool", f"{n} is cast {fact.cast!r}, not bool"
        assert isinstance(fact.value, bool), f"{n}'s default is {fact.value!r}, not a bool"
        assert fact.env_var == n, f"{n} is indexed under env var {fact.env_var!r}"


def test_the_defaults_match_what_the_code_actually_does():
    """Cross-check the parsed default against the live module, so the index cannot drift from the
    constant it describes — a wrong default silently reverses every claim checked against it."""
    from agents.market_intelligence import constants
    facts = _facts("agents/market_intelligence/constants.py")
    import os
    for name in MUST_BE_VISIBLE["agents/market_intelligence/constants.py"]:
        if os.environ.get(name) is not None:
            continue  # the env is set in this shell, so the module value is not the default
        if not hasattr(constants, name):
            continue  # not a module-level constant (e.g. resolved through a function)
        assert facts[name].value is getattr(constants, name), (
            f"{name}: the drift checker thinks the default is {facts[name].value}, but the module "
            f"evaluates to {getattr(constants, name)} with the variable unset"
        )


def test_the_shared_readers_are_both_recognised():
    """`env_flag_on` (permissive) and `env_is_true` (exact) are the two sanctioned readers. A
    module constant written with either must land in the index — otherwise the next migration
    re-opens this hole from the other side."""
    import ast
    from scripts.live_rules import _classify_value
    for src, want_default in (('env_is_true("X")', False),
                              ('env_is_true("X", default=True)', True),
                              ('env_flag_on("X")', False)):
        node = ast.parse(src, mode="eval").body
        got = _classify_value(node)
        assert got is not None, f"{src} is not recognised as an env flag"
        assert got["kind"] == "env" and got["cast"] == "bool" and got["env_var"] == "X"
        assert got["value"] is want_default, f"{src} parsed default {got['value']}, want {want_default}"
