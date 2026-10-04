"""#391 coil-finder unit tests — anticipation.find_coil_setup.

The detector: RUNUP (>=15% leg) -> consolidation give-back (retrace of the runup leg) -> recent-coil
tightness. The HOLD gate (<= COIL_HOLD_LIMIT) is applied by the JOB, not the detector, so these tests
assert the detector RETURNS the retrace and the job's filter would act on it.
"""
import logging
from datetime import date, timedelta

import pytest

from agents.market_intelligence.anticipation import (
    find_coil_setup, evaluate_coil_consolidation, coil_pin_reject_reason, COIL_HOLD_LIMIT,
    db_rows_to_bars, format_consolidation_row, format_orderliness, orderliness_score,
)

_D0 = date(2026, 1, 1)


def _bars(closes, *, hl_frac=0.01):
    """Replay bars from a close series; h/l a tight +/-hl_frac band around each close."""
    return [{
        "date": (_D0 + timedelta(days=k)).isoformat(),
        "o": c, "h": c * (1 + hl_frac), "l": c * (1 - hl_frac), "c": c, "v": 1_000_000.0,
    } for k, c in enumerate(closes)]


_BASE = [100.0] * 30                                   # prior swing-low region
_RUNUP = [100.0 + 3.0 * (k + 1) for k in range(10)]    # 103..130 (a +30% leg; peak = 130 at idx 39)


def _series(coil_close):
    return _bars(_BASE + _RUNUP + [coil_close] * 15)   # 55 bars; peak idx 39, consolidation idx 40..54


def test_shallow_hold_tight_coil_is_found():
    bars = _series(125.0)                              # holds ~125 of the 100->130 leg (shallow give-back)
    s = find_coil_setup(bars, len(bars) - 1)
    assert s is not None
    assert s["peak_date"] == bars[39]["date"]         # the runup top, not a coil bar
    assert s["runup"] > 1.15
    assert s["retrace"] <= COIL_HOLD_LIMIT            # held the runup -> the job keeps it
    assert s["band"] < 0.05                           # tight coil


def test_deep_pullback_exceeds_hold_limit():
    bars = _series(108.0)                              # gives back most of the 100->130 leg
    s = find_coil_setup(bars, len(bars) - 1)
    # the runup is real so the detector still returns a setup; the JOB's filter drops it on retrace
    assert s is None or s["retrace"] > COIL_HOLD_LIMIT


def test_no_runup_flat_series_is_none():
    bars = _bars([100.0] * 55)                         # flat -> no >=15% leg
    assert find_coil_setup(bars, len(bars) - 1) is None


# ── evaluate_coil_consolidation: the LIVE #327 base detector (coil-finder + hold gate +
#    consolidation-shaped output anchored on the corrected coil peak) ──

def test_evaluate_coil_consolidation_held_coil_returns_row_anchored_on_peak():
    bars = _series(125.0)                              # shallow hold of the 100->130 leg
    row, reject_reason = evaluate_coil_consolidation(bars)
    assert row is not None
    assert reject_reason is None
    assert row["anchor_date"] == bars[39]["date"]      # anchored on the runup PEAK, not a coil bar
    assert row["runup_ratio"] > 1.15
    assert row["state"] in ("coiled", "post_runup", "aged")
    assert row["hold_retrace"] <= COIL_HOLD_LIMIT
    # consolidation-shaped: the fields upsert_consolidation + the board consume are present
    for key in ("runup_high", "coil_days", "last_close", "rmv_15d", "pullback_shape",
                "fresh_tightening", "tight_close_streak"):
        assert key in row


def test_evaluate_coil_consolidation_deep_pullback_is_none():
    bars = _series(108.0)                              # gave back > half the leg -> hold gate drops it
    row, reject_reason = evaluate_coil_consolidation(bars)
    assert row is None
    assert reject_reason is None                       # plain miss, not a pin-guard reject


def test_evaluate_coil_consolidation_no_runup_is_none():
    row, reject_reason = evaluate_coil_consolidation(_bars([100.0] * 55))
    assert row is None
    assert reject_reason is None


