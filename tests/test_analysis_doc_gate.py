"""The analysis-doc gate must reject drift WITHOUT rejecting correct work."""
from __future__ import annotations


def test_numbered_headings_are_accepted():
    """A numbered heading is ordinary markdown. The gate used to require the section title to
    follow the #s directly, so `## 4. What this does not answer` was rejected on a doc that HAD
    the section (2026-09-01, the #482 re-read). A gate that rejects correct work teaches people
    to --no-verify, which is worse than the drift it exists to stop.

    MUTATION TARGET: dropping the optional numeric prefix from _LIMITS / _METHOD."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("cad", "scripts/check_analysis_doc.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    for heading in ("## What this does not answer",
                    "## 4. What this does not answer",
                    "### 12) What this does not answer",
                    "## IV. Limits"):
        assert m._LIMITS.search(heading), f"limits heading rejected: {heading!r}"
    for heading in ("## Method / population", "## 2. Method / population"):
        assert m._METHOD.search(heading), f"method heading rejected: {heading!r}"

    assert not m._LIMITS.search("## What this answers"), (
        "the matcher must not have gone so loose it accepts the opposite section")
