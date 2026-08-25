"""`scripts/probes/_structure_read_v2.py` — the shadow supply-ladder structure read.

WHY THESE TESTS EXIST. The measure is SHADOW and drives nothing, but the numbers in
`docs/analysis/structure_read_v2_2026-08-25.md` are only worth reading if two things hold:

  1. **The reused level derivation still reproduces the operator's own labelled levels.**
     `_structure_read_v2` imports `pivot_levels` / `sma50_level` from
     `_533_nbis_structure_encoder` and feeds them through a dict->tuple adapter. An adapter
     bug silently produces garbage levels and every ladder number downstream is meaningless.
     `test_parity_*` pins the four level values `docs/methodology/structure_model.md` §4
     documents (NBIS 226.81 · EROC 11.88 · SE 118.09 · FRMI's 50-day 7.06).
  2. **The gap-zone arithmetic is right.** Fill tracking is where the off-by-one lives, so
     every case is a hand-built bar series with the answer computable by eye: a clean
     vacuum, a fully filled one, a partially filled one, and the up-gap direction.

Plus the no-lookahead guard, which is the one thing that would corrupt the study invisibly
(the 08-25 capture rows are partial-day and physically present in the same files).

No DB, no network, no Alpaca, no LLM — pure arithmetic over literal bars.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from scripts.probes import _structure_read_v2 as V2


def _bars(rows, start=date(2026, 1, 5)):
    """rows = [(open, high, low, close, volume)] on consecutive (fake) sessions."""
    return [{"trade_date": start + timedelta(days=i), "open_price": o, "high_price": h,
             "low_price": lo, "close": c, "volume": v}
            for i, (o, h, lo, c, v) in enumerate(rows)]


# ── the reused level derivation, through this module's adapter ────────────────────────
def test_parity_reproduces_the_four_documented_levels():
    rows = V2.parity_check(verbose=False)
    bad = [(nm, got, want) for nm, ok, got, want in rows if not ok]
    assert not bad, f"reused level derivation drifted from structure_model.md §4: {bad}"
    assert len(rows) == 4


# ── gap zones ─────────────────────────────────────────────────────────────────────────
def test_clean_unfilled_gap_down_is_one_untouched_vacuum():
    #                    day 0 trades 10-12, day 1 trades 6-7 -> vacuum (7, 10), never revisited
    bars = _bars([(11, 12, 10, 11, 100), (6.5, 7, 6, 6.5, 100), (6.5, 7, 6, 6.5, 100)])
    zs = V2.gap_zones(bars)
    assert len(zs) == 1
    z = zs[0]
    assert z["direction"] == "down"
    assert z["bottom"] == pytest.approx(7.0) and z["top"] == pytest.approx(10.0)
    assert z["unfilled"] == [(pytest.approx(7.0), pytest.approx(10.0))]
    assert z["unfilled_span"] == pytest.approx(3.0)
    assert z["filled_frac"] == pytest.approx(0.0)


def test_a_later_session_that_covers_the_vacuum_fills_it_completely():
    bars = _bars([(11, 12, 10, 11, 100), (6.5, 7, 6, 6.5, 100), (6.5, 11, 6.5, 10.5, 100)])
    z = V2.gap_zones(bars)[0]
    assert z["unfilled"] == []
    assert z["unfilled_span"] == pytest.approx(0.0)
    assert z["filled_frac"] == pytest.approx(1.0)


def test_a_partial_fill_leaves_exactly_the_untraded_remnant():
    # vacuum (7, 10); a later session trades 6.5-8.5 -> only (8.5, 10) is still untraded
    bars = _bars([(11, 12, 10, 11, 100), (6.5, 7, 6, 6.5, 100), (7, 8.5, 6.5, 8, 100)])
    z = V2.gap_zones(bars)[0]
    assert z["unfilled"] == [(pytest.approx(8.5), pytest.approx(10.0))]
    assert z["unfilled_span"] == pytest.approx(1.5)
    assert z["filled_frac"] == pytest.approx(0.5)


def test_a_fill_from_the_middle_can_leave_two_remnants():
    # vacuum (7, 12); a later session trades only 9-10 -> remnants (7,9) and (10,12)
    bars = _bars([(13, 14, 12, 13, 100), (6.5, 7, 6, 6.5, 100), (9, 10, 9, 9.5, 100)])
    z = V2.gap_zones(bars)[0]
    assert [(round(a, 4), round(b, 4)) for a, b in z["unfilled"]] == [(7.0, 9.0), (10.0, 12.0)]
    assert z["unfilled_span"] == pytest.approx(4.0)


def test_gap_up_is_detected_in_its_own_direction():
    bars = _bars([(5, 6, 4, 5.5, 100), (8, 9, 7, 8.5, 100)])
    z = V2.gap_zones(bars)[0]
    assert z["direction"] == "up"
    assert (z["bottom"], z["top"]) == (pytest.approx(6.0), pytest.approx(7.0))


def test_touching_ranges_are_not_a_gap():
    # day 1's high equals day 0's low — contiguous, no vacuum
    bars = _bars([(11, 12, 10, 11, 100), (9, 10, 9, 9.5, 100)])
    assert V2.gap_zones(bars) == []


# ── volume at price ───────────────────────────────────────────────────────────────────
def test_overhead_volume_fraction_is_zero_in_blue_sky_and_one_when_buried():
    bars = _bars([(10, 12, 10, 11, 100), (10, 12, 10, 11, 100)])
    assert V2.overhead_volume_fraction(bars, 20.0) == pytest.approx(0.0)
    assert V2.overhead_volume_fraction(bars, 5.0) == pytest.approx(1.0)


def test_overhead_volume_fraction_splits_a_straddled_session_pro_rata():
    # one session 10-20 with 100 shares; half its range sits above 15
    bars = _bars([(10, 20, 10, 15, 100)])
    assert V2.overhead_volume_fraction(bars, 15.0) == pytest.approx(0.5)


def test_overhead_volume_fraction_weights_by_volume_not_by_session_count():
    bars = _bars([(10, 20, 10, 15, 900),      # 900 shares, all above 5
                  (1, 2, 1, 1.5, 100)])       # 100 shares, all below 5
    assert V2.overhead_volume_fraction(bars, 5.0) == pytest.approx(0.9)


# ── the gap-robust tightness claim, at N=1 ────────────────────────────────────────────
def test_a_base_with_a_vacuum_in_it_reads_wider_than_the_same_base_without():
    """The operator's objection made mechanical: two bases whose sessions have the SAME
    intraday ranges, one of which contains a gap. `base_range_adr` must see the gap."""
    quiet = _bars([(10, 10.5, 9.5, 10, 100)] * 20)
    gapped = _bars([(10, 10.5, 9.5, 10, 100)] * 10 + [(6, 6.5, 5.5, 6, 100)] * 10)
    adr_q, adr_g = V2.adr20(quiet), V2.adr20(gapped)
    tq = V2.base_tightness(quiet, adr_q)
    tg = V2.base_tightness(gapped, adr_g)
    assert tq["base_range_adr"] == pytest.approx(0.0, abs=1e-9)
    assert tg["base_range_adr"] > 3.0
    assert tq["base_gap_count_1p0x"] == 0
    assert tg["base_gap_count_1p0x"] == 1


# ── the no-lookahead guard ────────────────────────────────────────────────────────────
def test_a_bar_dated_on_the_alert_day_is_rejected_not_silently_used():
    bars = _bars([(10, 11, 9, 10, 100)] * 30, start=date(2026, 1, 5))
    alert = bars[-1]["trade_date"]          # the last bar IS the alert day — must raise
    with pytest.raises(AssertionError, match="lookahead"):
        V2.structure_read_v2(bars, alert, 11.0)


def test_a_clean_prior_only_series_computes_and_reports_its_own_history_depth():
    bars = _bars([(10, 11, 9, 10, 100)] * 30)
    out = V2.structure_read_v2(bars, bars[-1]["trade_date"] + timedelta(days=1), 12.0)
    assert out["reason"] is None
    assert out["n_bars"] == 30
    assert out["overhead_vol_frac"] == pytest.approx(0.0)     # 12 is above every prior high
    assert out["thin_history"] is False


def test_a_very_short_history_says_so_instead_of_returning_a_number():
    bars = _bars([(10, 11, 9, 10, 100)] * 5)
    out = V2.structure_read_v2(bars, bars[-1]["trade_date"] + timedelta(days=1), 12.0)
    assert out["reason"].startswith("history_too_thin")
    assert "overhead_vol_frac" not in out