# ── #410 buyout/deal-PIN shape guard — NUVL 6/30 FP: gapped ~37% to the acquisition price and
#    flatlined; the coil-finder read the post-deal PIN as a tight coil (buy 123.50/stop 123.43 =
#    0.06% stop distance, the giveaway). ────────────────────────────────────────────────────────

def test_normal_coil_is_not_pin_rejected():
    """Sanity: the existing organic-coil fixture (shallow hold, ~1% daily range) must NOT trip the
    buyout-pin guard — the guard only fires on the deal-pin flatness signature (<0.5% median range)."""
    bars = _series(125.0)
    coil = find_coil_setup(bars, len(bars) - 1)
    assert coil is not None
    assert coil_pin_reject_reason(bars, coil) is None
    row, reject_reason = evaluate_coil_consolidation(bars)
    assert row is not None   # unaffected — still a valid candidate
    assert reject_reason is None


def _nuvl_series():
    """Buyout-PIN fixture (NUVL 6/30-shaped): 40 flat days at 100 (pre-deal base), ONE gap day to
    137 (+37%, the entire leg lands in a SINGLE bar — a deal-price jump, not an organic runup),
    then 15 near-dead-flat days at 137 (the post-deal PIN, hl_frac=0.0003 -> ~0.06% daily range,
    matching NUVL's actual buy 123.50/stop 123.43 giveaway)."""
    closes = [100.0] * 40 + [137.0] * 16   # index 40 = the gap day; 41..55 = the 15-day flat PIN
    return _bars(closes, hl_frac=0.0003)


def test_buyout_pin_gap_to_flat_rejected():
    bars = _nuvl_series()
    coil = find_coil_setup(bars, len(bars) - 1)
    assert coil is not None                       # a real runup->coil STRUCTURE is found...
    assert coil["retrace"] <= COIL_HOLD_LIMIT      # ...and it "held" — deceptively: it's the deal pin
    assert coil_pin_reject_reason(bars, coil) == "gap_to_flat"
    # the qualifier rejects it outright — NOT a silent drop; evaluate_coil_consolidation now
    # RETURNS this exact reason (no re-derivation) so the job layer (scheduler.
    # _consolidation_readiness_job) can audit it (anticipation_coil_buyout_pin_rejected) rather
    # than letting it surface as a false coil.
    row, reject_reason = evaluate_coil_consolidation(bars)
    assert row is None
    assert reject_reason == "gap_to_flat"


def test_buyout_pin_stop_floor_rejected_without_single_bar_gap():
    """A pin that reads flat (<0.5% range) but whose runup was an ORGANIC multi-day climb (not a
    single-bar gap) still trips the guard — via the plain stop_floor reason, not gap_to_flat."""
    base = [100.0] * 30
    runup = [100.0 + 3.0 * (k + 1) for k in range(10)]   # 103..130, a +30% MULTI-DAY leg
    closes = base + runup + [129.5] * 15                  # flat pin just under the peak
    bars = _bars(closes, hl_frac=0.0003)
    coil = find_coil_setup(bars, len(bars) - 1)
    assert coil is not None
    assert coil["retrace"] <= COIL_HOLD_LIMIT
    assert coil_pin_reject_reason(bars, coil) == "stop_floor"
    row, reject_reason = evaluate_coil_consolidation(bars)
    assert row is None
    assert reject_reason == "stop_floor"


# ══ #394 C2 Phase 1 — the ORDERLINESS score: recorded on the coil row, shown on the board line ══
# Operator ruling 2026-10-03 on the C1 tune tables: "Sign" — keep the 50% cap, keep the board order,
# NO orderliness demotion → display only (method docs/analysis/394_coil_tuning_methodology_2026-07-11.md
# §3c Phase 1). Here: the definition on hand cases, that evaluate_coil_consolidation carries it and is
# otherwise IDENTICAL whether or not it works, and the plain-words line. The probe-identity pin is in
# test_394_coil_tune_probe.py; the DB / scan / rendered-handler halves are in
# test_consolidation_scan_timeout.py Part D.

