"""The LIKELY-BUILT surface fired 9/9 false positives (2026-08-06) and could not stop.

`_DEPLOY_MARKER` asks "has this line EVER mentioned a deploy", not "is this headline lying". Task
lines accumulate `>>` updates forever, so a multi-part task that ships ONE piece matches for the
rest of its life. On 2026-08-06 all 9 flagged tasks were checked individually and all 9 were
already correctly classified — and three of them carried a PROSE note from the 07-31 sweep saying
"checked, classification is HONEST, no change", which a regex cannot see.

A surface at 9/9 noise is the failure mode the operator named on 07-18: it "got triaged as
housekeeping and ignored". The fix is a dated `swept:YYYY-MM-DD` marker, mirroring the
`revalidated:` idiom the stale-block gate already uses.

These tests pin the two ways that fix could go wrong:
  1. it stops suppressing when the marker ages out (otherwise it is a permanent mute), and
  2. a malformed or future date cannot be used to silence a line forever.
"""
from datetime import date, timedelta

import pytest

from scripts.check_plan import (
    _SWEPT,
    _DEPLOY_MARKER,
    _SWEEP_MAX_AGE,
    _sweep_is_fresh,
)

TODAY = date(2026, 8, 6)


def _line(marker: str = "") -> str:
    """A realistic flagged title: real deploy prose plus an optional sweep marker."""
    return ("HTF filter — SHIPPED + DEPLOYED 2026-07-24, verify-live pending. " + marker).strip()


def test_the_underlying_surface_still_flags_a_deploy_marker():
    """Guard the guard: if _DEPLOY_MARKER stops matching, suppression tests would pass
    vacuously while the surface silently detected nothing."""
    assert _DEPLOY_MARKER.search(_line())


def test_a_fresh_sweep_marker_suppresses():
    assert _sweep_is_fresh(_line("[swept:2026-08-06 — checked, honest]"), TODAY)


def test_a_marker_at_the_exact_age_limit_is_still_fresh():
    d = TODAY - timedelta(days=_SWEEP_MAX_AGE)
    assert _sweep_is_fresh(_line(f"[swept:{d.isoformat()}]"), TODAY)


def test_an_expired_marker_does_NOT_suppress():
    """The whole point of dating it — suppression must lapse so the line is re-checked."""
    d = TODAY - timedelta(days=_SWEEP_MAX_AGE + 1)
    assert not _sweep_is_fresh(_line(f"[swept:{d.isoformat()}]"), TODAY)


def test_no_marker_does_NOT_suppress():
    assert not _sweep_is_fresh(_line(), TODAY)


@pytest.mark.parametrize("bad", [
    "[swept:2026-13-45]",      # impossible date
    "[swept:not-a-date]",      # unparseable
    "[swept:26-08-06]",        # wrong format
    "[swept:]",                # empty
])
def test_a_malformed_date_cannot_silence_the_surface(bad):
    """A typo must fail OPEN (keep surfacing), never closed. Otherwise the easiest way to mute a
    task forever is to fat-finger the date, and nothing would ever report it."""
    assert not _sweep_is_fresh(_line(bad), TODAY)


def test_a_FUTURE_dated_marker_cannot_silence_the_surface():
    """Post-dating is the obvious way to buy permanent silence — `swept:2099-01-01` would
    otherwise suppress for 73 years. Rejected by the `0 <= age` bound."""
    assert not _sweep_is_fresh(_line("[swept:2099-01-01]"), TODAY)


def test_case_insensitive_marker():
    assert _sweep_is_fresh(_line("[SWEPT: 2026-08-06]"), TODAY)


def test_mutation_removing_the_age_bound_would_break_expiry():
    """Executable proof that test_an_expired_marker_does_NOT_suppress is load-bearing: a version
    that only checks 'is there a marker' suppresses an ancient sweep, which is the permanent-mute
    failure this whole mechanism exists to avoid."""
    ancient = _line("[swept:2020-01-01]")
    naive_would_suppress = bool(__import__("re").search(r"swept:", ancient, __import__("re").I))
    assert naive_would_suppress, "fixture no longer exercises the mutation"
    assert not _sweep_is_fresh(ancient, TODAY), "the real implementation must reject it"


