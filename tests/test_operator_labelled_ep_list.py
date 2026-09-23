"""The operator-labelled EP list, the shared identity module, and the fixture must not drift apart.

He asked for one findable list of the EPs he named himself. A hand-maintained doc beside a
machine-readable fixture rots by default — BFLY was labelled 2026-06-19 and never reached the
fixture at all, which is exactly the failure this guards. 2026-09-07 added a THIRD surface,
`shared/operator_labelled_eps.py` (the identity `agents/` code — which cannot import `tests/` —
actually checks against), so this now pins doc <-> shared module <-> fixture, three ways.
"""
import re

from shared.operator_labelled_eps import ACKNOWLEDGED_DOWNGRADES, OPERATOR_LABELLED_EPS

DOC = "docs/methodology/operator_labelled_eps.md"


def _doc_tickers() -> set:
    with open(DOC, encoding="utf-8") as fh:
        body = fh.read()
    table = body[body.index("## The list"):body.index("## What the list says")]
    return set(re.findall(r"^\|\s*\*\*([A-Z]{1,5})\*\*\s*\|", table, re.MULTILINE))


def _doc_identities() -> set:
    """(ticker, alert_date) pairs from the doc table's first two columns."""
    with open(DOC, encoding="utf-8") as fh:
        body = fh.read()
    table = body[body.index("## The list"):body.index("## What the list says")]
    return set(re.findall(
        r"^\|\s*\*\*([A-Z]{1,5})\*\*\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|", table, re.MULTILINE
    ))


def _fixture_tickers() -> set:
    from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS
    return {m.ticker for m in MUST_NOT_MISS if m.label_source == "operator"}


def _fixture_identities() -> set:
    from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS
    return {(m.ticker, m.alert_date) for m in MUST_NOT_MISS if m.label_source == "operator"}


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


# ── 2026-09-07: the shared identity module joins the sync ─────────────────────────────────────


def test_the_shared_module_and_the_doc_hold_the_same_identities():
    """`shared/operator_labelled_eps.py` is the identity `agents/` code imports (it cannot import
    `tests/fixtures/`) — it must carry the exact same (ticker, alert_date) pairs as the doc, not
    merely the same tickers. A date typo there would make the downgrade invariant check the WRONG
    alert_date and silently never match a real row.

    MUTATION TARGET: editing OPERATOR_LABELLED_EPS's MRNA date to '2026-08-18' (one day off from
    the doc's '2026-08-19') flips this red even though the ticker set alone still agrees.
    """
    doc, shared = _doc_identities(), {(ep.ticker, ep.alert_date) for ep in OPERATOR_LABELLED_EPS}
    assert doc == shared, (
        "shared/operator_labelled_eps.py has drifted from the doc.\n"
        f"  in the doc but not the shared module: {sorted(doc - shared)}\n"
        f"  in the shared module but not the doc: {sorted(shared - doc)}\n"
    )


def test_the_fixture_and_the_shared_module_agree():
    """The fixture's operator-named members must source their identity FROM the shared module,
    not a second hand-typed literal. Comparing full (ticker, alert_date) identities catches a
    drifted DATE that `test_the_list_and_the_fixture_hold_the_same_names` (ticker-only, vs the
    doc) would miss.

    MUTATION TARGET: hand-typing a fixture member's alert_date instead of sourcing it via
    `_op(ticker).alert_date` (e.g. HTFL literal '2026-08-15', one day off the shared module's
    '2026-08-14') flips this red.
    """
    fix = _fixture_identities()
    shared = {(ep.ticker, ep.alert_date) for ep in OPERATOR_LABELLED_EPS}
    assert fix == shared, (
        "the fixture's operator-named identities have drifted from the shared module.\n"
        f"  in the shared module but not the fixture: {sorted(shared - fix)}\n"
        f"  in the fixture but not the shared module: {sorted(fix - shared)}\n"
    )


def test_acknowledged_downgrades_only_reference_real_operator_labelled_eps():
    """`ACKNOWLEDGED_DOWNGRADES` silences an alarm — a key for a (ticker, alert_date) that is not
    actually on `OPERATOR_LABELLED_EPS` would be dead weight at best and, if a ticker/date typo
    ever diverged from the real list, would silently fail to silence the row it was meant to.

    MUTATION TARGET: adding an acknowledged-set entry keyed to a ticker/date not on the list
    (e.g. a typo'd alert_date) flips this red.
    """
    identities = {(ep.ticker, ep.alert_date) for ep in OPERATOR_LABELLED_EPS}
    for ticker, alert_date, event_type in ACKNOWLEDGED_DOWNGRADES:
        assert (ticker, alert_date) in identities, (
            f"ACKNOWLEDGED_DOWNGRADES has an orphaned key {(ticker, alert_date, event_type)} — "
            "not on OPERATOR_LABELLED_EPS at all"
        )


def test_acknowledged_downgrades_carry_a_named_reason_and_owner():
    """The module docstring bans 'we looked and it's fine' — every entry must carry a non-trivial
    reason string and an owning task/doc reference, not an empty or placeholder value.

    MUTATION TARGET: an acknowledged-set entry with `owner=""` or a one-word `reason` flips this.
    """
    for key, ack in ACKNOWLEDGED_DOWNGRADES.items():
        assert len(ack.reason) > 20, f"{key}: reason too thin to be a real root cause"
        assert ack.owner.strip(), f"{key}: owner is empty — nothing owns this silenced alarm"
