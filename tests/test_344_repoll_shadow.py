"""#344 — re-poll trigger + grade-corpus assembly (pure-function unit tests, no I/O).

The re-poll shadow is the real hot-path risk; the offline corpus eval gives it zero
coverage (advisor 6/19). These lock the trigger contract: shadow-re-grade a CACHED grade
EXACTLY ONCE when a new in-ORB primary-subject source appears, and NEVER re-poll a grade
that already fires.
"""
from datetime import date

from datetime import timedelta

from agents.market_intelligence.ep_detector import (
    should_repoll_shadow, assemble_grade_corpus, recent_dilution_filing,
    _DILUTION_WINDOW_DAYS,
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


# ── #238 dilution feed: recent_dilution_filing + corpus negative-context block ──

_GRADE_DAY = date(2026, 6, 18)
_424B5 = {"form": "424B5", "filed": (_GRADE_DAY - timedelta(days=3)).isoformat(), "items": "",
          "text": "z" * 200 + " 5,000,000 shares of common stock at a public offering price "
                  "of $4.10 per share; net proceeds of approximately $19 million."}
_8K_302 = {"form": "8-K", "filed": (_GRADE_DAY - timedelta(days=2)).isoformat(),
           "items": "3.02,9.01", "text": "w" * 200 + " unregistered sale of equity securities; "
                    "issued 1,200,000 shares in a private placement."}


def test_dilution_finds_recent_424b5():
    f = recent_dilution_filing([_424B5], _GRADE_DAY)
    assert f is not None and f["form"] == "424B5"


def test_dilution_finds_8k_item_302():
    f = recent_dilution_filing([_8K_302], _GRADE_DAY)
    assert f is not None and "3.02" in f["items"]


def test_dilution_picks_most_recent_in_window():
    # _8K_302 (−2d) is newer than _424B5 (−3d) → it wins.
    f = recent_dilution_filing([_424B5, _8K_302], _GRADE_DAY)
    assert f["filed"] == _8K_302["filed"]


def test_dilution_excludes_stale_offering():
    stale = dict(_424B5, filed=(_GRADE_DAY - timedelta(days=_DILUTION_WINDOW_DAYS + 5)).isoformat())
    assert recent_dilution_filing([stale], _GRADE_DAY) is None


def test_dilution_excludes_offering_after_the_gap():
    # Point-in-time: an offering filed AFTER today's gap = raising into strength, excluded.
    future = dict(_424B5, filed=(_GRADE_DAY + timedelta(days=1)).isoformat())
    assert recent_dilution_filing([future], _GRADE_DAY) is None


def test_dilution_ignores_non_dilutive_8k():
    plain = {"form": "8-K", "filed": (_GRADE_DAY - timedelta(days=1)).isoformat(),
             "items": "1.01,9.01", "text": "a deal"}
    assert recent_dilution_filing([plain], _GRADE_DAY) is None


def test_corpus_baseline_omits_dilution_block():
    c = assemble_grade_corpus(_GRADE_DAY, None, [], None, None, enrich=False,
                              dilution_filing=_424B5)
    assert "DILUTIVE FILING" not in c        # enrich=False → no dilution block at all


def test_corpus_enriched_includes_dated_dilution_negative_context():
    c = assemble_grade_corpus(_GRADE_DAY, None, [], None, None, enrich=True,
                              dilution_filing=_424B5)
    assert "RECENT DILUTIVE FILING" in c
    assert "424B5" in c
    assert "filed " + _424B5["filed"] in c
    assert "days BEFORE today's gap" in c
    # Stays a JUDGE prompt, not a deterministic reject — the canary (real EP + raise) relies on this.
    assert "do NOT auto-reject" in c
    # Substantive slice surfaced past the boilerplate.
    assert "offering price" in c