def test_an_EDITED_line_invalidates_its_sweep_immediately():
    """The date alone answers the wrong question (advisor, 2026-08-06).

    A sweep asserts "I read THIS line and its status is honest". The moment the line gains a
    `>> SHIPPED` update that judgement is void — waiting out a 30-day timer would hide exactly
    the misclassification this surface is the board's only detector for. So the marker carries a
    fingerprint of the line it was made against.
    """
    from scripts.check_plan import sweep_fingerprint
    body = _line()
    fp = sweep_fingerprint(body)
    swept = f"{body} [swept:2026-08-06:{fp}]"
    assert _sweep_is_fresh(swept, TODAY), "an unchanged line should stay suppressed"

    edited = swept.replace("verify-live pending.", "verify-live pending. >> SHIPPED 08-07.")
    assert not _sweep_is_fresh(edited, TODAY), (
        "a line edited after its sweep must re-surface immediately, not in 30 days")


def test_a_marker_with_no_fingerprint_still_works_on_the_timer():
    """Backwards compatibility: date-only markers predate the fingerprint and must not all go
    stale at once, but they get no content protection — only the timer."""
    assert _sweep_is_fresh(_line("[swept:2026-08-06]"), TODAY)


def test_a_WRONG_fingerprint_does_not_suppress():
    assert not _sweep_is_fresh(_line("[swept:2026-08-06:dead]"), TODAY)


def test_fingerprint_ignores_the_marker_itself():
    """Otherwise the hash would have to hash itself — stamping would change what it stamped."""
    from scripts.check_plan import sweep_fingerprint
    body = _line()
    assert sweep_fingerprint(body) == sweep_fingerprint(f"{body} [swept:2026-08-06:abcd]")
    assert sweep_fingerprint(body) == sweep_fingerprint(f"{body} [swept:1999-01-01 — a note]")


def test_every_swept_marker_on_the_live_board_matches_its_line():
    """The markers actually written into PLAN.md must still be valid against their current
    content. A mismatch here means a swept line was edited without re-sweeping — which is the
    stale-judgement case, and the board would be quietly hiding it."""
    import pathlib
    from scripts.check_plan import _TASK, sweep_fingerprint
    bad = []
    for raw in pathlib.Path("PLAN.md").read_text(encoding="utf-8").splitlines():
        m = _TASK.match(raw)
        if not m or "swept:" not in raw:
            continue
        title = m.group(4)
        got = _SWEPT.search(title)
        if not got or not got.group(2):
            continue                       # date-only marker, covered by the timer test
        if got.group(2).lower() != sweep_fingerprint(title):
            bad.append(f"#{m.group(1)}: marker {got.group(2)} != content {sweep_fingerprint(title)}")
    assert not bad, ("swept markers no longer match their line — re-sweep or drop the marker:\n  "
                     + "\n  ".join(bad))


def test_every_swept_marker_on_the_live_board_is_parseable_and_not_future():
    """The markers actually written into PLAN.md must all work. A typo'd marker fails open, so
    this would not hide a task — but it WOULD mean a sweep someone believed they recorded is not
    recorded, which is worth failing the suite over."""
    import pathlib
    import re as _re
    txt = pathlib.Path("PLAN.md").read_text(encoding="utf-8")
    # Capture the DATE only — a marker may carry an optional `:hash` suffix, which is checked by
    # test_every_swept_marker_on_the_live_board_matches_its_line, not here.
    found = _re.findall(r"swept:\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[^\s\]:—]+)", txt, _re.I)
    assert found, "expected sweep markers on the board; if the sweep idiom is retired, delete this test"
    bad = []
    for raw in found:
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            bad.append(f"{raw!r} does not parse")
            continue
        if d > date.today():
            bad.append(f"{raw!r} is in the future")
    assert not bad, "unusable swept: markers on the board:\n  " + "\n  ".join(bad)
