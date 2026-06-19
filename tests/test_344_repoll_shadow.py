"""#344 — re-poll trigger + grade-corpus assembly (pure-function unit tests, no I/O).

The re-poll shadow is the real hot-path risk; the offline corpus eval gives it zero
coverage (advisor 6/19). These lock the trigger contract: shadow-re-grade a CACHED grade
EXACTLY ONCE when a new in-ORB primary-subject source appears, and NEVER re-poll a grade
that already fires.
"""
from datetime import date

from agents.market_intelligence.ep_detector import (
    should_repoll_shadow, assemble_grade_corpus,
)


# ── should_repoll_shadow(cached_quality, grade_count, cur_count, already_logged, in_orb) ──

def test_repoll_fires_on_new_source_for_routine_in_window():
    # BFLY class: graded routine with 0 sources, the PR arrives (count 0→1), in the
    # ORB window, not yet logged → re-grade.
    assert should_repoll_shadow("routine", 0, 1, False, True) is True


def test_repoll_only_once_already_logged():
    # Same new-source condition but we've already logged → never again (no per-tick thrash).
    assert should_repoll_shadow("routine", 0, 1, True, True) is False


def test_repoll_only_in_orb_window():
    assert should_repoll_shadow("routine", 0, 1, False, False) is False


def test_repoll_never_for_firing_grade():
    # A grade that already fires is terminal for the miss-class we fix — never re-poll.
    assert should_repoll_shadow("strong", 0, 2, False, True) is False
    assert should_repoll_shadow("game_changer", 0, 3, False, True) is False


def test_repoll_no_new_source_no_fire():
    assert should_repoll_shadow("routine", 1, 1, False, True) is False
    assert should_repoll_shadow("routine", 2, 1, False, True) is False  # count fell


# ── assemble_grade_corpus: date anchor + prior-context labeling ──

_AGREEMENT = {"filed": "2025-11-18", "items": "1.01,9.01",
              "text": "x" * 200 + " entered into a Co-Development and Licensing Agreement "
                      "with Midjourney, Inc. granting an exclusive license; $15 million "
                      "one-time fee and a $10 million annual license fee."}
_EARNINGS = {"filed": "2026-02-26", "items": "2.02,9.01",
             "text": "y" * 200 + " total revenue of $26.5 million, up 25% YoY; Midjourney "
                     "partnership contributed $6.8 million of revenue in Q4."}


def test_corpus_always_anchors_today():
    c = assemble_grade_corpus(date(2026, 6, 18), None, [], None, None, enrich=False)
    assert "today is 2026-06-18" in c
    assert "[TODAY'S NEWS" in c


def test_corpus_baseline_omits_prior_context():
    c = assemble_grade_corpus(date(2026, 6, 18), None, [], _AGREEMENT, _EARNINGS, enrich=False)
    assert "PRIOR CONTEXT" not in c          # enrich=False → no prior agreement/earnings
    assert "Co-Development" not in c


def test_corpus_enriched_labels_prior_context_with_age_not_today():
    c = assemble_grade_corpus(date(2026, 6, 18), None, [], _AGREEMENT, _EARNINGS, enrich=True)
    # Prior agreement substance is surfaced (past the boilerplate) and clearly dated.
    assert "Co-Development and Licensing Agreement" in c
    assert "filed 2025-11-18" in c
    assert "months BEFORE today's gap" in c
    assert "NOT today's catalyst" in c
    # Revenue context surfaced too.
    assert "Midjourney partnership contributed" in c
