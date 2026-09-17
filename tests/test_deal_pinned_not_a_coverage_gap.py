"""A stock pinned by an announced acquisition is NOT a theme-engine coverage gap.

FOUND 2026-09-17, by the operator, on the evening brief's own line:

    ⚓ Unanchored persistent (5-session, RS≥90) — entered: ACVA
       theme-engine coverage gap — no theme claimed these names all week

His reply: *"From evening brief, but stock is being bought out."* He was right, and our own bars
already said so — ACVA gapped **+44.2% on 114.9M shares** (vs a ~3M norm) on 2026-09-11 and every
session since traded in a **0.19–0.48%** range, closing 10.41 → 10.48. That is a cash deal price.

WHY IT MATTERED: RS is a backward-looking 1M/3M/6M percentile, so one deal gap moved ACVA from rank
**1084 → 7** and it was still rank 17 six sessions later on flat bars. The surface then asserted a
diagnosis the data contradicts: a company being acquired is **un-themeable by construction**, so no
amount of theme-engine work would ever claim it. The claim pointed at work that does not exist.

⚠ THE RULE IS NOT NEW. `db.get_eod_9m_sugar_babies` already carried it — *"intraday range >= 2% of
close (rejects merger-arb pins like DBRG)"* — but on the retired 9M path; the only other M&A
handling (`parabolic_detector._news_check_for_exclusion`) is private, Perplexity-paid and bound to
the parabolic setup. `db.get_deal_pinned_tickers` lifts the FREE rule to a shared helper rather than
inventing a third mechanism.

⚠ AND THE EXCLUSION IS ANNOUNCED, NOT SILENT — this file's parent module states the rule itself
("silence ≠ didn't run"). Swapping a false claim for an invisible drop is not a fix, so the brief
names what it removed. Both halves are pinned below.
"""
from __future__ import annotations

from agents.market_intelligence.brief_composer import (
    compute_persistent_unanchored_sets, compute_unanchored,
)

LEADERS = [
    {"ticker": "ACVA", "rs_composite": 99.3},   # the real case: deal-pinned
    {"ticker": "HURN", "rs_composite": 95.0},   # a genuine unanchored leader
    {"ticker": "SPY",  "rs_composite": 99.9},   # index, always skipped
    {"ticker": "XLK",  "rs_composite": 99.9},   # ETF prefix, always skipped
]


def test_a_deal_pinned_leader_is_not_reported_as_unanchored():
    out = compute_unanchored(LEADERS, set(), rs_floor=90.0, pinned_tickers={"ACVA"})
    assert "ACVA" not in out, (
        "ACVA was still counted as an unanchored leader — this is the exact line the operator "
        "corrected on 2026-09-17"
    )
    assert "HURN" in out, "the filter removed a genuine unanchored leader as well"


def test_without_a_pinned_set_nothing_changes():
    """Backwards compatibility is the whole reason the parameter defaults to None: every
    existing caller and every stored session predating 2026-09-17 must read identically."""
    base = compute_unanchored(LEADERS, set(), rs_floor=90.0)
    for empty in (None, set()):
        assert compute_unanchored(LEADERS, set(), rs_floor=90.0, pinned_tickers=empty) == base
    assert "ACVA" in base, "test is vacuous — ACVA must be present WITHOUT the filter"


def test_the_existing_etf_and_index_skips_still_apply():
    out = compute_unanchored(LEADERS, set(), rs_floor=90.0, pinned_tickers={"ACVA"})
    assert "SPY" not in out and "XLK" not in out


def test_themed_and_pinned_are_independent_filters():
    """A pinned name that is ALSO themed must not reappear, and vice versa — the two sets are
    applied separately, so a bug in either could resurrect a name."""
    assert compute_unanchored(LEADERS, {"HURN"}, rs_floor=90.0, pinned_tickers={"ACVA"}) == []


def _session(date_str, tickers, pinned=()):
    return {"date": date_str, "leaders": [{"ticker": t, "rs_composite": 99.0} for t in tickers],
            "themed_tickers": set(), "pinned_tickers": set(pinned)}


def test_the_persistence_check_threads_the_pinned_set_per_session():
    """⚠ PER-SESSION, not once: a name is pinned only from its announcement onward, and the
    5-session window straddles that day. Using today's pinned set for all five would rewrite
    history and could erase a name that was genuinely unanchored before the deal."""
    sessions = [_session(f"d{i}", ["ACVA", "HURN"], pinned=["ACVA"]) for i in range(6)]
    today, prior = compute_persistent_unanchored_sets(sessions, rs_floor=90.0, streak=5)
    assert "ACVA" not in today and "ACVA" not in prior
    assert "HURN" in today, "the genuine persistent leader was lost"


def test_a_name_pinned_only_recently_still_counts_before_its_deal():
    """The half the per-session threading buys: ACVA was a legitimate leader before 09-11."""
    sessions = [_session("d0", ["ACVA"], pinned=["ACVA"])] + \
               [_session(f"d{i}", ["ACVA"]) for i in range(1, 6)]
    today, prior = compute_persistent_unanchored_sets(sessions, rs_floor=90.0, streak=5)
    assert "ACVA" not in today, "still counted today despite being pinned today"
    assert "ACVA" in prior, (
        "the PRIOR window was computed with today's pinned set — that rewrites history and "
        "hides the change the brief exists to report"
    )
