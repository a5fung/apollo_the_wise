"""#332 — C1 deterministic setup-class classifier (ADR 0028 §2, operator-signed 2026-07-18).

THE CLOSED SPEC under test:
  pradeep_explosive: mcap < $2B AND (RVOL>=3 OR 9M-print same-day OR sugar-baby cohort)
  mature_leader:     mcap >= $10B OR (Stage-2 AND price>=0.75*52w_high AND ADV_20_dollar>=$100M)
  episodic_neglect:  $2B <= mcap < $10B AND price<0.70*52w_high AND upgrades_30d == 0
  unclassified:      anything else / missing fields -> uniform baseline, never penalized

Two layers:
  1. `classify_setup_class` — pure, zero I/O. Every class boundary (incl. the two operator-
     pinned cuts: ADV_20_dollar>=$100M and upgrades_30d==0), the pradeep-vs-mature overlap
     tie-break (first-match-wins per the ADR §2 table order), missing-fields->unclassified,
     and a lookahead-honesty pin (the function only ever reads what's handed to it — it can't
     "reach out" for fresher data).
  2. `compute_setup_class_fields` — the async assembler: reuses structure_axis_shadow's
     `stage2`, calls the 4 as-of lookups (3 DB + the repaired upgrades source), and is
     independently fail-soft per lookup (mirrors the axis-shadow "never guess" discipline).
  3. `count_recent_upgrades` — the REPAIRED (#332, 2026-07-18) upgrades_30d source: pure,
     lookahead-honest counting of POSITIVE-DIRECTION events from
     `collector.get_recent_upgrade_events`'s dated-event shape. Includes the explicit
     discrimination re-verification the repair was gated on: a coverage-heavy name must NOT
     read upgrades_30d==0, a genuinely-uncovered name can.

P0 — this module never grades/gates/sizes anything (THE LINE). No test here touches
score_tier, ep_score, or trade state.
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock

from tests.conftest import make_mock_pool

from agents.market_intelligence.setup_class_classifier import (
    CLASS_EPISODIC_NEGLECT,
    CLASS_MATURE_LEADER,
    CLASS_PRADEEP_EXPLOSIVE,
    CLASS_UNCLASSIFIED,
    MATURE_ADV_DOLLAR_MIN,
    MCAP_MATURE_MIN,
    MCAP_PRADEEP_MAX,
    classify_setup_class,
    compute_setup_class_fields,
    count_recent_upgrades,
)


def _run(coro):
    return asyncio.run(coro)


# ─── pradeep_explosive ──────────────────────────────────────────────────────────────────────

def test_pradeep_explosive_via_rvol():
    assert classify_setup_class({"market_cap": 1.5e9, "rvol": 3.0}) == CLASS_PRADEEP_EXPLOSIVE


def test_pradeep_explosive_via_9m_same_day_even_with_low_rvol():
    c = {"market_cap": 1.5e9, "rvol": 0.5, "is_9m_same_day": True}
    assert classify_setup_class(c) == CLASS_PRADEEP_EXPLOSIVE


def test_pradeep_explosive_via_sugar_baby_cohort_even_with_no_rvol():
    c = {"market_cap": 1.5e9, "rvol": None, "is_sugar_baby_cohort": True}
    assert classify_setup_class(c) == CLASS_PRADEEP_EXPLOSIVE


def test_pradeep_explosive_rvol_below_3_and_no_other_trigger_falls_through():
    c = {"market_cap": 1.5e9, "rvol": 2.9}
    assert classify_setup_class(c) == CLASS_UNCLASSIFIED


def test_pradeep_explosive_mcap_exactly_2b_is_excluded_strict_less_than():
    """Spec is `mcap < $2B` (strict) — exactly $2B must NOT qualify."""
    c = {"market_cap": MCAP_PRADEEP_MAX, "rvol": 10.0}
    assert classify_setup_class(c) != CLASS_PRADEEP_EXPLOSIVE


def test_pradeep_explosive_mcap_at_10b_never_qualifies_regardless_of_rvol():
    c = {"market_cap": 50e9, "rvol": 100.0, "is_9m_same_day": True, "is_sugar_baby_cohort": True}
    assert classify_setup_class(c) == CLASS_MATURE_LEADER


# ─── mature_leader ──────────────────────────────────────────────────────────────────────────

def test_mature_leader_via_mcap_alone():
    assert classify_setup_class({"market_cap": 10.1e9}) == CLASS_MATURE_LEADER


def test_mature_leader_mcap_exactly_10b_is_included_inclusive():
    """Spec is `mcap >= $10B` (inclusive) — exactly $10B DOES qualify."""
    assert classify_setup_class({"market_cap": MCAP_MATURE_MIN}) == CLASS_MATURE_LEADER


def test_mature_leader_via_stage2_near_high_and_adv():
    c = {
        "market_cap": 3e9, "stage2": True, "price": 76.0, "week52_high": 100.0,
        "adv_20_dollar": 150_000_000,
    }
    assert classify_setup_class(c) == CLASS_MATURE_LEADER


def test_mature_leader_price_exactly_75pct_of_high_is_included_inclusive():
    c = {
        "market_cap": 3e9, "stage2": True, "price": 75.0, "week52_high": 100.0,
        "adv_20_dollar": MATURE_ADV_DOLLAR_MIN,
    }
    assert classify_setup_class(c) == CLASS_MATURE_LEADER


def test_mature_leader_adv_exactly_100m_is_included_inclusive():
    c = {
        "market_cap": 3e9, "stage2": True, "price": 80.0, "week52_high": 100.0,
        "adv_20_dollar": 100_000_000.0,
    }
    assert classify_setup_class(c) == CLASS_MATURE_LEADER


def test_mature_leader_adv_just_below_100m_fails():
    c = {
        "market_cap": 3e9, "stage2": True, "price": 80.0, "week52_high": 100.0,
        "adv_20_dollar": 99_999_999.0,
    }
    assert classify_setup_class(c) == CLASS_UNCLASSIFIED


def test_mature_leader_stage2_path_needs_all_three_conditions():
    base = {
        "market_cap": 3e9, "stage2": True, "price": 76.0, "week52_high": 100.0,
        "adv_20_dollar": 150_000_000,
    }
    # Drop stage2 -> fails
    assert classify_setup_class({**base, "stage2": False}) == CLASS_UNCLASSIFIED
    assert classify_setup_class({**base, "stage2": None}) == CLASS_UNCLASSIFIED
    # Not near high -> fails
    assert classify_setup_class({**base, "price": 50.0}) == CLASS_UNCLASSIFIED
    # ADV too low -> fails
    assert classify_setup_class({**base, "adv_20_dollar": 1_000_000}) == CLASS_UNCLASSIFIED
    assert classify_setup_class({**base, "adv_20_dollar": None}) == CLASS_UNCLASSIFIED


# ─── episodic_neglect ───────────────────────────────────────────────────────────────────────

def test_episodic_neglect_full_match():
    c = {"market_cap": 5e9, "price": 60.0, "week52_high": 100.0, "upgrades_30d": 0}
    assert classify_setup_class(c) == CLASS_EPISODIC_NEGLECT


def test_episodic_neglect_mcap_band_boundaries_inclusive_lower_exclusive_upper():
    lo = {"market_cap": 2_000_000_000, "price": 60.0, "week52_high": 100.0, "upgrades_30d": 0}
    assert classify_setup_class(lo) == CLASS_EPISODIC_NEGLECT  # $2B included (>=)
    hi = {"market_cap": 10_000_000_000, "price": 60.0, "week52_high": 100.0, "upgrades_30d": 0}
    assert classify_setup_class(hi) != CLASS_EPISODIC_NEGLECT  # $10B excluded (mature_leader instead)
    assert classify_setup_class(hi) == CLASS_MATURE_LEADER


def test_episodic_neglect_price_exactly_70pct_of_high_is_excluded_strict_less_than():
    c = {"market_cap": 5e9, "price": 70.0, "week52_high": 100.0, "upgrades_30d": 0}
    assert classify_setup_class(c) == CLASS_UNCLASSIFIED


def test_episodic_neglect_price_just_below_70pct_qualifies():
    c = {"market_cap": 5e9, "price": 69.99, "week52_high": 100.0, "upgrades_30d": 0}
    assert classify_setup_class(c) == CLASS_EPISODIC_NEGLECT


def test_episodic_neglect_upgrades_must_be_exactly_zero():
    base = {"market_cap": 5e9, "price": 60.0, "week52_high": 100.0}
    assert classify_setup_class({**base, "upgrades_30d": 0}) == CLASS_EPISODIC_NEGLECT
    assert classify_setup_class({**base, "upgrades_30d": 1}) == CLASS_UNCLASSIFIED
    assert classify_setup_class({**base, "upgrades_30d": None}) == CLASS_UNCLASSIFIED


# ─── unclassified fail-to-baseline + missing fields (lookahead-honesty pin) ────────────────

def test_missing_market_cap_is_unclassified_regardless_of_everything_else():
    """market_cap is the outer gate for all 3 named classes — its absence must short-circuit
    straight to unclassified even when every OTHER field looks explosive."""
    c = {
        "market_cap": None, "rvol": 50.0, "is_9m_same_day": True, "is_sugar_baby_cohort": True,
        "stage2": True, "price": 100.0, "week52_high": 100.0, "adv_20_dollar": 1e9,
        "upgrades_30d": 0,
    }
    assert classify_setup_class(c) == CLASS_UNCLASSIFIED


def test_empty_candidate_is_unclassified():
    assert classify_setup_class({}) == CLASS_UNCLASSIFIED


def test_mid_cap_with_no_qualifying_signal_is_unclassified_never_penalized():
    """A $5B name with no RVOL/9M/sugar-baby/stage2/neglect signal at all — must degrade
    to unclassified, not be forced into any of the 3 named classes."""
    c = {"market_cap": 5e9, "rvol": 1.0, "price": 90.0, "week52_high": 100.0, "upgrades_30d": 2}
    assert classify_setup_class(c) == CLASS_UNCLASSIFIED


def test_all_four_classes_are_reachable_and_exhaustive_sweep():
    """Sanity sweep: every class in the ADR §2 table is actually producible, and the function
    never raises or returns anything outside the pinned vocabulary."""
    from agents.market_intelligence.setup_class_classifier import ALL_CLASSES
    cases = [
        {"market_cap": 1e9, "rvol": 5.0},
        {"market_cap": 20e9},
        {"market_cap": 5e9, "price": 50.0, "week52_high": 100.0, "upgrades_30d": 0},
        {"market_cap": 5e9, "price": 95.0, "week52_high": 100.0, "upgrades_30d": 0},
    ]
    seen = {classify_setup_class(c) for c in cases}
    assert seen == {
        CLASS_PRADEEP_EXPLOSIVE, CLASS_MATURE_LEADER, CLASS_EPISODIC_NEGLECT, CLASS_UNCLASSIFIED,
    }
    for c in cases:
        assert classify_setup_class(c) in ALL_CLASSES


# ─── documented tie-break: pradeep_explosive vs mature_leader's stage2 path ────────────────

def test_overlap_pradeep_and_mature_stage2_path_pradeep_wins_first_match():
    """A sub-$2B name that ALSO satisfies mature_leader's Stage-2/near-high/ADV path (no mcap
    floor of its own) AND pradeep_explosive's RVOL/9M/sugar-baby OR-condition: the ADR §2 table
    order is pradeep_explosive, mature_leader, episodic_neglect — this function evaluates in
    that literal order, first-match-wins (documented v1 implementation call, module docstring)."""
    c = {
        "market_cap": 1.5e9,           # < $2B -> pradeep_explosive's mcap gate passes
        "rvol": 5.0,                    # pradeep_explosive OR-condition hit
        "stage2": True,                 # mature_leader's 2nd-path conditions ALSO hold...
        "price": 90.0, "week52_high": 100.0,
        "adv_20_dollar": 200_000_000,
    }
    assert classify_setup_class(c) == CLASS_PRADEEP_EXPLOSIVE


def test_overlap_without_pradeep_trigger_falls_to_mature_leader():
    """Same sub-$2B, stage2/near-high/ADV setup, but WITHOUT any pradeep_explosive trigger —
    correctly resolves to mature_leader (proves the tie-break isn't just 'small caps never
    reach mature_leader', it's specifically about the OR-condition firing)."""
    c = {
        "market_cap": 1.5e9, "rvol": 0.5, "is_9m_same_day": False, "is_sugar_baby_cohort": False,
        "stage2": True, "price": 90.0, "week52_high": 100.0, "adv_20_dollar": 200_000_000,
    }
    assert classify_setup_class(c) == CLASS_MATURE_LEADER


# ─── lookahead-honesty pin ──────────────────────────────────────────────────────────────────

def test_classifier_is_pure_reads_only_the_dict_it_is_given():
    """Static/behavioral pin: classify_setup_class must be pure I/O-free — no DB/network call,
    no clock read, no import of anything that could fetch 'current' data. A historical replay
    handed a dict of STORED fields must get the exact same answer every time, with nothing
    reached for beyond what's in the dict (ADR 0028 §2 field-provenance paragraph)."""
    import inspect
    src = inspect.getsource(classify_setup_class)
    forbidden = ("await ", "conn.", "get_pool", "fetchrow", "fetch(", "datetime.now", "date.today")
    for token in forbidden:
        assert token not in src, f"classify_setup_class must stay pure — found {token!r}"
    # Determinism: same input -> same output, called repeatedly.
    c = {"market_cap": 1.5e9, "rvol": 5.0}
    results = {classify_setup_class(dict(c)) for _ in range(5)}
    assert results == {CLASS_PRADEEP_EXPLOSIVE}


