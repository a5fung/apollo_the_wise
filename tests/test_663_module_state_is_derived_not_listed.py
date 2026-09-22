"""The byte-identity guards run two scans in ONE process — so module state must be derived, not listed.

#663. `test_toggle_off_is_byte_identical_to_a_scan_with_no_belonging_at_all` flaked in CI on
2026-09-14 and has never reproduced: it passes alone, passes on re-run, and 60 local runs found
nothing. `ep_detector` and `ep_theme_belonging` hold module-level dedupe and "seen" structures
that are first-call-does-X / later-calls-skip BY DESIGN, so if the harness does not clear them
between the two compared scans, scan 1 can behave differently from scan 2 — and whether it does
depends on what earlier tests left behind. Exactly the shape of a once-in-CI flake.

⚠ **WHAT WAS ACTUALLY ESTABLISHED ON 2026-09-22, stated so this file is not read as a fix for the
flake.** An AST scan found 15 per-run state holders in `ep_detector` and 3 in
`ep_theme_belonging`; the harness resets 5. Each of the four un-reset dedupe structures
(`_tinycap_seen`, `_rt_fresh_seen`, `_repoll_shadow_state`, `_corp_action_set`) was PRE-POISONED
and the guard re-run — **none made it fail** (`scripts/probes/_663_poison_the_guard.py`). So this
closes the named suspect CLASS structurally; it does not explain 2026-09-14, and #663 stays open.

⚠ AND THE DERIVED RESET WAS WRONG ON ITS FIRST DRAFT, which is why `_OWN_RESET` exists: a blanket
`.clear()` on `_ctx_cache` destroys the `"key"`/`"ctx"` entries the module INDEXES BY NAME, so the
next call raises KeyError. Caught by running it before wiring it in.
"""
from __future__ import annotations

import importlib

import pytest

from tests._module_state import WATCHED, _NOT_PER_RUN_STATE, reset_all, state_holders


def test_every_per_run_state_holder_is_reachable_by_the_reset():
    """THE GATE. Add `_new_seen: set = set()` to `ep_detector` next month and this fails — which
    is the whole point: a hand-written list would have gone silently stale."""
    cleared = {c.split(" ")[0] for c in reset_all()}
    missing = []
    for mod_name in WATCHED:
        short = mod_name.rsplit(".", 1)[-1]
        for name in state_holders(importlib.import_module(mod_name)):
            if f"{short}.{name}" not in cleared:
                missing.append(f"{short}.{name}")
    assert not missing, (
        f"{len(missing)} module-level state holder(s) survive `reset_all()`: {sorted(missing)}. "
        f"Two scans in one process can therefore diverge on whichever of them a previous test "
        f"populated. Either clear it, or add it to `_NOT_PER_RUN_STATE` WITH the reason it is "
        f"configuration rather than per-run state."
    )


def test_the_population_is_derived_from_source_not_hardcoded():
    """A count floor cannot catch a population defect — name the members. This asserts the
    scanner actually reads the modules, so it cannot pass vacuously on an empty result."""
    import agents.market_intelligence.ep_detector as ed
    holders = state_holders(ed)
    assert len(holders) >= 10, f"the AST scan found only {len(holders)} holders — it is not reading"
    for known in ("_tinycap_seen", "_rt_fresh_seen", "_catalyst_cache", "_repoll_shadow_state"):
        assert known in holders, f"{known} is no longer derived — the scanner stopped seeing it"


def test_config_and_task_handles_are_excluded_with_a_stated_reason():
    """The escape must be a decision on the record. An entry with an empty reason is a silent
    exclusion, which is how the original hole would reopen."""
    assert _NOT_PER_RUN_STATE, "the exclusion list is empty — every holder is being cleared"
    for name, why in _NOT_PER_RUN_STATE.items():
        assert why and len(why) > 15, f"{name} is excluded with no real reason: {why!r}"


def test_resetting_does_not_break_the_caches_it_clears():
    """⚠ THE BUG THIS FILE'S HELPER SHIPPED WITH. `_ctx_cache` is read as `_ctx_cache["key"]` and
    `_fit_day` as `_fit_day["date"]`; a blanket `.clear()` removes those keys and the next call
    raises KeyError. Reverting `_OWN_RESET` to `{}` turns this red."""
    import agents.market_intelligence.ep_theme_belonging as etb
    etb._ctx_cache["key"] = "poisoned"
    etb._fit_day["date"] = "poisoned"
    reset_all()
    assert set(etb._ctx_cache) == {"key", "ctx"}, "clearing destroyed the keys the module indexes"
    assert set(etb._fit_day) == {"date", "calls"}, "clearing destroyed _fit_day's own keys"
    assert etb._ctx_cache["key"] is None and etb._fit_day["date"] is None


def test_reset_is_idempotent_and_safe_to_call_twice():
    """The harness calls it before each of two scans; the second call must not raise."""
    first, second = reset_all(), reset_all()
    assert first == second and first


@pytest.mark.parametrize("cache", ["_tinycap_seen", "_rt_fresh_seen", "_corp_action_set"])
def test_a_poisoned_seen_set_does_not_survive_the_reset(cache):
    """The concrete mechanism: a 'seen' set makes call 2 skip what call 1 did. Poison it and the
    reset must clear it, or the two compared scans start from different worlds.

    ⚠ `_corp_action_set` is declared `set[str] | None = None` and built lazily, so "cleared" for
    it means back to None — the sentinel its own date-guard tests. Asserting `.add()` on it was
    this test's first draft and it failed on NoneType; the honest assertion is that the poison is
    GONE, whatever the empty representation is."""
    import agents.market_intelligence.ep_detector as ed
    setattr(ed, cache, {"XQZT"})
    assert "XQZT" in getattr(ed, cache)
    reset_all()
    after = getattr(ed, cache)
    assert not after or "XQZT" not in after, f"{cache} survived the reset: {after!r}"
