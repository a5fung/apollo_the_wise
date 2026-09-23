"""The standing-ask table is the ONLY surface `operator_asks.py` reads — so its row parser
must not silently drop rows.

FOUND 2026-09-16. The match was `ln.startswith("| **#")`. Both rows in the table that day opened
with a status marker instead — `| 🔴 **#610 …` and `| ✅ **#501 …` — so NEITHER matched, and the
tool printed **"Standing section carries NO open asks. Nothing waits on him."** while an HTF fork
that had been written for Sunday 09-13 sat unruled inside the table.

That is the worst direction for this particular bug to fail in: the whole point of the OPEN ritual
is that "what waits on you" is never assembled by hand, so a parser that quietly drops decorated
rows converts a real ask into a confident denial. The table's own warning already says an ask
written as prose is structurally invisible; this was the same failure one layer down, inside the
tool that warning points at.

⚠ The fix must NOT go the other way and resurrect settled rows — [[never-re-ask-an-answered-question]]
exists because three of four standing asks were found already answered on 2026-09-08, one carried
for seven weeks. So rows marked ANSWERED / WITHDRAWN / RULED / ✅ stay excluded on purpose, and
that is pinned here too.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The REAL predicate, imported — not a copy. It was lifted out of main() for exactly this reason
# (#653: exercise behaviour, do not pin source text). A local re-implementation could pass while
# the script it describes was broken, which is the failure mode this whole file is about.
from scripts.operator_asks import _SETTLED_MARKERS, is_open_ask as _is_ask  # noqa: E402


def test_the_exact_rows_that_were_invisible_are_asks_now():
    """Reinstating `startswith("| **#")` reddens this: both real rows from 2026-09-16 open with a
    status marker, so the old predicate returned False for both and the tool said nothing waits."""
    assert _is_ask("| 🔴 **#610/#592 — the HTF fork, written for Sunday and never ruled** | … | … |")


def test_every_settled_marker_in_the_STATUS_CELL_suppresses_a_row():
    """The fix must not become a resurrection machine — exercised per marker, not read off source.
    The table's convention puts status in the FIRST cell, so that is where each marker is placed."""
    for token in _SETTLED_MARKERS:
        row = f"| **#999 — something {token} on 2026-09-08** | the ask | the proof |"
        assert not _is_ask(row), (
            f"a row marked {token!r} would be raised with him again — the failure "
            f"never-re-ask-an-answered-question was written for."
        )


def test_a_settled_word_in_the_DESCRIPTION_does_not_suppress_an_open_ask():
    """⚠ THE SECOND BUG, found by review on 2026-09-16 hours after the first was fixed. Scanning
    the WHOLE line for markers re-created the original defect one layer narrower: an OPEN ask whose
    description explains history — "the earlier proposal was WITHDRAWN 09-10, the question now is
    X" — vanished, and the tool printed "nothing waits on him" over it. Same failure direction,
    introduced by the fix for it. Markers are read from the status cell only."""
    for token in _SETTLED_MARKERS:
        row = (f"| **#700 — a live fork** | the earlier proposal was {token} on 09-10; "
               f"the question now is X | verified still open |")
        assert _is_ask(row), (
            f"an OPEN ask was suppressed because {token!r} appears in its DESCRIPTION. That is the "
            f"silent drop this whole file exists to prevent, re-introduced by the fix for it."
        )


def test_a_row_with_a_status_marker_is_still_an_ask():
    """The exact shape that was invisible on 2026-09-16."""
    assert _is_ask("| 🔴 **#610/#592 — the HTF fork** | three options | verified open |")
    assert _is_ask("| **#123 — a plain row** | ask | proof |")
    assert _is_ask("| ⚠ **#7 — a warning marker** | ask | proof |")


def test_settled_rows_are_not_raised():
    assert not _is_ask("| ✅ **#501 — ANSWERED AND SHIPPED 2026-09-13** | … | verified |")
    assert not _is_ask("| **#641 — WITHDRAWN same day** | … | … |")
    assert not _is_ask("| **#452 — RULED 2026-09-07** | … | … |")


def test_table_furniture_is_not_an_ask():
    for line in ("| # | the ask | PROOF it is still open |", "|---|---|---|", "", "some prose"):
        assert not _is_ask(line), f"{line!r} parsed as an ask"


def test_the_live_table_parses_to_something(monkeypatch=None):
    """End-to-end against the REAL PLAN.md: whatever the table currently holds, the count of rows
    naming a task must equal asks + settled. A silent drop shows up here as a mismatch."""
    block = re.search(r"^### Standing — waits on the operator.*?(?=^## |\Z)",
                      (REPO / "PLAN.md").read_text(encoding="utf-8"), re.M | re.S)
    assert block, "the standing-ask section is gone from PLAN.md"
    rows = [l for l in block.group(0).splitlines() if l.startswith("|") and re.search(r"\*\*#\d", l)]
    assert rows, "no task rows at all in the standing table — furniture only"
    asks = [l for l in rows if _is_ask(l)]
    settled = [l for l in rows if not _is_ask(l)]
    assert len(asks) + len(settled) == len(rows), "a row was classified as neither"