def test_missing_stored_field_classifies_unclassified_never_backfilled():
    """The exact ADR 0028 §2 field-provenance scenario: a historical row stored WITHOUT
    week52_high/upgrades_30d (pre-C1, or a lookup that failed at detection time) must classify
    unclassified — the function has no mechanism to 'reach out' and backfill from current
    data; it only ever sees what's in the candidate dict."""
    c = {"market_cap": 5e9, "price": 50.0}  # week52_high/upgrades_30d absent, not None-filled
    assert classify_setup_class(c) == CLASS_UNCLASSIFIED


# ─── count_recent_upgrades (pure, the #332 2026-07-18 SOURCE REPAIR) ───────────────────────

def test_count_recent_upgrades_counts_only_positive_direction_action():
    events = [
        {"date": date(2026, 7, 1), "action": "up"},
        {"date": date(2026, 7, 5), "action": "down"},
        {"date": date(2026, 7, 10), "action": "main"},   # reiteration — not counted
        {"date": date(2026, 7, 12), "action": "init"},   # initiation — not counted
        {"date": date(2026, 7, 15), "action": "Up"},     # case-insensitive
    ]
    assert count_recent_upgrades(events, date(2026, 7, 18)) == 2


def test_count_recent_upgrades_window_is_30_calendar_days_and_lookahead_honest():
    """Mirrors the #332 backtest probe's validated window exactly: `lo < d <= as_of` where
    `lo = as_of - 30d` — the lower bound is EXCLUSIVE (exactly 30 days ago is just outside),
    the upper bound is INCLUSIVE of same-day, and anything strictly after as_of (a future
    event relative to the alert) is excluded — the lookahead-honesty guarantee."""
    as_of = date(2026, 7, 18)
    events = [
        {"date": as_of - timedelta(days=31), "action": "up"},  # too old: excluded
        {"date": as_of - timedelta(days=30), "action": "up"},  # exactly 30d ago: excluded (lo < d)
        {"date": as_of - timedelta(days=29), "action": "up"},  # just inside: included
        {"date": as_of, "action": "up"},                       # same-day: included
        {"date": as_of + timedelta(days=1), "action": "up"},   # FUTURE: excluded (lookahead)
    ]
    assert count_recent_upgrades(events, as_of) == 2


