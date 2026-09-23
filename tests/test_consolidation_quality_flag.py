"""#327 shadow-fix §1/§2 (operator-signed 2026-07-14) — the quality-gate + stop-geometry helpers.

Pins the PURE readings the readiness scan records on every entry-shadow fire:
  1. quality_readings — point-in-time above-50SMA + 20-bar dollar-ADV (backward-only reads;
     insufficient history → None, never guessed);
  2. would_pass_quality_flag — stocks-only AND above-50SMA AND RS≥floor AND ADV≥$5M; a missing
     reading FAILS the flag (an unknown can't demonstrate a pass; components recorded alongside);
  3. stop_pct_of_entry + STOP_FLOOR_MIN_PCT — the sub-1% coiled_low geometry flag (min observed
     0.06% — noise stops that poison R math; diagnostic §4a).
FLAGS ONLY — the recorder writes pass and fail rows alike (A/B forward); the #327 entry gates
(is_entry_tight / entry_signal_at / confirm_signal_at) are untouched by this pack.
"""
import pytest

import agents.market_intelligence.anticipation as de


def _bar(c, v=1e6):
    return {"date": "d", "o": c, "h": c, "l": c, "c": c, "v": v}


# ── 1. quality_readings ────────────────────────────────────────────────────────
def test_above_50sma_true_on_rising_series():
    bars = [_bar(50.0 + 0.5 * i) for i in range(60)]     # rising → last close > 50-SMA
    q = de.quality_readings(bars, len(bars) - 1)
    assert q["above_50sma"] is True
    assert q["sma_50"] == pytest.approx(sum(50.0 + 0.5 * i for i in range(10, 60)) / 50, rel=1e-9)


def test_above_50sma_false_on_falling_series():
    bars = [_bar(100.0 - 0.5 * i) for i in range(60)]    # falling → last close < 50-SMA
    assert de.quality_readings(bars, len(bars) - 1)["above_50sma"] is False


def test_adv20_dollar_is_trailing_20_bar_mean_of_close_times_volume():
    bars = [_bar(10.0, v=1_000_000)] * 40 + [_bar(20.0, v=500_000)] * 20
    q = de.quality_readings(bars, len(bars) - 1)
    assert q["adv20_dollar"] == pytest.approx(20.0 * 500_000)   # only the last 20 bars count


def test_readings_none_on_insufficient_history():
    q = de.quality_readings([_bar(10.0)] * 30, 29)       # 30 bars: enough for ADV(20), not SMA(50)
    assert q["above_50sma"] is None and q["sma_50"] is None
    assert q["adv20_dollar"] == pytest.approx(10.0 * 1e6)
    q2 = de.quality_readings([_bar(10.0)] * 10, 9)       # 10 bars: neither
    assert q2["above_50sma"] is None and q2["adv20_dollar"] is None


def test_readings_are_point_in_time_backward_only():
    # readings at idx must ignore bars AFTER idx (same discipline as is_entry_tight)
    bars = [_bar(50.0 + 0.5 * i) for i in range(60)]
    base = de.quality_readings(bars, 55)
    assert de.quality_readings(bars + [_bar(1.0, v=1)] * 5, 55) == base


# ── 2. would_pass_quality_flag ─────────────────────────────────────────────────
_PASS = dict(is_common_stock=True, above_50sma=True, rs_composite=72.0, adv20_dollar=15e6)


def test_flag_passes_when_all_components_pass():
    assert de.would_pass_quality_flag(**_PASS) is True


@pytest.mark.parametrize("override", [
    {"is_common_stock": False},                  # ETF/ETP/warrant — stocks-only
    {"above_50sma": False},                      # sub-50SMA bear-bounce "coil"
    {"above_50sma": None},                       # unknown = cannot demonstrate a pass
    {"rs_composite": 50.0},                      # below the RS floor (65)
    {"rs_composite": None},                      # unscored (the diagnostic's ETFs were unscored)
    {"adv20_dollar": 400_000.0},                 # untradeable prints (SENEA $0.2M class)
    {"adv20_dollar": None},
])
def test_flag_fails_when_any_component_fails(override):
    assert de.would_pass_quality_flag(**{**_PASS, **override}) is False


def test_flag_floor_is_inclusive_at_the_boundary():
    assert de.would_pass_quality_flag(**{**_PASS, "rs_composite": de.QUALITY_RS_FLOOR}) is True
    assert de.would_pass_quality_flag(**{**_PASS, "adv20_dollar": de.QUALITY_ADV_DOLLAR_MIN}) is True


# ── 3. stop geometry (§2) ──────────────────────────────────────────────────────
def test_stop_pct_of_entry_basic_and_edges():
    assert de.stop_pct_of_entry(100.0, 98.0) == pytest.approx(2.0)
    assert de.stop_pct_of_entry(100.0, 99.94) == pytest.approx(0.06)   # the observed CNK minimum
    assert de.stop_pct_of_entry(None, 98.0) is None
    assert de.stop_pct_of_entry(0.0, 98.0) is None
    assert de.stop_pct_of_entry(100.0, None) is None


def test_sub1pct_floor_constant_flags_noise_stops():
    # the recorder flags sub1pct_reject = stop_pct(coiled_low) < STOP_FLOOR_MIN_PCT (1.0)
    assert de.stop_pct_of_entry(100.0, 99.5) < de.STOP_FLOOR_MIN_PCT       # 0.5% → flagged
    assert not (de.stop_pct_of_entry(100.0, 98.0) < de.STOP_FLOOR_MIN_PCT)  # 2.0% → clean
