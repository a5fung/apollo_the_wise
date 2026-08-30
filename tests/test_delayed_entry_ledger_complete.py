"""Every delayed-entry document is referenced from the context ledger.

WHY THIS TEST EXISTS
Operator, 2026-08-29: "i don't want delay entry to be re-discussed everytime with no context,
make sure everything is saved 100%, history, convo, context and linked everywhere we have delay
entries, all tasks, etc. and whatever finding when we're done."

The failure that produced it: two cards ran on delayed entry with no context loaded and returned
his own methodology restated back to him. The context existed the whole time — the setup SSoT,
the pivot principles, the #562 study — spread across a dozen files with nothing tying them
together, so "read the context" meant knowing which twelve files to open. It is now one ledger
in docs/setups/delayed_ep_reentry.md, and this test keeps it complete.

A ledger only works while it is current. Prose intentions do not survive here — the burndown,
verify-live, PLAN.md and the report format all had to become gates before they held, for the
same reason. So: a new delayed-entry analysis or design document that the ledger does not
reference FAILS the build, and the fix is to add the row rather than to silence the test.

WHAT IT DOES NOT CHECK: whether the ledger's summary of a document is ACCURATE. That is not
decidable from the text. This guarantees a finding is linked, never that it is well described.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_LEDGER = _REPO / "docs" / "setups" / "delayed_ep_reentry.md"

# Directories whose delayed-entry documents must appear in the ledger.
_SCANNED = ("docs/analysis", "docs/design")

# A filename is delayed-entry work if it matches one of these. Deliberately NARROW and
# filename-only: a content grep for "delayed" sweeps in delayed-DATA and delayed-price work,
# which is a different subject entirely and would make this test fire on unrelated files —
# the quickest way to get a guard switched off.
_PATTERNS = (
    re.compile(r"delayed_e", re.I),        # delayed_entry_*, delayed_ep_*
    re.compile(r"pivot_ladder", re.I),
    re.compile(r"pivot_proximity", re.I),
    re.compile(r"mnts_delayed", re.I),
    re.compile(r"conversion_rehearsal", re.I),
)

# Documents deliberately NOT given their own ledger row, each with its reason. This is the
# escape hatch: an unexplained entry defeats the test as surely as deleting it.
_EXEMPT: dict[str, str] = {}


def _delayed_entry_docs() -> list[Path]:
    found: list[Path] = []
    for rel in _SCANNED:
        d = _REPO / rel
        if not d.is_dir():
            continue
        for path in sorted(d.iterdir()):
            if path.suffix.lower() not in {".md", ".txt"}:
                continue
            if any(p.search(path.name) for p in _PATTERNS):
                found.append(path)
    return found


def test_ledger_exists_and_is_the_hub() -> None:
    assert _LEDGER.is_file(), f"the delayed-entry SSoT is missing: {_LEDGER}"
    text = _LEDGER.read_text(encoding="utf-8")
    assert "THE CONTEXT LEDGER" in text, (
        "docs/setups/delayed_ep_reentry.md lost its CONTEXT LEDGER section. That section is the "
        "one place carrying the goal, the operator's rulings and every study — removing it "
        "re-creates the 2026-08-29 failure where the context existed but nobody could find it."
    )


def test_every_delayed_entry_document_is_in_the_ledger() -> None:
    docs = _delayed_entry_docs()
    assert docs, "found no delayed-entry documents at all — the patterns have probably rotted"

    text = _LEDGER.read_text(encoding="utf-8")
    missing = [d for d in docs if d.name not in _EXEMPT and d.name not in text]
    assert not missing, (
        "delayed-entry document(s) not referenced from the context ledger in "
        "docs/setups/delayed_ep_reentry.md:\n  "
        + "\n  ".join(str(d.relative_to(_REPO)) for d in missing)
        + "\n\nAdd a row to the ledger's study table saying what the document ESTABLISHED — not "
          "what it was about. An orphaned finding is how this context was lost the first time "
          "(operator 2026-08-29: \"make sure everything is saved 100%\"). If a document "
          "genuinely does not belong, add it to _EXEMPT here WITH its reason."
    )


def test_the_operator_rulings_survive() -> None:
    """The rulings are the part that kept getting re-derived. Pin the load-bearing ones."""
    text = _LEDGER.read_text(encoding="utf-8")
    for phrase, why in [
        ('NEAR" IS A BEHAVIOUR',
         "the 2026-08-29 ruling that 'near' is deceleration/cessation/consolidation/turn, "
         "not a percentage — it replaces the +/-0.5xADR proximity test"),
        ("THE PIVOT IS THE FILTER",
         "the ruling that the behaviour triggers and the pivot only qualifies it"),
        ("day-1 construct",
         "the ruling that an opening range does not transfer to a delayed entry"),
        ("character",
         "the 2026-06-11 principle that the right pivot differs per stock"),
    ]:
        assert phrase in text, f"the ledger lost a load-bearing operator ruling: {why}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