def test_count_recent_upgrades_none_events_is_unknown_not_zero():
    """A fetch failure (None) must propagate as None ('unknown'), never masquerade as a
    confirmed zero — the exact failure mode that made the OLD dead feed vacuous."""
    assert count_recent_upgrades(None, date(2026, 7, 18)) is None


def test_count_recent_upgrades_empty_list_is_a_real_zero():
    assert count_recent_upgrades([], date(2026, 7, 18)) == 0


# ─── The discrimination re-verification (#332, 2026-07-18) ────────────────────────────────
# The whole point of the source repair: under the OLD dead feed, EVERY ticker read
# upgrades_30d == 0 (vacuous). The NEW source must actually DISCRIMINATE — a coverage-heavy
# name must NOT read 0, and a genuinely-uncovered name still can.

def test_discrimination_coverage_heavy_name_does_not_read_zero_upgrades():
    """NVDA-shaped: heavy, recent, real upgrade activity -> upgrades_30d != 0 -> correctly
    EXCLUDED from episodic_neglect (even placed in-band on mcap/price to isolate the
    upgrades_30d cut specifically, since real NVDA's mcap alone would already route it to
    mature_leader regardless)."""
    nvda_like_events = [
        {"date": date(2026, 7, 2), "action": "up"},
        {"date": date(2026, 7, 9), "action": "up"},
        {"date": date(2026, 7, 15), "action": "up"},
    ]
    upgrades_30d = count_recent_upgrades(nvda_like_events, date(2026, 7, 18))
    assert upgrades_30d == 3 and upgrades_30d != 0
    candidate = {
        "market_cap": 5e9, "price": 60.0, "week52_high": 100.0,  # in-band, otherwise-neglect-shaped
        "upgrades_30d": upgrades_30d,
    }
    assert classify_setup_class(candidate) != CLASS_EPISODIC_NEGLECT
    assert classify_setup_class(candidate) == CLASS_UNCLASSIFIED  # no recent-upgrade signal blocks it

    # Real NVDA itself: mega-cap routes to mature_leader on mcap alone, upgrades irrelevant.
    real_nvda = {"market_cap": 3.3e12, "price": 180.0, "week52_high": 200.0, "upgrades_30d": 12}
    assert classify_setup_class(real_nvda) == CLASS_MATURE_LEADER
    assert classify_setup_class(real_nvda) != CLASS_EPISODIC_NEGLECT


