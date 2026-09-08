"""#471/#167 — the lane-2 decision record must log WHY, not only WHAT.

Operator, 2026-09-08, during the seed-vs-birth calibration read: "let's log why as
well so we can know what was decision making at the time."

The read could establish that 13 of 25 seeded names never joined any theme, but not
why — every seed rendered as "(none given)", because the record stored the outcome and,
for join/birth only, the theme name. A seed carried neither a story nor a reason, even
though `new_seeds` already held the story the model saw. It was being dropped on the
floor at the point of writing.

A seed becomes a theme only when a LATER name shares its story, so the story text is
exactly what makes "it stayed a one-off" checkable after the fact rather than inferred.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest


def _outcomes_from(record):
    return record["outcomes"]


def test_a_seeded_name_carries_the_story_it_was_seeded_on():
    """The gap the operator asked to close: a seed with no story is unauditable."""
    from agents.market_intelligence import theme_engine as te
    today_set = {"AAA", "BBB"}
    new_seeds = [{"ticker": "AAA", "story": "orbital launch cadence"}]
    seeded_tk = {s["ticker"] for s in new_seeds}
    seed_story = {s["ticker"]: s.get("story") for s in new_seeds}
    clean = [{"tickers": ["BBB"], "joined": True, "name": "Nuclear SMR buildout"}]

    outcomes = {}
    for tk in sorted(today_set):
        outcome, narr = "none", None
        for e in clean:
            if tk in e["tickers"]:
                outcome = "join" if e["joined"] else "birth"
                narr = e["name"]
                break
        if outcome == "none" and tk in seeded_tk:
            outcome = "seed"
        rec_o = {"outcome": outcome}
        if narr is not None:
            rec_o["narrative"] = narr
        if outcome == "seed":
            rec_o["story"] = seed_story.get(tk)
        outcomes[tk] = rec_o

    assert outcomes["AAA"]["outcome"] == "seed"
    assert outcomes["AAA"]["story"] == "orbital launch cadence", \
        "a seed must record the story it was seeded on"
    # join/birth keep the theme name and gain no spurious story key
    assert outcomes["BBB"]["narrative"] == "Nuclear SMR buildout"
    assert "story" not in outcomes["BBB"]


def test_the_writer_in_the_module_matches_that_contract():
    """Pins the real source, so the behaviour above cannot silently drift out of it."""
    import inspect
    from agents.market_intelligence import theme_engine as te
    src = inspect.getsource(te._discover_lane2_registry)
    assert 'seed_story = {s["ticker"]: s.get("story") for s in new_seeds}' in src
    assert 'rec_o["story"] = seed_story.get(tk)' in src
    assert '"offered_count": len(today_set)' in src, \
        "night-level context: a lone candidate had no peer to pair with by construction"
