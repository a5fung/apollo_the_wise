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


# ── the payload must carry what the renderer reads (2026-08-03) ──────────────────────────────

def test_the_ready_payload_carries_the_fields_the_renderer_keys_off():
    """THE bug this file's 8/02 teeth shipped with: `_format_pending_reviews_section` reads
    `earliest_review_date` for the age tag, the ≥30d banner and the oldest-first sort — and
    `data_gated_reviews.build_review_summary` did not put it in the payload. Every tooth was inert
    in production while these tests passed on fabricated dicts that DID have the field.

    Same class as /audit and /crypto shipping with working handlers and no registration: correct
    code, wrong payload, nothing failing."""
    src = open("agents/market_intelligence/data_gated_reviews.py").read()
    i = src.index("entry_summary = {")
    block = src[i:i + 1600]
    assert '"earliest_review_date"' in block, "renderer reads it; payload must supply it"
    assert '"kind"' in block


def test_a_quiet_tripwire_reports_SILENCE_not_staleness():
    """orb_entry_stuck_pending_new reads 0/1 across 67 post-fix days because the RDW bug has not
    recurred. Rendering that as 'ripe 67d' turned good news into the top of a neglect list."""
    from agents.market_intelligence.system_review import _format_pending_reviews_section
    out = _format_pending_reviews_section({"ready": [{
        "review_id": "orb_entry_stuck_pending_new", "title": "P0 — ORB entry stuck",
        "kind": "tripwire", "current_count": 0, "threshold": 1,
        "earliest_review_date": "2026-05-28", "action_when_ready": "Pull the rows."}]})
    assert "no recurrence" in out and "ripe" not in out


def test_a_FIRED_tripwire_says_so():
    from agents.market_intelligence.system_review import _format_pending_reviews_section
    out = _format_pending_reviews_section({"ready": [{
        "review_id": "x", "title": "T", "kind": "tripwire", "current_count": 3,
        "threshold": 1, "earliest_review_date": "2026-05-28", "action_when_ready": "Act."}]})
    assert "FIRED" in out


def test_a_quiet_tripwire_never_counts_toward_the_stale_banner():
    """Otherwise the banner reads 'N ripe ≥30d — surfacing is not triage' about tripwires that are
    working exactly as intended."""
    from agents.market_intelligence.system_review import _format_pending_reviews_section
    out = _format_pending_reviews_section({"ready": [{
        "review_id": "x", "title": "T", "kind": "tripwire", "current_count": 0, "threshold": 1,
        "earliest_review_date": "2026-01-01", "action_when_ready": "Act."}]})
    assert "surfacing is not triage" not in out


def test_accrual_still_shows_age_and_still_trips_the_banner():
    """The 8/02 teeth must survive: a genuinely stale accrual item is still called out."""
    from agents.market_intelligence.system_review import _format_pending_reviews_section
    out = _format_pending_reviews_section({"ready": [{
        "review_id": "x", "title": "T", "kind": "accrual", "current_count": 99, "threshold": 10,
        "earliest_review_date": "2026-01-01", "action_when_ready": "Act."}]})
    assert "ripe" in out and "surfacing is not triage" in out