def test_discrimination_genuinely_uncovered_smallcap_can_be_episodic_neglect():
    """A genuinely-uncovered small/mid-cap (no upgrade events at all) still classifies
    episodic_neglect — the repair doesn't make the class unreachable, just non-vacuous."""
    upgrades_30d = count_recent_upgrades([], date(2026, 7, 18))
    assert upgrades_30d == 0
    candidate = {
        "market_cap": 3e9, "price": 40.0, "week52_high": 100.0, "upgrades_30d": upgrades_30d,
    }
    assert classify_setup_class(candidate) == CLASS_EPISODIC_NEGLECT


# ─── compute_setup_class_fields (async assembler) ──────────────────────────────────────────

def _patch_upgrade_events(monkeypatch, events):
    async def _fake(_ticker):
        return events
    monkeypatch.setattr(
        "agents.market_intelligence.setup_class_classifier.get_recent_upgrade_events", _fake)


def test_assembler_pulls_threaded_fields_from_r_and_counts_repaired_upgrades(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    _patch_upgrade_events(monkeypatch, [
        {"date": date(2026, 7, 1), "action": "up"},
        {"date": date(2026, 7, 10), "action": "up"},
    ])
    r = {
        "ticker": "TICK", "alert_date": date(2026, 7, 18),
        "market_cap": 3e9, "rel_volume": 4.0, "current_price": 42.0,
        "week52_high": 60.0,
    }
    fields = _run(compute_setup_class_fields(conn, r))
    assert fields["market_cap"] == 3e9
    assert fields["rvol"] == 4.0
    assert fields["price"] == 42.0
    assert fields["week52_high"] == 60.0
    assert fields["upgrades_30d"] == 2  # from the REPAIRED source, not r.get("upgrades_30d")


def test_assembler_no_longer_reads_upgrades_30d_off_r(monkeypatch):
    """#332 2026-07-18: upgrades_30d must come ONLY from the repaired fetch — a stale/irrelevant
    value sitting on `r` (e.g. leftover from an old code path) must be ignored."""
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=None)
    _patch_upgrade_events(monkeypatch, [])
    r = {
        "ticker": "TICK", "alert_date": date(2026, 7, 18),
        "market_cap": 3e9, "current_price": 42.0, "week52_high": 60.0,
        "upgrades_30d": 999,  # must be IGNORED
    }
    fields = _run(compute_setup_class_fields(conn, r))
    assert fields["upgrades_30d"] == 0


