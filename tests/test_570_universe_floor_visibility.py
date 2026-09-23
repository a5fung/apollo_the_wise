"""#570 (remaining half, 2026-08-22) — the two silent D-1 universe floors now log a
skip_reason like every other gate.

Card: `docs/analysis/silent_universe_floors_570_2026-08-22.md`. The measurement half
(DoD b) is done; this is the logging half (DoD a): `MIN_PREV_CLOSE` ($5, applied
`ep_detector.py`'s snapshot loop) and `MIN_PREV_DAY_VOLUME` (50k shares, same loop)
previously dropped a candidate with NO row, NO skip_reason, NO scan_log line anywhere
— the only exclusions in the whole EP pipeline that left no trace. VALUES UNCHANGED
(THE LINE); this only makes the rejection visible.

What's pinned here:
  1. `_universe_floor_skip` (the pure helper `run_ep_scan`'s loop calls) — admit/reject
     shape, including the "would-be candidate" gate (only log when the gap would
     otherwise have cleared today's Pass-1 floor — matches #570's own "26.5/day
     silently dropped" population, not the whole non-gapping market) and the "no
     data" edge case (missing prevDay must return None, not a bogus "$0.00" row).
  2. Mutation-proof: raising the would-be-candidate gate flips a case that logs at
     the default floor to NOT logging — proves the gate isn't vacuous.
  3. The two new `broker/skip_reasons.py` constants are wired into `humanize()`.
  4. Source-inspection pins on `run_ep_scan`: both floor branches call the helper,
     and the flush happens BEFORE `if not candidates: return []` (else a tick with
     zero real candidates would silently drop the floor-skip rows too — the exact
     invisibility this card exists to end).
  5. `missed_outcomes._categorize_skip_reason` buckets the new reasons into their
     own `d1_universe_floor` category (not the catch-all `filter_other`), and that
     category is registered as `structural` / hidden-by-default the same way the
     other correctly-filtered universe floors already are.
  6. The morning-briefing surface (`briefing._format_ep_section`) explicitly
     excludes the new class from "gap candidates scanned" and the 5-slot
     near-miss line — it outnumbers the real candidate pool ~2:1 and would drown
     genuine near-misses in an AUTO-PUSHED digest (unlike `/setup TICKER` / EP
     scan history / `mi_ep_missed_outcomes`, which are on-demand and should show it).
"""
from __future__ import annotations

import inspect

from agents.market_intelligence import ep_detector
from agents.market_intelligence import briefing
from agents.market_intelligence import missed_outcomes
from agents.market_intelligence.broker.skip_reasons import (
    FILTER_UNIVERSE_PREV_CLOSE_TOO_LOW,
    FILTER_UNIVERSE_PREV_DAY_ILLIQUID,
    humanize,
)

_PREV_CLOSE_OK = 10.0
_PREV_VOLUME_OK = 100_000


def _pin_default_floor(monkeypatch):
    """Pin the live Pass-1 gap floor to the operator-ruled default (9.0%, Pass-2 off),
    immune to env overrides — same pattern test_577_min_gap_pct_9pct.py uses."""
    monkeypatch.setattr(ep_detector, "EP_RT_PASS2_ENABLED", False)
    monkeypatch.setattr(ep_detector, "MIN_GAP_PCT", ep_detector._MIN_GAP_PCT_DEFAULT)


# ── the pure helper: admit/reject shape ──────────────────────────────────────────────

def test_both_floors_clear_returns_none(monkeypatch):
    _pin_default_floor(monkeypatch)
    out = ep_detector._universe_floor_skip(
        "GOOD", _PREV_CLOSE_OK, _PREV_VOLUME_OK, current_price=_PREV_CLOSE_OK * 1.20)
    assert out is None


def test_prev_close_floor_fail_logs_with_correct_reason(monkeypatch):
    _pin_default_floor(monkeypatch)
    # $3 prior close, gaps to $4.50 -> +50%, well clear of the 9% floor
    out = ep_detector._universe_floor_skip(
        "CHEAP", prev_close=3.0, prev_volume=_PREV_VOLUME_OK, current_price=4.50)
    assert out is not None
    assert out["ticker"] == "CHEAP"
    assert out["filter_reason"].startswith(FILTER_UNIVERSE_PREV_CLOSE_TOO_LOW)
    assert "3.00" in out["filter_reason"] and "5.00" in out["filter_reason"]
    assert abs(out["gap_pct"] - 50.0) < 1e-6


