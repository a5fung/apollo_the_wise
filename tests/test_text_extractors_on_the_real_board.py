"""Every PLAN.md text rule, run over EVERY open task, every suite run.

WHY THIS FILE EXISTS (operator 2026-09-11: *"can you prevent these issues going forward?"*).

Three defects in two days, all in the same place and all the same shape — a regex that captures
past the end of the thing it is extracting:

- 2026-09-10 · `close_bar_for` matched the RAW line, so a DoD followed by an `[ok:...]` rebump tag
  swallowed the tag. **12 of 67 open lines.** The close gate could then be satisfied by quoting
  rebump history — including on #540, the task whose mishandled close is the reason it exists.
- 2026-09-11 · the same function's stop set was missing `⚖`, the marker this repo uses for the
  scope / THE-LINE sentence, which sits directly after a DoD more often than anything else.
  **15 of 64 open lines.** A close could have quoted a THE-LINE caveat as its criterion.
- 2026-09-11 · #471 had been closed against a sentence that is no clause of its own DoD, an hour
  before the close gate shipped. Nothing re-read the ledger afterwards.

**Every one was found by running the extractor over the WHOLE BOARD and looking at the output** —
never by reading the regex, and never by a unit test on a fixture. A fixture proves the rule works
on the case its author imagined; the board is the population it actually runs on, and it is 65
lines of adversarial real text written over four months.

So this file is not a fifth gate. It is the population check, made automatic: the properties below
hold for all open tasks, and any new extractor gets a row here rather than its own gate.
"""
import re

import pytest

from scripts.check_plan import (
    PLAN,
    _norm,
    _verify_claim_body,
    close_bar_for,
    parse,
    verify_is_absence_only,
)

# Markers that START A NEW THOUGHT in a PLAN line. Nothing extracted as a task's own criterion may
# contain one: if it does, the capture ran past the end of the criterion into commentary.
_SECTION_MARKERS = ("▶", ">>", "⚠", "✅", "⛔", "⚖", "➕", "📌", "🔴", "🔑", "📉", "🔎", "⏱", "📊", "🚨")
# Meta-commentary brackets: a PAST rebump / sweep decision, never a live statement of the criterion.
_META_TAG = re.compile(r"\[(?:ok|blocked|swept|revalidated):", re.I)


@pytest.fixture(scope="module")
def board():
    tasks = parse(PLAN.read_text(encoding="utf-8"))[0]
    assert len(tasks) > 20, "the board did not parse — every assertion below would be vacuous"
    return tasks


def test_no_extracted_bar_runs_past_a_section_marker(board):
    """THE 2026-09-10 AND 2026-09-11 DEFECTS, both of them, in one assertion."""
    bad = []
    for t in board:
        got = close_bar_for(t["title"])
        if got and any(m in got[1] for m in _SECTION_MARKERS):
            hit = next(m for m in _SECTION_MARKERS if m in got[1])
            bad.append(f"#{t['id']} (past {hit!r})")
    assert not bad, ("a task's extracted criterion ran into commentary — add the marker to "
                     f"`_BAR_END`: {bad}")


def test_no_extracted_bar_contains_a_rebump_tag(board):
    """`[ok:]` prose is commentary about a past date change, never the task's own criterion."""
    bad = [t["id"] for t in board
           if (got := close_bar_for(t["title"])) and _META_TAG.search(got[1])]
    assert not bad, f"bars bleeding into rebump commentary: {bad}"


def test_every_open_task_states_a_criterion(board):
    """`_dod_required_gate`'s promise, asserted over the population rather than at commit time."""
    missing = [t["id"] for t in board if close_bar_for(t["title"]) is None]
    assert not missing, (f"tasks with no DoD / VERIFY-LIVE / VERIFY the close gate could use: "
                         f"{missing}")


def test_no_extracted_bar_swallows_the_whole_line(board):
    """A criterion is a sentence or two. One that is most of the line has stopped being a
    criterion and is just the task text — which would make `close_bar_matches` accept anything
    written anywhere in the line."""
    bad = []
    for t in board:
        got = close_bar_for(t["title"])
        if not got:
            continue
        line_words = len(_norm(t["title"]).split())
        bar_words = len(_norm(got[1]).split())
        if line_words > 80 and bar_words > 0.5 * line_words:
            bad.append(f"#{t['id']} ({bar_words}/{line_words} words)")
    assert not bad, f"the extracted criterion is most of the whole line: {bad}"


def test_the_meta_tag_strip_never_empties_a_line(board):
    """`_verify_claim_body` is the shared substrate; if it ate a whole line, every gate that
    reads it would silently see nothing — the unfireable-check shape, one layer down."""
    bad = [t["id"] for t in board if not _verify_claim_body(t["title"]).strip()]
    assert not bad, f"the meta-tag strip emptied these lines: {bad}"


def test_no_deployed_task_rests_on_an_absence_alone(board):
    """`_absence_only_verify_gate` fires at commit time on CHANGED lines only. This is the same
    question asked of every deployed line on the board, so an old one cannot sit there unasked."""
    bad = []
    for t in board:
        if t["status"] != "deployed":
            continue
        got = close_bar_for(t["title"])
        if got and verify_is_absence_only(got[1]) and "WOULD-FAIL-IF" not in t["title"]:
            bad.append(t["id"])
    assert not bad, (f"deployed tasks whose check a BROKEN system would also pass, with no "
                     f"`WOULD-FAIL-IF:`: {bad}")
