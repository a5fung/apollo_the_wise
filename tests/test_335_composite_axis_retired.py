"""#335 (2026-09-19) — unplug the theme-axis credit from the live composite-authority
wire-in, on operator ruling 2026-09-15 ("aligned, keep container"): DROP the theme axis,
KEEP the composite-authority rail for #331 (gap-vs-structure).

`compute_theme_axis_credit_live` (catalyst_rubric_runtime.py) is RETIRED — it was the
ONLY caller feeding the live composite block. The composite block itself was extracted
out of the `_judge_shadow` closure into a module-level, directly-testable
`ep_detector._apply_composite_authority(r, new_tier, authority, do_override)`, gated by
the `_COMPOSITE_AXIS_CREDIT_SOURCES` registry (empty today — the rail #331 appends its
own axis credit function to).

DoD (PLAN.md #335): with zero axes registered, a scan produces byte-identical grades to
today with the toggle ON *and* OFF, proven by a test that RED-fails if the composer is
reached at all; `compute_theme_axis_credit_live` no longer exists; the toggle and
composer still do.
"""
import asyncio

import agents.market_intelligence.catalyst_rubric_runtime as crr
import agents.market_intelligence.db as db
import agents.market_intelligence.ep_detector as ep
import agents.market_intelligence.meta_rubric_compose as mrc


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ─── (1) compute_theme_axis_credit_live no longer exists ───────────────────────────────


def test_compute_theme_axis_credit_live_retired():
    """RED-proof: this assertion fails on the pre-#335 code (the function exists there —
    confirmed by running this test against the pre-edit source, where `hasattr` is True)
    and passes only after the deletion in catalyst_rubric_runtime.py. Ran RED before the
    delete, GREEN after, as the commit's own before/after (no synthetic mutation needed
    for a deletion task — the deletion itself is the mutation under test, run in reverse)."""
    assert not hasattr(crr, "compute_theme_axis_credit_live")
    # Also not importable directly (belt-and-braces vs a stray re-export elsewhere).
    import inspect
    names = {n for n, _ in inspect.getmembers(crr) if not n.startswith("__")}
    assert "compute_theme_axis_credit_live" not in names


# ─── (2) the toggle and composer still exist ────────────────────────────────────────────


def test_toggle_and_composer_still_exist():
    """DoD: '...the toggle and composer still do [exist]'. #331's rail depends on both
    being untouched — this is the existence half of that guarantee (the behavioral half
    is proven by test_registering_an_axis_composes below).

    MUTATION: temporarily renamed `compose_final_tier` in meta_rubric_compose.py to
    `_compose_final_tier_RENAMED_FOR_MUTATION_TEST` — this test's last assertion
    (`callable(mrc.compose_final_tier)`) failed with AttributeError. Restored; verified
    by hand before committing."""
    assert callable(db.get_composite_authority_enabled)
    assert callable(mrc.resolve_composite_tier)
    assert callable(mrc.compose_final_tier)


# ─── (3) zero axes registered -> explicit, tested no-op; composer unreached ────────────


def _spy_resolve_composite_tier(monkeypatch):
    """A NON-RAISING spy — `_apply_composite_authority`'s own try/except would swallow a
    raise and make a reached-but-failed composer indistinguishable from an unreached one.
    Recording calls instead detects 'reached at all' regardless of what it returns."""
    calls = []

    def _spy(*a, **k):
        calls.append((a, k))
        return ("HIGH", "composite", True, None)  # arbitrary valid-shaped return

    monkeypatch.setattr(mrc, "resolve_composite_tier", _spy)
    return calls


def test_zero_axes_registered_toggle_on_is_byte_identical_composer_unreached(monkeypatch):
    """MUTATION (proves this test is RED-provable): delete the
    `if not _COMPOSITE_AXIS_CREDIT_SOURCES: return ...` early-return AND delete the
    `if not credits: return ...` guard inside `_apply_composite_authority` (i.e. call
    `resolve_composite_tier` unconditionally, the shape the code had before #335's
    extraction relied on an always-present credit). With BOTH guards removed and the
    toggle True, `resolve_composite_tier` gets called once with `credits=[]` — `calls`
    becomes non-empty and this test fails. Restoring either guard alone is insufficient
    (the other still lets the call through), which is why both were removed together
    to red-prove the assertion; verified by hand, then restored — see the commit message
    for the exact before/after pytest output."""
    assert ep._COMPOSITE_AXIS_CREDIT_SOURCES == []  # the shipped-today state
    calls = _spy_resolve_composite_tier(monkeypatch)

    async def _toggle_true():
        return True
    monkeypatch.setattr(db, "get_composite_authority_enabled", _toggle_true)

    r = {"ticker": "ABCD", "alert_date": "2026-09-19"}
    result = _run(ep._apply_composite_authority(r, "MODERATE", "judge", True))

    assert result == ("MODERATE", "judge", True), "toggle ON must not move the tier"
    assert calls == [], "the composer (resolve_composite_tier) must never be reached"
    assert "composite_trace" not in r