def test_assembler_missing_ticker_or_alert_date_skips_all_lookups():
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(side_effect=AssertionError("must not be called"))
    fields = _run(compute_setup_class_fields(conn, {"ticker": None, "alert_date": date(2026, 7, 18)}))
    assert fields["stage2"] is None
    assert fields["is_9m_same_day"] is False
    assert fields["is_sugar_baby_cohort"] is False
    assert fields["adv_20_dollar"] is None
    assert fields["upgrades_30d"] is None


def test_assembler_one_lookup_failing_does_not_blank_the_others(monkeypatch):
    """A sugar-baby query hiccup must not stop the 9M/stage2/ADV/upgrades fields from still
    resolving — each lookup is independently guarded."""
    pool, conn = make_mock_pool()

    async def _bars(_conn, _ticker, _alert_date, days=380):
        return []
    monkeypatch.setattr(
        "agents.market_intelligence.setup_class_classifier.get_daily_bars_asof", _bars)

    async def _nine_m(_conn, _ticker, _alert_date):
        return True
    monkeypatch.setattr(
        "agents.market_intelligence.setup_class_classifier.get_9m_alert_same_day", _nine_m)

    async def _sugar_boom(_conn, _ticker, _alert_date):
        raise RuntimeError("db hiccup")
    monkeypatch.setattr(
        "agents.market_intelligence.setup_class_classifier.get_sugar_baby_cohort_member_asof",
        _sugar_boom)

    async def _adv(_conn, _ticker, _alert_date, price, days=20):
        return 200_000_000.0
    monkeypatch.setattr(
        "agents.market_intelligence.setup_class_classifier.get_adv_20_dollar_asof", _adv)

    _patch_upgrade_events(monkeypatch, [{"date": date(2026, 7, 5), "action": "up"}])

    r = {
        "ticker": "TICK", "alert_date": date(2026, 7, 18),
        "market_cap": 1.5e9, "rel_volume": 1.0, "current_price": 10.0,
    }
    fields = _run(compute_setup_class_fields(conn, r))
    assert fields["is_9m_same_day"] is True         # unaffected by the sugar-baby failure
    assert fields["is_sugar_baby_cohort"] is False   # safe default on failure, never a guess
    assert fields["adv_20_dollar"] == 200_000_000.0  # unaffected
    assert fields["stage2"] is None                 # empty bars -> uncomputable, not a guess
    assert fields["upgrades_30d"] == 1               # unaffected


