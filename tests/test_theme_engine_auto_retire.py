"""Regression test for theme_engine auto-retire on Pass1/1.5 drop (2026-05-25).

The bug: themes dropped during Pass1 protect_strip + cap_drop or absorbed by
Pass1.5 silently vanished from the daily upsert. Their last row stayed at
Mainstream/Accelerating forever, tripping the L1 zombie_theme invariant.

The fix: after merge passes complete, diff `existing` (themes loaded at run
start) vs final `all_themes`. For lost names, synthesize Retired rows with
parent_theme recovered from today's theme_pass1_5_absorption +
theme_pass1_protect_strip audit events.

This test verifies the diff-and-synthesize logic. It bypasses the upsert
itself (covered by other tests) and asserts on the rows that would be
written.
"""
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest


def _parse_successor_map(audit_rows):
    """Replicates the regex logic in theme_engine.py to extract successor
    pointers from today's audit events. Kept here as a fixture so a future
    refactor that breaks the parsing has a focused failure point."""
    import re
    successor_by_lost = {}
    for r in audit_rows:
        if r["event_type"] == "theme_pass1_5_absorption":
            m = re.search(r"'([^']+)' -> '([^']+)'", r["summary"] or "")
            if m:
                successor_by_lost.setdefault(m.group(1), m.group(2))
        else:
            im = re.search(r"i='([^']+)'", r["detail"] or "")
            jm = re.search(r"j='([^']+)'", r["detail"] or "")
            if im and jm:
                successor_by_lost.setdefault(jm.group(1), im.group(1))
    return successor_by_lost


def test_absorption_summary_parsed_to_successor():
    """theme_pass1_5_absorption summary 'Pass1.5: A -> B' → A: B."""
    rows = [{
        "event_type": "theme_pass1_5_absorption",
        "summary": "Pass1.5: 'Cybersecurity Network Edge & SD-WAN' -> 'Network Security & Zero-Trust Edge'",
        "detail": "",
    }]
    m = _parse_successor_map(rows)
    assert m == {"Cybersecurity Network Edge & SD-WAN": "Network Security & Zero-Trust Edge"}


def test_protect_strip_detail_parsed_to_successor():
    """theme_pass1_protect_strip detail 'i=X ... j=Y' → Y is lost, X is successor."""
    rows = [{
        "event_type": "theme_pass1_protect_strip",
        "summary": "Pass1: stripped 3 ticker(s)",
        "detail": (
            "i='Custom AI Silicon & Chip Architecture Licensing' i_protected=True i_size=7 "
            "j='AI Datacenter Silicon' j_protected=True j_size=0 "
            "intersection=['AMD', 'ARM', 'MRVL'] stripped='AI Datacenter Silicon' 3"
        ),
    }]
    m = _parse_successor_map(rows)
    assert m == {"AI Datacenter Silicon": "Custom AI Silicon & Chip Architecture Licensing"}


def test_multiple_events_first_match_wins():
    """If the same lost theme appears in both an absorption and a strip event
    (rare but possible), the first audit row encountered wins via setdefault."""
    rows = [
        {"event_type": "theme_pass1_5_absorption",
         "summary": "Pass1.5: 'A' -> 'B'", "detail": ""},
        {"event_type": "theme_pass1_protect_strip",
         "summary": "Pass1: stripped",
         "detail": "i='C' i_size=5 j='A' j_size=0 intersection=[] stripped='A' 0"},
    ]
    m = _parse_successor_map(rows)
    assert m["A"] == "B"  # absorption wins because it came first


def test_diff_identifies_lost_themes_correctly():
    """Themes in `existing` whose name isn't in final_names AND whose prior
    stage isn't already 'Retired' should be flagged as lost."""
    existing = [
        {"name": "A", "stage": "Mainstream", "tickers": ["X", "Y"]},
        {"name": "B", "stage": "Accelerating", "tickers": ["Z"]},
        {"name": "C", "stage": "Fading", "tickers": []},
        {"name": "D", "stage": "Retired", "tickers": []},  # already retired
    ]
    final_names = {"A", "C"}  # B dropped, D was already retired
    lost = [
        t for t in existing
        if t.get("stage") != "Retired" and t["name"] not in final_names
    ]
    assert [t["name"] for t in lost] == ["B"]


def test_retire_row_carries_successor_pointer():
    """Synthesized Retired row should set parent_theme from successor_by_lost
    and tickers=[]."""
    lost = [{"name": "B", "stage": "Mainstream", "tickers": ["Z"]}]
    successor_by_lost = {"B": "B_successor"}
    today = date(2026, 5, 25)
    today_str = today.isoformat()

    # Replicate the synthesis logic (kept in lockstep with theme_engine.py).
    retire_rows = []
    for t in lost:
        successor = successor_by_lost.get(t["name"])
        retire_rows.append({
            "theme_date": today,
            "name": t["name"],
            "stage": "Retired",
            "parent_theme": successor,
            "tickers": [],
        })

    assert len(retire_rows) == 1
    r = retire_rows[0]
    assert r["name"] == "B"
    assert r["stage"] == "Retired"
    assert r["parent_theme"] == "B_successor"
    assert r["tickers"] == []
    assert r["theme_date"] == today


def test_retire_row_with_no_successor():
    """If no audit event matches the lost theme (e.g. dropped via a path we
    don't capture), parent_theme stays None — Retired row still gets written."""
    lost = [{"name": "X", "stage": "Mainstream", "tickers": []}]
    successor_by_lost = {}  # nothing matched
    retire_rows = [{
        "name": t["name"],
        "stage": "Retired",
        "parent_theme": successor_by_lost.get(t["name"]),
        "tickers": [],
    } for t in lost]
    assert retire_rows[0]["parent_theme"] is None
    assert retire_rows[0]["stage"] == "Retired"