def test_prev_volume_floor_fail_logs_with_correct_reason(monkeypatch):
    _pin_default_floor(monkeypatch)
    out = ep_detector._universe_floor_skip(
        "ILLIQUID", prev_close=_PREV_CLOSE_OK, prev_volume=49_999, current_price=_PREV_CLOSE_OK * 1.30)
    assert out is not None
    assert out["filter_reason"].startswith(FILTER_UNIVERSE_PREV_DAY_ILLIQUID)
    assert "49,999" in out["filter_reason"] and "50,000" in out["filter_reason"]


def test_prev_close_floor_checked_before_volume_floor(monkeypatch):
    """Both floors fail — the close floor is the one that must win (matches the
    loop's own order: the close check runs first and `continue`s before the
    volume check is ever reached)."""
    _pin_default_floor(monkeypatch)
    out = ep_detector._universe_floor_skip(
        "BOTHFAIL", prev_close=2.0, prev_volume=100, current_price=3.0)
    assert out["filter_reason"].startswith(FILTER_UNIVERSE_PREV_CLOSE_TOO_LOW)


def test_gap_below_floor_not_logged_even_though_it_fails_a_floor(monkeypatch):
    """The would-be-candidate gate: a sub-$5 ticker that barely moves must NOT be
    logged — it was never going to be a real candidate regardless of the D-1
    floor, and unconditioned logging would flood scan_log with the whole
    sub-$5/illiquid market (the same reasoning the P2.0b unclassified fail-safe
    already applies one gate up)."""
    _pin_default_floor(monkeypatch)
    out = ep_detector._universe_floor_skip(
        "FLAT", prev_close=3.0, prev_volume=_PREV_VOLUME_OK, current_price=3.10)  # +3.3%, < 9%
    assert out is None


def test_missing_current_price_returns_none(monkeypatch):
    """Row 6 of the #570 analysis table: no current price = data availability, not
    policy — must not be conflated with a floor rejection."""
    _pin_default_floor(monkeypatch)
    out = ep_detector._universe_floor_skip(
        "NODATA", prev_close=2.0, prev_volume=100, current_price=None)
    assert out is None
    out2 = ep_detector._universe_floor_skip(
        "NODATA2", prev_close=2.0, prev_volume=100, current_price=0)
    assert out2 is None


def test_missing_prev_close_returns_none_not_a_bogus_row(monkeypatch):
    """prev_close=0 (no prevDay bar at all) must not synthesize a '$0.00 < $5.00'
    row — the gap can't be computed, so this is the same 'no data' case as a
    missing current price, not a real floor rejection."""
    _pin_default_floor(monkeypatch)
    out = ep_detector._universe_floor_skip(
        "NOPREVCLOSE", prev_close=0, prev_volume=100, current_price=10.0)
    assert out is None


# ── mutation-proof: the would-be-candidate gate is real, not vacuous ────────────────

def test_mutation_proof_raising_the_gate_flips_flat_case_to_still_none_but_edge_case_flips():
    """At a much lower Pass-1 floor (1%), the same 'FLAT' candidate from the test
    above (+3.3%) now clears it and MUST be logged — proving the gate in
    `_universe_floor_skip` is actually reading `_pass1_gap_floor()` live, not a
    hardcoded/vacuous condition."""
    import agents.market_intelligence.ep_detector as ed
    orig_pass2 = ed.EP_RT_PASS2_ENABLED
    orig_min_gap = ed.MIN_GAP_PCT
    try:
        ed.EP_RT_PASS2_ENABLED = False
        ed.MIN_GAP_PCT = 1.0
        out = ed._universe_floor_skip(
            "FLAT", prev_close=3.0, prev_volume=_PREV_VOLUME_OK, current_price=3.10)  # +3.3%
        assert out is not None, "at a 1% floor, a +3.3% gap must now be logged"
    finally:
        ed.EP_RT_PASS2_ENABLED = orig_pass2
        ed.MIN_GAP_PCT = orig_min_gap


# ── humanize() wiring ─────────────────────────────────────────────────────────────

def test_humanize_wires_both_new_reasons():
    close_reason = f"{FILTER_UNIVERSE_PREV_CLOSE_TOO_LOW}: prior close $3.00 < $5.00 floor"
    vol_reason = f"{FILTER_UNIVERSE_PREV_DAY_ILLIQUID}: prior-day volume 100 < 50,000 shares floor"
    close_h = humanize(close_reason)
    vol_h = humanize(vol_reason)
    assert close_h != close_reason  # got the human label, not a raw passthrough
    assert "5 universe floor" in close_h
    assert vol_h != vol_reason
    assert "50k-share universe floor" in vol_h


