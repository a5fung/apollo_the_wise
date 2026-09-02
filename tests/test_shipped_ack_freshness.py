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


def test_stale_blocker_reads_the_CURRENT_tag_not_the_whole_history():
    """A long-lived task carries its whole block history inline. Reading EVERY
    `[blocked:...]` tag makes a superseded reference fire forever — #353 was re-pointed off
    the closed #327 on 2026-09-01 and kept flagging, because an August tag still named #327
    as history. A surface that cries wolf gets ignored, which is worse than not having it.

    The rule: only the LAST blocked tag is the current claim.

    MUTATION TARGET: scanning `t["title"]` wholesale for `blocked:...#N` again — which is
    exactly what the pre-fix implementation did, and it passes every other test here."""
    from scripts.check_plan import stale_blockers

    live = [{"id": 400, "status": "pending", "title": "still open"}]
    superseded = {
        "id": 353, "status": "blocked",
        "title": ("[blocked:#999 the old gate, closed since] later re-pointed "
                  "[blocked:#400 the real one revalidated:2026-09-01]"),
    }
    assert stale_blockers([*live, superseded]) == [], (
        "the CURRENT tag names a live task; a dead reference in an OLDER tag is history "
        "and must not keep the surface firing")

    still_stale = {
        "id": 354, "status": "blocked",
        "title": "[blocked:#400 fine] then [blocked:#998 this one really is gone]",
    }
    hits = stale_blockers([*live, still_stale])
    assert len(hits) == 1 and hits[0][1] == ["998"], (
        "a dead reference in the CURRENT tag must still fire — the fix narrows which tag "
        "is read, it does not weaken the check")


def test_two_blockers_in_one_tag_are_both_checked():
    """Narrowing to the last TAG must not narrow to the last REFERENCE: a task legitimately
    blocked on two things names both in one tag, and either going stale matters."""
    from scripts.check_plan import stale_blockers

    live = [{"id": 400, "status": "pending", "title": "open"}]
    t = {"id": 355, "status": "blocked", "title": "[blocked:#400 and #997 together]"}
    hits = stale_blockers([*live, t])
    assert len(hits) == 1 and hits[0][1] == ["997"]


def test_day_movement_counts_SETS_not_diff_lines():
    """Asked what a day achieved, I listed nine closes and four were the previous day's. The
    operator caught it: "you show us have 9 real closes but task closed is only 1". The board's
    history is in git and the answer is decidable, so it should never have been prose.

    The subtlety this pins: PLAN lines are EDITED constantly (a note appended to a task removes
    and re-adds the line), so a naive +/- line diff counts an edit as a close-and-reopen. Comparing
    id SETS is what makes it correct.

    MUTATION TARGET: reverting to a +/- line diff, which reads plausible and inflates both counts.
    """
    import inspect

    from scripts.check_plan import day_movement
    src = inspect.getsource(day_movement)
    assert "was - now" in src and "now - was" in src, (
        "movement must be a set difference over task ids, not a diff of added/removed lines")
    assert "rev-list" in src and "--before=" in src, (
        "the comparison point must be the last commit BEFORE the operator's PT day began")
    assert "_OPERATOR_TZ" in src, "the day boundary is the operator's PT day, never UTC"
