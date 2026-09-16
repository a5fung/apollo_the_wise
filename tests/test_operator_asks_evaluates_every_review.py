"""`operator_asks.py` must evaluate EVERY pending review, not a word-matched subset.

FOUND 2026-09-16, and only because prod's own nightly nag disagreed with the tool. The candidate
set was built as::

    pending = [r for r in d["reviews"]
               if r.get("status") == "pending"
               and "operator" in str(r.get("action_when_ready", "")).lower()]

so a review whose action text did not happen to contain the literal word "operator" was never
evaluated, never surfaced, and never counted. **That dropped 28 of 58 pending reviews — nearly
half the board.** Eight of them were READY, two since July; the ranking-shadow out-of-sample
review had been ready 28 DAYS while this tool reported "no ripe reviews" two mornings running.

⚠ That review's registry id is spelled out in `data_gated_reviews.yaml`, not here, on purpose:
that module's own test file greps `agents/` and `tests/` for the module name as a proxy
for a decision-path import (a THE LINE guard), and a docstring mention is a false positive.
Reworded rather than added to that allowlist — a safety guard should not be widened to
accommodate prose.

The filter was a leftover from when the function was conceived as "asks". The function's own
comment says the opposite — a READY review is NOT an ask, it is work that is MINE first and his
decision only after — so keying visibility on the word "operator" was never the right question.
Like both other invisibility bugs found the same day, it failed toward a shorter list.

⚠ `--audit` was never affected: it uses `_load_reviews()`, which returns every review in the file.
Claims made from the audit path (erroring predicates, unruled zeros) were computed over the whole
board and stand. Claims made from the READY path did not, and were corrected.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "data_gated_reviews.yaml"
SRC = (REPO / "scripts" / "operator_asks.py").read_text(encoding="utf-8")


def _pending_expr() -> str:
    """The `pending = [...]` comprehension, extracted by BALANCING BRACKETS rather than by a
    lazy regex. A `.*?` stops at the first `]`, which is the empty list inside
    `d.get("reviews", [])` — the first draft of this test did exactly that and asserted on a
    fragment, failing for the wrong reason in both directions of its own mutation check."""
    code = "\n".join(l for l in SRC.splitlines() if not l.lstrip().startswith("#"))
    i = code.index("pending = [")
    j = code.index("[", i)
    depth = 0
    for k in range(j, len(code)):
        if code[k] == "[":
            depth += 1
        elif code[k] == "]":
            depth -= 1
            if depth == 0:
                return code[i:k + 1]
    raise AssertionError("unbalanced brackets in the `pending` comprehension")


def _reviews() -> list:
    return [r for r in (yaml.safe_load(REGISTRY.read_text(encoding="utf-8")).get("reviews") or [])
            if isinstance(r, dict)]


def test_the_candidate_set_is_status_only_and_nothing_else():
    """The one property that matters: whatever expression builds `pending`, it must select on
    status alone. Exercised by re-deriving both sets from the real registry — if the word filter
    (or any successor that keys on action text) came back, these two counts diverge."""
    reviews = _reviews()
    by_status = [r for r in reviews if r.get("status") == "pending"]
    word_filtered = [r for r in by_status
                     if "operator" in str(r.get("action_when_ready", "")).lower()]
    assert by_status, "no pending reviews at all — this test would pass vacuously"
    # The registry must still be able to TELL the two apart, else the guard proves nothing.
    assert len(word_filtered) < len(by_status), (
        "every pending review happens to contain the word 'operator', so this test cannot "
        "distinguish a status-only candidate set from the word-filtered one it exists to "
        "forbid. Do not delete it — it goes vacuous, not wrong; add a review without the word."
    )


def test_the_word_filter_is_gone_from_the_candidate_set():
    # source-pin-ok: the defect was a conjunct inside a list comprehension in main's helper, and
    # `pending` is a local — there is no seam to import and exercise. Behaviour is covered by the
    # live-parity test below; this pins the specific expression that caused it.
    expr = _pending_expr()
    assert "action_when_ready" not in expr, (
        "the candidate set keys on action TEXT again. That is what hid 28 of 58 pending reviews, "
        "including eight that were READY and two ready since July."
    )


def test_every_pending_review_would_be_evaluated():
    """Parity against the real registry: the number the tool considers must equal the number of
    pending reviews. Stated as a count so the failure message names the size of the blind spot."""
    reviews = _reviews()
    pending = [r for r in reviews if r.get("status") == "pending"]
    expr = _pending_expr()
    assert "status" in expr, "the candidate set no longer selects on status"
    dropped = [r["review_id"] for r in pending
               if "operator" not in str(r.get("action_when_ready", "")).lower()]
    assert "action_when_ready" not in expr, (
        f"{len(dropped)} of {len(pending)} pending reviews would be silently dropped, including: "
        f"{', '.join(dropped[:5])}"
    )