# ── source-inspection pins on run_ep_scan (test_347/test_577 pattern) ───────────────

def test_run_ep_scan_calls_universe_floor_skip_on_both_branches():
    src = inspect.getsource(ep_detector.run_ep_scan)
    # Both the close-floor branch and the volume-floor branch must call the helper.
    close_idx = src.index("prev_close < MIN_PREV_CLOSE")
    volume_idx = src.index("prev_volume < MIN_PREV_DAY_VOLUME")
    helper_calls = [i for i in _all_indices(src, "_universe_floor_skip(ticker")]
    assert len(helper_calls) >= 2, "expected a call at both the close and volume floor sites"
    assert any(close_idx < i < close_idx + 400 for i in helper_calls), \
        "close-floor branch must call _universe_floor_skip"
    assert any(volume_idx < i < volume_idx + 400 for i in helper_calls), \
        "volume-floor branch must call _universe_floor_skip"


def test_flush_happens_before_the_empty_candidates_early_return():
    """The load-bearing ordering bug this design avoids: `if not candidates: return
    []` must come AFTER the #570 flush, or a tick with zero real candidates would
    silently drop every floor-skip row that tick — reproducing the exact
    invisibility this card exists to end."""
    src = inspect.getsource(ep_detector.run_ep_scan)
    flush_idx = src.index("log_ep_scan_candidates([")
    return_idx = src.index("if not candidates:\n        return []")
    assert flush_idx < return_idx, \
        "the #570 visibility flush must be emitted before the empty-candidates early return"


def _all_indices(haystack: str, needle: str):
    start = 0
    while True:
        i = haystack.find(needle, start)
        if i == -1:
            return
        yield i
        start = i + 1


# ── missed_outcomes.py categorization ────────────────────────────────────────────

def test_categorize_skip_reason_buckets_both_new_reasons():
    close_reason = f"{FILTER_UNIVERSE_PREV_CLOSE_TOO_LOW}: prior close $3.00 < $5.00 floor"
    vol_reason = f"{FILTER_UNIVERSE_PREV_DAY_ILLIQUID}: prior-day volume 100 < 50,000 shares floor"
    assert missed_outcomes._categorize_skip_reason("scan_filter", close_reason) == "d1_universe_floor"
    assert missed_outcomes._categorize_skip_reason("scan_filter", vol_reason) == "d1_universe_floor"


def test_d1_universe_floor_is_structural_and_untradeable():
    """Matches the treatment of the OTHER correctly-filtered universe floors
    (mcap_low, adv_low, atr_high, extension_gate) — hidden from the default
    /missed view, visible via /missed all. Not a should've-entered miss."""
    assert "d1_universe_floor" in missed_outcomes._UNTRADEABLE_CATEGORIES
    assert missed_outcomes._CATEGORY_KIND["d1_universe_floor"] == "structural"
    assert "d1_universe_floor" not in missed_outcomes._SHOULDVE_ENTERED_CATEGORIES


# ── operator-facing surface: excluded from the morning-briefing digest ──────────────

def test_briefing_excludes_universe_floor_class_from_scan_count():
    scan_log = [
        {"ticker": "REALFILT", "filter_reason": "EP cooldown — alerted within last 60 days",
         "gap_pct": 12.0},
        {"ticker": "FLOORHIT", "filter_reason":
            f"{FILTER_UNIVERSE_PREV_CLOSE_TOO_LOW}: prior close $3.00 < $5.00 floor", "gap_pct": 25.0},
    ]
    out = briefing._format_ep_section([], section_num=1, scan_log=scan_log)
    # Only the real filtered candidate counts toward "gap candidates scanned".
    assert "(1 gap candidates scanned)" in out
    assert "FLOORHIT" not in out


def test_briefing_near_miss_line_excludes_universe_floor_rows():
    scan_log = [
        {"ticker": f"FLOOR{i}", "filter_reason":
            f"{FILTER_UNIVERSE_PREV_DAY_ILLIQUID}: prior-day volume {i} < 50,000 shares floor",
         "gap_pct": 15.0}
        for i in range(10)
    ]
    out = briefing._format_ep_section([], section_num=1, scan_log=scan_log)
    assert "Near misses" not in out  # the only candidates were the excluded class
