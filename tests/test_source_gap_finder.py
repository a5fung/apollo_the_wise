"""#235 — gap-finder answer parsing (the only non-I/O logic in the loop)."""
from agents.market_intelligence.source_gap_finder import parse_gap_answer


def test_well_formed_answer_parses():
    ans = ("EVENT: Won a $40M Japan MoD drone contract.\n"
           "FIRST_REPORTED: GlobeNewswire\n"
           "SOURCE_CLASS: press_wire\n")
    p = parse_gap_answer(ans)
    assert p["source_class"] == "press_wire"
    assert p["first_reported"] == "GlobeNewswire"
    assert p["covered"] is False


def test_covered_feed_is_flagged_not_dropped():
    ans = ("EVENT: Q1 earnings beat.\n"
           "FIRST_REPORTED: Benzinga Newswire\n"
           "SOURCE_CLASS: press_wire\n")
    p = parse_gap_answer(ans)
    assert p is not None and p["covered"] is True


def test_none_found_returns_none():
    assert parse_gap_answer("EVENT: unclear\nFIRST_REPORTED: n/a\nSOURCE_CLASS: none_found") is None


def test_unparseable_returns_none():
    assert parse_gap_answer("I could not determine the cause of the move.") is None
    assert parse_gap_answer("") is None
    assert parse_gap_answer(None) is None
