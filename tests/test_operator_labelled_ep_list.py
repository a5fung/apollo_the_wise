"""The operator-labelled EP list and the fixture must not drift apart.

He asked for one findable list of the EPs he named himself. A hand-maintained doc beside a
machine-readable fixture rots by default — BFLY was labelled 2026-06-19 and never reached the
fixture at all, which is exactly the failure this guards.
"""
import re

DOC = "docs/methodology/operator_labelled_eps.md"


def _doc_tickers() -> set:
    with open(DOC, encoding="utf-8") as fh:
        body = fh.read()
    table = body[body.index("## The list"):body.index("## What the list says")]
    return set(re.findall(r"^\|\s*\*\*([A-Z]{1,5})\*\*\s*\|", table, re.MULTILINE))


def _fixture_tickers() -> set:
    from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS
    return {m.ticker for m in MUST_NOT_MISS if m.label_source == "operator"}


def test_the_list_and_the_fixture_hold_the_same_names():
    doc, fix = _doc_tickers(), _fixture_tickers()
    assert doc == fix, (
        f"the operator-labelled EP list has drifted from the fixture.\n"
        f"  in {DOC} but not the fixture: {sorted(doc - fix)}\n"
        f"  in the fixture but not the doc: {sorted(fix - doc)}\n"
        "Both must be updated when he names an EP — see the doc's 'rule for adding one'."
    )


def test_the_list_is_not_empty():
    """Guard the guard: an empty parse would make the comparison above vacuous."""
    assert len(_doc_tickers()) >= 6, "the list parser found almost nothing — it is broken"


def test_every_row_records_what_our_system_did():
    """The list exists to show where each real EP was lost, not just to name them."""
    with open(DOC, encoding="utf-8") as fh:
        table = fh.read()
    table = table[table.index("## The list"):table.index("## What the list says")]
    for row in re.findall(r"^\|\s*\*\*[A-Z]{1,5}\*\*.*$", table, re.MULTILINE):
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert len(cells) == 5, f"row has {len(cells)} cells, expected 5: {row[:60]}"
        assert len(cells[4]) > 40, f"the 'what our system did' cell is too thin: {row[:60]}"