def _gap_bars(closes, *, opens=None, hl=0.01):
    """Bars with an explicit open series (default open = the close) and the live `o_missing` flag."""
    return [{"date": (_D0 + timedelta(days=k)).isoformat(),
             "o": c if opens is None else opens[k],
             "h": c * (1 + hl), "l": c * (1 - hl), "c": c, "v": 1_000_000.0, "o_missing": False}
            for k, c in enumerate(closes)]


def test_orderliness_is_p95_overnight_gap_over_atr14_pct():
    closes = [100.0] * 30
    opens = list(closes)
    opens[21:26] = [100.0, 100.0, 101.0, 100.0, 103.0]          # gaps 0,0,1,0,3 % vs the flat 100 close
    score, n, dropped = orderliness_score(_gap_bars(closes, opens=opens), 20, 25)
    assert (n, dropped) == (5, 0)
    # sorted gaps 0,0,0,1,3 -> P95 = 1 + (3-1)*0.8 = 2.6 %; TR = 2 (h-l, the +-1% band) -> ATR14% = 2.0
    assert score == pytest.approx(2.6 / 2.0)


def test_orderliness_second_hand_case_with_a_different_p95_and_atr():
    closes = [100.0] * 30
    opens = list(closes)
    opens[21:26] = [100.0, 101.0, 99.0, 100.0, 102.0]           # gaps 0,1,1,0,2 %
    score, n, _ = orderliness_score(_gap_bars(closes, opens=opens, hl=0.02), 20, 25)
    # sorted 0,0,1,1,2 -> P95 = 1 + (2-1)*0.8 = 1.8 %; TR = 4 (the +-2% band) -> ATR14% = 4.0
    assert n == 5 and score == pytest.approx(1.8 / 4.0)


def test_orderliness_window_is_strictly_after_the_anchor_and_stops_at_the_end_bar():
    closes = [100.0] * 30
    opens = list(closes)
    opens[20] = 110.0                                            # the anchor day's own gap: excluded
    opens[27] = 120.0                                            # after the end bar: excluded
    score, n, _ = orderliness_score(_gap_bars(closes, opens=opens), 20, 25)
    assert n == 5 and score == pytest.approx(0.0)


def test_orderliness_null_open_day_is_dropped_not_read_as_a_close_to_close_move():
    closes = [100.0] * 24 + [104.0] + [104.0] * 5
    bars = _gap_bars(closes)                                     # open == close, the NULL fallback
    bars[24]["o_missing"] = True                                 # close jumped 4 %, open unknown
    score, n, dropped = orderliness_score(bars, 20, 26)
    assert dropped == 1 and n == 5 and score == pytest.approx(0.0)


def test_orderliness_unscored_cases_return_none_never_a_made_up_number():
    bars = _gap_bars([100.0] * 30)
    assert orderliness_score(bars, 20, 22)[0] is None            # 2 usable gaps < 3
    assert orderliness_score(bars, 20, 23)[0] is not None        # 3 usable gaps = the floor
    assert orderliness_score(bars, 20, 20)[0] is None            # empty window
    assert orderliness_score(bars, None, 25)[0] is None
    assert orderliness_score(_gap_bars([100.0] * 12), 3, 10)[0] is None   # < 14 bars of history: no ATR14


def test_db_rows_to_bars_flags_a_null_open_and_keeps_a_float_open():
    raw = [{"trade_date": date(2026, 7, 1), "open_price": None, "high_price": 11, "low_price": 9,
            "close": 10, "volume": 5},
           {"trade_date": date(2026, 7, 2), "open_price": 10.5, "high_price": 11, "low_price": 9,
            "close": 10, "volume": 5}]
    b = db_rows_to_bars(raw)
    assert b[0]["o_missing"] is True and b[0]["o"] == 10.0
    assert b[1]["o_missing"] is False and b[1]["o"] == 10.5


def _flat_coil_bars(*, gappy_days=()):
    """55 bars: a +30% leg (peak idx 39) then 15 flat coil days at 125. Every open = the prior close
    (zero gap) except `gappy_days`, which open +1.0% above the flat 125 close."""
    closes = _BASE + _RUNUP + [125.0] * 15
    opens = [closes[0]] + closes[:-1]
    for d in gappy_days:
        opens[d] = 125.0 * 1.01
    return _gap_bars(closes, opens=opens)