def test_zero_axes_registered_toggle_off_is_byte_identical_composer_unreached(monkeypatch):
    """Same as above with the toggle OFF — DoD requires BOTH toggle states to read
    identically with zero axes registered. MUTATION: same as the ON-side test."""
    assert ep._COMPOSITE_AXIS_CREDIT_SOURCES == []
    calls = _spy_resolve_composite_tier(monkeypatch)

    async def _toggle_false():
        return False
    monkeypatch.setattr(db, "get_composite_authority_enabled", _toggle_false)

    r = {"ticker": "ABCD", "alert_date": "2026-09-19"}
    result = _run(ep._apply_composite_authority(r, "MODERATE", "judge", True))

    assert result == ("MODERATE", "judge", True)
    assert calls == []
    assert "composite_trace" not in r


def test_zero_axes_registered_on_and_off_agree_byte_identically(monkeypatch):
    """The DoD's literal claim in one assertion: toggle ON and toggle OFF produce the
    SAME (tier, authority, override) triple for every base-decision shape a real scan can
    hand in (floor/no-override, judge/override, fallback/override).

    MUTATION (a real discriminator, not a code-path break like the other tests here —
    this one proves the ASSERTION would have caught the pre-#335 shape): temporarily
    seeded `_COMPOSITE_AXIS_CREDIT_SOURCES` at module level with a fake always-fires
    +1 axis (simulating "theme still plugged in"). Toggle ON then composes
    MODERATE->HIGH while toggle OFF stays MODERATE — the `MODERATE, judge, True` case's
    assertion failed (`('HIGH', 'composite', True) != ('MODERATE', 'judge', True)`).
    Restored; verified by hand before committing."""
    for base_tier, base_auth, base_over in [
        ("HIGH", "floor", False),
        ("MODERATE", "judge", True),
        ("none", "fallback", True),
    ]:
        for toggle_val in (True, False):
            async def _toggle(v=toggle_val):
                return v
            monkeypatch.setattr(db, "get_composite_authority_enabled", _toggle)
            r = {"ticker": "T", "alert_date": "2026-09-19"}
            result = _run(ep._apply_composite_authority(r, base_tier, base_auth, base_over))
            assert result == (base_tier, base_auth, base_over)


# ─── (4) forward-compat: the rail still composes once an axis registers ────────────────


def test_registering_an_axis_still_composes_no_rail_rebuild_needed(monkeypatch):
    """WOULD-FAIL-IF guard: '...or #331 would have to rebuild the rail.' Proves #331's
    entire integration is `_COMPOSITE_AXIS_CREDIT_SOURCES.append(fn)` — nothing else in
    `_apply_composite_authority` needs to change for a registered axis to compose,
    trace, and audit-log exactly as the retired theme axis did.

    MUTATION: hardcoded `return new_tier, authority, do_override` as the first line of
    `_apply_composite_authority` (unconditional early-return) — this test's `result`
    assertion failed (`('MODERATE', 'judge', True) != ('HIGH', 'composite', True)`)
    because nothing ever composes. Restored; verified by hand before committing."""
    async def _fake_gap_axis(r):
        return {"axis": "gap", "credit_steps": 1, "marker": "aligned", "reason": "test"}

    monkeypatch.setattr(ep, "_COMPOSITE_AXIS_CREDIT_SOURCES", [_fake_gap_axis])

    async def _toggle_true():
        return True
    monkeypatch.setattr(db, "get_composite_authority_enabled", _toggle_true)

    audit_calls = []

    async def _fake_audit(*a, **k):
        audit_calls.append((a, k))
    monkeypatch.setattr(ep, "log_audit_event", _fake_audit)

    r = {"ticker": "ABCD", "alert_date": "2026-09-19"}
    result = _run(ep._apply_composite_authority(r, "MODERATE", "judge", True))

    assert result == ("HIGH", "composite", True)
    assert r["composite_trace"]["final_tier"] == "HIGH"
    assert r["composite_trace"]["credits"][0]["axis"] == "gap"
    assert audit_calls and audit_calls[0][0][0] == "composite_axis_composed"


def test_registered_axis_returning_none_is_still_a_no_op(monkeypatch):
    """An axis registered but uncomputable for this candidate (None, same contract the
    retired theme function used) must not move the tier — mirrors the old
    'credit is not None' guard, now applied across the whole gathered list.

    MUTATION: shares the exact mutation from the zero-axes-registered tests above
    (remove both the `if not _COMPOSITE_AXIS_CREDIT_SOURCES` and `if not credits`
    no-op guards, so `resolve_composite_tier` is called unconditionally) — credits
    ends up `[]` here too (the one registered axis returns None), so `calls` becomes
    non-empty and this test's `calls == []` assertion fails identically. Verified as
    part of that same combined mutation run; see this file's git history / the commit
    message for the exact before/after pytest output (3 failed / 4 passed, this test
    among the 3)."""
    async def _uncomputable_axis(r):
        return None

    monkeypatch.setattr(ep, "_COMPOSITE_AXIS_CREDIT_SOURCES", [_uncomputable_axis])

    async def _toggle_true():
        return True
    monkeypatch.setattr(db, "get_composite_authority_enabled", _toggle_true)

    calls = _spy_resolve_composite_tier(monkeypatch)

    r = {"ticker": "ABCD", "alert_date": "2026-09-19"}
    result = _run(ep._apply_composite_authority(r, "MODERATE", "judge", True))

    assert result == ("MODERATE", "judge", True)
    assert calls == [], "an all-None credit gather must not reach the composer either"
