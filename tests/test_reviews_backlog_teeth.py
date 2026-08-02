"""The data-gated review list must show its AGE and its SIZE (2026-08-02).

Measured that day: 124 registered reviews, **50 already ripe, the oldest 72 days**. They surfaced in
the Sunday digest every week and nothing happened.

Operator: *"is this file and review again pile?"* — yes, it was. A list that fires and is ignored is
not a gate, it is a pile; the same defect the PLAN board had before the growth ceiling.

Two teeth, both deliberately mild, plus one deliberate non-tooth:
  1. AGE per item — a review ripe 72 days must not read like a new one.
  2. A CAP on how many render, with the overflow COUNTED — an un-scannable wall is *why* it got
     ignored, but silently truncating would be the same failure wearing a tidier face.
  3. It does NOT auto-close or auto-defer anything. A stale review still holds a real question and
     disposing of it is the operator's call.
"""
from datetime import date, timedelta

import agents.market_intelligence.system_review as sr

_TODAY = date(2026, 8, 2)


def _r(days_ripe, rid="x", title=None):
    return {"review_id": rid, "title": title or f"review {rid}",
            "action_when_ready": "Do the thing. Then more.",
            "earliest_review_date": (_TODAY - timedelta(days=days_ripe)).isoformat()}


def _render(monkeypatch, ready):
    monkeypatch.setattr("agents.market_intelligence.collector.et_today", lambda: _TODAY)
    return sr._format_pending_reviews_section({"ready": ready})


def test_age_is_shown_so_a_forgotten_review_cannot_read_as_new(monkeypatch):
    out = _render(monkeypatch, [_r(72, "ancient")])
    assert "ripe 72d" in out


def test_the_total_count_is_in_the_header(monkeypatch):
    out = _render(monkeypatch, [_r(i, f"r{i}") for i in range(1, 13)])
    assert "Reviews ready* (12)" in out


def test_a_stale_banner_fires_and_says_surfacing_is_not_triage(monkeypatch):
    out = _render(monkeypatch, [_r(72), _r(40, "b"), _r(2, "c")])
    assert "have been ripe" in out and "surfacing is not triage" in out


def test_no_stale_banner_when_everything_is_fresh(monkeypatch):
    out = _render(monkeypatch, [_r(2), _r(5, "b")])
    assert "surfacing is not triage" not in out


def test_oldest_first(monkeypatch):
    out = _render(monkeypatch, [_r(3, "new", "NEW ONE"), _r(60, "old", "OLD ONE")])
    assert out.index("OLD ONE") < out.index("NEW ONE")


def test_overflow_is_COUNTED_never_silently_dropped(monkeypatch):
    """Truncating quietly would be the same failure in a tidier form."""
    out = _render(monkeypatch, [_r(i, f"r{i}") for i in range(1, 21)])
    assert f"and {20 - sr._REVIEWS_RENDER_CAP} more ripe" in out


def test_it_never_auto_closes_or_defers(monkeypatch):
    """The registry's own status semantics make disposition the operator's call. A renderer that
    quietly retired stale items would lose real questions — the failure the registry prevents."""
    ready = [_r(400, "very_old")]
    out = _render(monkeypatch, ready)
    assert "very_old" in out or "review very_old" in out
    assert ready[0].get("status") is None, "renderer must not mutate review state"
    for word in ("auto-closed", "deferred", "retired"):
        assert word not in out.lower()


def test_empty_stays_silent(monkeypatch):
    assert _render(monkeypatch, []) == ""
