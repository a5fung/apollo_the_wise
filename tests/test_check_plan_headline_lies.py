"""A `deployed` task must not open by saying it is not deployed.

FOUND 2026-09-17. Three tasks carried a headline reading "BUILT BUT NOT DEPLOYED" while all three
had shipped — #658 (deployed 09-14, its $1 backtest already run), #654 (09-13), #630 (09-10). Each
had the truth recorded further down its line, and **#630's tail even carried an explicit 2026-09-11
correction** saying the headline sentence was *"STALE and was misleading a reader (me, this
morning)"*. The headline was left lying anyway, and it misled the same reader again on 2026-09-17 —
a second time, from a line that already knew about itself.

That is the daily-waste leak the `deployed` status was invented for (operator 2026-07-18: built
tasks "sat in_progress for weeks wearing a to-build headline and got re-checked/re-built"). The
STATUS field was fixed then and works; the HEADLINE was not, so the leak moved one field left.

⚠ The gate must tolerate a headline QUOTING the wording it replaces — all three corrections do
exactly that, and a naive match would flag every fix as a fresh violation. Both directions are
pinned below, because a guard that cannot fail and a guard that always fires read identically from
a green suite.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from check_plan import _headline_lies_violations, _headline_of, parse  # noqa: E402


def _task(title: str, status: str = "deployed") -> dict:
    return {"id": 1, "line": 1, "status": status, "title": title}


# ── the three real headlines that shipped the bug ────────────────────────────────────────────────

REAL_PRE_FIX = [
    ("#658", "[b1] 🔴 **BOTH 2026-09-13 THEME CHANGES ARE BUILT AND ON `main` BUT NOT DEPLOYED — "
             "and the EP one has NEVER HAD ITS DECIDING BACKTEST RUN.** ▶ detail follows"),
    ("#654", "🟡 **THE FAILED-BREAKOUT TELEMETRY IS BUILT AND MERGED BUT NOT DEPLOYED — three "
             "columns that nothing in prod is writing yet.** ▶ detail follows"),
    ("#630", "**Two post-deploy corrections from the 09-08 advisor pass — built and suite-green, "
             "NOT deployed (the 21:15 ET window had 15 minutes left).** ▶ detail follows"),
]


def test_each_real_lying_headline_is_caught():
    for name, title in REAL_PRE_FIX:
        assert _headline_lies_violations([_task(title)]), (
            f"{name}'s real pre-fix headline was not caught — this is the exact text that misled a "
            f"reader on 2026-09-17."
        )


def test_a_correction_may_quote_the_wording_it_replaces():
    """⚠ THE HALF THAT MAKES THE GATE USABLE. Every fix for this bug names the old wording so the
    next reader knows what changed. If quoting it re-trips the gate, the only way to satisfy the
    gate is to delete the history — so the fix and the guard would be in direct conflict."""
    corrected = ('🟢 **DEPLOYED 09-14, both scopes, and the backtest has run.** ⚠ **HEADLINE '
                 'CORRECTED 2026-09-17: it read *"BUILT AND ON main BUT NOT DEPLOYED — and the EP '
                 'one has NEVER HAD ITS DECIDING BACKTEST RUN"*, false since 09-14.**')
    assert not _headline_lies_violations([_task(corrected)]), (
        "a corrected headline was flagged because it quotes the wording it replaced — the gate "
        "would force the fix to erase its own history"
    )


def test_the_tail_is_not_the_headline():
    """#630's tail carried the 2026-09-11 correction and the headline still lied. The gate reads
    the HEADLINE, so tail text must neither rescue a lying headline nor trip a true one."""
    assert not _headline_lies_violations([_task(
        "🟢 **DEPLOYED 09-10 and confirmed in the running image.** >> it was NOT deployed on 09-08"
    )]), "tail text tripped the gate — the headline is what a reader meets first"
    assert _headline_lies_violations([_task(
        "**Built and suite-green, NOT deployed.** >> CORRECTION: actually deployed 09-10"
    )]), "a lying headline was rescued by a correction buried in its tail — the 2026-09-11 failure"


def test_only_deployed_tasks_are_judged():
    """A `pending` or `in_progress` task saying 'not deployed' is telling the truth."""
    title = "**Built but NOT deployed — the window closed.** ▶ detail"
    for status in ("pending", "in_progress", "blocked"):
        assert not _headline_lies_violations([_task(title, status)]), (
            f"a {status} task was flagged for accurately saying it is not deployed"
        )
    assert _headline_lies_violations([_task(title, "deployed")])


def test_the_phrasings_that_actually_get_written():
    for phrase in ("NOT DEPLOYED", "not deployed", "not yet deployed", "never deployed"):
        assert _headline_lies_violations([_task(f"**Something — {phrase} yet.** ▶ x")]), phrase


def test_the_live_board_is_clean():
    """End-to-end against the REAL PLAN.md. Goes vacuous rather than wrong if the board empties."""
    tasks, _ = parse((REPO / "PLAN.md").read_text(encoding="utf-8"))
    assert [t for t in tasks if t["status"] == "deployed"], "no deployed tasks — test is vacuous"
    bad = _headline_lies_violations(tasks)
    assert not bad, f"lying headlines on the live board: {[t['id'] for t in bad]}"


def test_headline_extraction_stops_at_the_first_marker():
    assert "tail" not in _headline_of("**head** >> tail")
    assert "detail" not in _headline_of("**head** ▶ detail")
    assert "caveat" not in _headline_of("**head** ⚠ caveat")


def test_a_headline_that_OPENS_with_a_marker_is_still_checked():
    """⚠ THE HOLE, found by review on 2026-09-17 — the same day the gate shipped. `_headline_of`
    cut at the first marker using `i != -1`, so a line OPENING with ⚠ (or ▶, or >>) cut at index 0
    and returned an empty string. Empty text matches nothing, so the task passed by vacuity — a
    guard that cannot fire, which is the exact class this repo keeps building by accident."""
    for opener in ("⚠", "▶", ">>"):
        title = f"{opener} **Built and suite-green, NOT deployed.** ▶ detail follows"
        assert _headline_of(title).strip(), f"headline starting with {opener!r} extracted as empty"
        assert _headline_lies_violations([_task(title)]), (
            f"a lying headline opening with {opener!r} was not caught — it passed by vacuity"
        )