def test_held_coil_row_carries_the_hand_computed_orderliness():
    bars = _flat_coil_bars(gappy_days=(45, 49, 52))
    row, reject = evaluate_coil_consolidation(bars)
    assert reject is None and row is not None and row["anchor_date"] == bars[39]["date"]
    # 15 coil-window gaps: twelve 0 and three 1.0 % -> P95 = 1.0 %; ATR14% = 2.5/125 = 2.0 %
    assert row["orderliness"] == pytest.approx(0.5)
    assert row["orderliness"] == orderliness_score(bars, 39, len(bars) - 1)[0]


def test_a_calm_coil_scores_zero_not_none():
    row, _ = evaluate_coil_consolidation(_flat_coil_bars())
    assert row["orderliness"] == pytest.approx(0.0)


def test_orderliness_changes_nothing_but_its_own_key(monkeypatch, caplog):
    """The display score must be unable to alter admission: with the scorer working, returning None,
    or RAISING, the held coil is admitted and every other field is identical. A raise is logged
    (loud), not swallowed silently, and not allowed to reject the coil."""
    import agents.market_intelligence.anticipation as ant
    bars = _flat_coil_bars(gappy_days=(45, 49, 52))
    base, _ = evaluate_coil_consolidation(bars)

    def _without(row):
        return {k: v for k, v in row.items() if k != "orderliness"}

    monkeypatch.setattr(ant, "orderliness_score", lambda *a, **kw: (None, 0, 0))
    unscored, rej = evaluate_coil_consolidation(bars)
    assert rej is None and unscored["orderliness"] is None
    assert _without(unscored) == _without(base)

    def boom(*a, **kw):
        raise ZeroDivisionError("degenerate bar")

    monkeypatch.setattr(ant, "orderliness_score", boom)
    with caplog.at_level(logging.WARNING, logger=ant.logger.name):
        failed, rej = evaluate_coil_consolidation(bars)
    assert rej is None and failed is not None, "a scoring failure must never reject a held coil"
    assert failed["orderliness"] is None and _without(failed) == _without(base)
    assert any("orderliness unscored" in r.getMessage() for r in caplog.records)


def test_rejected_coil_stays_rejected_and_never_reaches_the_scorer(monkeypatch):
    """A deep give-back (> 50% of the leg) is rejected by the hold gate exactly as before, and the
    scorer is not even called for it."""
    import agents.market_intelligence.anticipation as ant
    called = []
    monkeypatch.setattr(ant, "orderliness_score", lambda *a, **kw: called.append(1) or (0.0, 5, 0))
    row, reject = evaluate_coil_consolidation(_series(108.0))
    assert row is None and reject is None and called == []


def test_orderliness_phrase_is_plain_words_and_absent_when_unscored():
    assert format_orderliness(0.8) == "overnight gaps 0.8× daily range"
    assert format_orderliness(0.0) == "overnight gaps 0.0× daily range"      # calm is a reading, not a gap
    assert format_orderliness(None) is None


def test_coiling_board_line_shows_it_last_and_the_rest_of_the_line_is_unchanged():
    kw = dict(ticker="LUNL", runup_ratio=1.7, coil_days=14, rmv_5d=10.0, fresh_tightening=True)
    plain = format_consolidation_row(**kw)
    assert plain == "  `LUNL ` +70% · coiling 14d · very tight · tightening↓"
    assert format_consolidation_row(**kw, orderliness=0.8) == plain + " · overnight gaps 0.8× daily range"
    assert format_consolidation_row(**kw, orderliness=None) == plain


def test_post_runup_board_line_shows_it_too():
    kw = dict(ticker="FUTU", runup_ratio=1.17, coil_days=15, coiled=False)
    assert format_consolidation_row(**kw) == "  `FUTU ` +17% · 15d since peak"
    assert (format_consolidation_row(**kw, orderliness=0.3)
            == "  `FUTU ` +17% · 15d since peak · overnight gaps 0.3× daily range")