def test_assembler_upgrade_fetch_failure_does_not_blank_the_others(monkeypatch):
    """The mirror case: a yfinance upgrade-events fetch failure must not stop the DB-backed
    fields from resolving."""
    pool, conn = make_mock_pool()

    async def _bars(_conn, _ticker, _alert_date, days=380):
        return []
    monkeypatch.setattr(
        "agents.market_intelligence.setup_class_classifier.get_daily_bars_asof", _bars)

    async def _nine_m(_conn, _ticker, _alert_date):
        return True
    monkeypatch.setattr(
        "agents.market_intelligence.setup_class_classifier.get_9m_alert_same_day", _nine_m)

    async def _sugar(_conn, _ticker, _alert_date):
        return False
    monkeypatch.setattr(
        "agents.market_intelligence.setup_class_classifier.get_sugar_baby_cohort_member_asof",
        _sugar)

    async def _adv(_conn, _ticker, _alert_date, price, days=20):
        return 50_000_000.0
    monkeypatch.setattr(
        "agents.market_intelligence.setup_class_classifier.get_adv_20_dollar_asof", _adv)

    async def _upgrade_boom(_ticker):
        raise RuntimeError("yfinance unreachable")
    monkeypatch.setattr(
        "agents.market_intelligence.setup_class_classifier.get_recent_upgrade_events",
        _upgrade_boom)

    r = {
        "ticker": "TICK", "alert_date": date(2026, 7, 18),
        "market_cap": 1.5e9, "rel_volume": 1.0, "current_price": 10.0,
    }
    fields = _run(compute_setup_class_fields(conn, r))
    assert fields["upgrades_30d"] is None      # unknown on failure, never a guessed 0
    assert fields["is_9m_same_day"] is True    # unaffected
    assert fields["adv_20_dollar"] == 50_000_000.0  # unaffected
