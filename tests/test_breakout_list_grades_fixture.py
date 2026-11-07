"""The breakout-list grade fixture stays well-formed: one grade per (ticker, list night), every grade from
the allowed set, every sheet on disk, and the key matches the sheet's own answer key."""
from pathlib import Path

from tests.fixtures.breakout_list_grades import BREAKOUT_LIST_GRADES, GRADES_ALLOWED

_REPO = Path(__file__).resolve().parent.parent


def test_one_grade_per_ticker_and_night():
    keys = [(g.ticker, g.list_date) for g in BREAKOUT_LIST_GRADES]
    assert len(keys) == len(set(keys))


def test_every_grade_is_an_allowed_value_with_his_words():
    for g in BREAKOUT_LIST_GRADES:
        assert g.grade in GRADES_ALLOWED, g
        assert g.operator_words.strip(), g


def test_every_sheet_exists_and_its_key_agrees():
    for sheet in {g.sheet for g in BREAKOUT_LIST_GRADES}:
        path = _REPO / sheet
        assert path.exists(), sheet
        key = (path.parent / "key_do_not_show.txt").read_text().splitlines()
        rows = {r.split("|")[0]: r.split("|") for r in key if r[:2] in {f"{c}|" for c in "ABCDEFGHIJKL"}}
        for g in (x for x in BREAKOUT_LIST_GRADES if x.sheet == sheet):
            letter, ticker, rank = rows[g.sheet_card][:3]
            assert (ticker, int(rank)) == (g.ticker, g.list_rank), g
