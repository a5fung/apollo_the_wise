"""`[shipped-ack:]` recreated the pre-fix `swept:`/`revalidated:` shape a third time (2026-08-30
simplify review): presence-only — no date, no content fingerprint, no expiry. A shipped-ack
written once could mute SHIPPED-BUT-UNRECORDED for a task number FOREVER, including once
genuinely new, honestly-unshipped scope was filed under the same number — exactly the drift the
surface exists to catch.

Fix: `[shipped-ack:YYYY-MM-DD[:hash]]` now routes through the shared `_marker_is_fresh`
primitive — the SAME bounded-age + content-fingerprint contract `swept:` already has. These
tests pin the two ways a stale ack must stop suppressing, and guard that both markers actually
share the one primitive rather than each hand-rolling its own freshness check again.
"""
from datetime import date, timedelta

from scripts.check_plan import (
    _NOT_SHIPPED_CLAIM,
    _SHIPPED_ACK_MAX_AGE,
    _shipped_ack_is_fresh,
    shipped_ack_fingerprint,
)

TODAY = date(2026, 8, 30)


def _line(marker: str = "") -> str:
    """A realistic flagged title: a NOT-SHIPPED claim plus an optional shipped-ack marker."""
    return ("#331 — NOTHING SHIPPED, awaiting operator ruling. " + marker).strip()


def test_the_underlying_claim_pattern_still_matches():
    """Guard the guard: if _NOT_SHIPPED_CLAIM stops matching, the tests below would pass
    vacuously against a title the surface would never have looked at anyway."""
    assert _NOT_SHIPPED_CLAIM.search(_line())


def test_a_fresh_ack_suppresses():
    body = _line()
    fp = shipped_ack_fingerprint(body)
    assert _shipped_ack_is_fresh(f"{body} [shipped-ack:{TODAY.isoformat()}:{fp}]", TODAY)


def test_a_marker_at_the_exact_age_limit_is_still_fresh():
    d = TODAY - timedelta(days=_SHIPPED_ACK_MAX_AGE)
    body = _line()
    fp = shipped_ack_fingerprint(body)
    assert _shipped_ack_is_fresh(f"{body} [shipped-ack:{d.isoformat()}:{fp}]", TODAY)


def test_an_expired_ack_does_NOT_suppress():
    """MUTATION 1 — AGED OUT. The whole point of dating it: suppression must lapse so a task
    that has sat quietly for a month gets re-checked instead of muted forever."""
    d = TODAY - timedelta(days=_SHIPPED_ACK_MAX_AGE + 1)
    body = _line()
    fp = shipped_ack_fingerprint(body)
    assert not _shipped_ack_is_fresh(f"{body} [shipped-ack:{d.isoformat()}:{fp}]", TODAY)


def test_a_WRONG_fingerprint_does_not_suppress():
    """MUTATION 2 — WRONG FINGERPRINT. A hash that does not match the line's current content
    (as if copy-pasted from a different task, or hand-typed wrong) must not buy silence."""
    body = _line()
    assert not _shipped_ack_is_fresh(f"{body} [shipped-ack:{TODAY.isoformat()}:dead]", TODAY)


def test_a_FUTURE_dated_ack_cannot_silence_the_surface():
    body = _line()
    fp = shipped_ack_fingerprint(body)
    assert not _shipped_ack_is_fresh(f"{body} [shipped-ack:2099-01-01:{fp}]", TODAY)


def test_new_scope_added_under_the_same_number_invalidates_the_ack():
    """THE bug this fixes, end to end: new, honestly-unshipped scope filed under the SAME task
    number must re-surface immediately — an ack written about the old content must not cover
    content it never judged."""
    body = _line()
    fp = shipped_ack_fingerprint(body)
    acked = f"{body} [shipped-ack:{TODAY.isoformat()}:{fp}]"
    assert _shipped_ack_is_fresh(acked, TODAY)

    grown = acked.replace(
        "awaiting operator ruling.",
        "awaiting operator ruling. >> NEW SLICE: structure axis, NOT SHIPPED.")
    assert not _shipped_ack_is_fresh(grown, TODAY), (
        "editing the line after the ack must void it immediately, not after the timer runs out")


def test_mutation_a_presence_only_check_would_wrongly_keep_suppressing():
    """Executable proof the fingerprint/expiry checks are load-bearing: the PRE-FIX logic
    (bare `[shipped-ack:...]` presence, no date/hash) suppresses the expired-and-stale marker
    that the real implementation correctly un-suppresses."""
    import re as _re

    d = TODAY - timedelta(days=_SHIPPED_ACK_MAX_AGE + 1)
    body = _line()
    fp = shipped_ack_fingerprint(body)
    expired = f"{body} [shipped-ack:{d.isoformat()}:{fp}]"
    naive_presence_only = _re.compile(r"\[shipped-ack:[^\]]+\]", _re.I)
    assert naive_presence_only.search(expired), "fixture no longer exercises the mutation"
    assert not _shipped_ack_is_fresh(expired, TODAY), (
        "the real implementation must reject what the pre-fix logic accepted")


def test_the_surface_actually_uses_the_fresh_check():
    """Guard the guard: `shipped_but_unrecorded` must route the ack check through
    `_shipped_ack_is_fresh`, not a presence-only `_SHIPPED_ACK.search` inline — the exact
    regression this fix closes."""
    import inspect

    from scripts.check_plan import shipped_but_unrecorded
    src = inspect.getsource(shipped_but_unrecorded)
    assert "_shipped_ack_is_fresh" in src
    assert "_SHIPPED_ACK.search" not in src


def test_shared_primitive_used_by_both_markers():
    """swept: and shipped-ack: must both route through _marker_is_fresh — the whole point of
    generalising, so a fourth marker cannot recreate this bug a fourth time by hand-rolling its
    own copy of "is this judgement still good" again."""
    import inspect

    from scripts.check_plan import _shipped_ack_is_fresh, _sweep_is_fresh
    assert "_marker_is_fresh" in inspect.getsource(_sweep_is_fresh)
    assert "_marker_is_fresh" in inspect.getsource(_shipped_ack_is_fresh)


def test_the_live_board_markers_are_fresh():
    """The two markers this fix re-formed (#299, #335) must actually be fresh today — proof the
    re-form was done correctly, not just that the machinery works in the abstract. Uses the
    operator's PT day (the same clock check_plan.py itself uses), not the container's clock."""
    import pathlib
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from scripts.check_plan import _TASK
    today = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    hits = 0
    for raw in pathlib.Path("PLAN.md").read_text(encoding="utf-8").splitlines():
        m = _TASK.match(raw)
        if not m or "shipped-ack:" not in raw.lower():
            continue
        hits += 1
        assert _shipped_ack_is_fresh(m.group(4), today), (
            f"task #{m.group(1)}'s shipped-ack marker is not fresh against today's date")
    # Assert the INVARIANT (every marker on the board is fresh), not a COUNT. A hardcoded count
    # fails the moment anyone legitimately acknowledges another task — which happened within
    # minutes of this test being written, on #331 — and a test that fails on correct behaviour
    # gets deleted rather than fixed. `hits > 0` still proves the loop actually ran against real
    # board content rather than silently matching nothing.
    assert hits > 0, "no shipped-ack markers found on the board — the matcher has probably rotted"
