"""#502 — fresh deal-pin suppression on the HTF/flag actionable stages.

Operator-signed 2026-07-24. A cash-deal pin is mechanically indistinguishable
from a coil: the tightness that scores it COILED IS the pin. The pre-existing
Layer-3 rule needs a 10-session median under 0.5%, which a days-old deal cannot
reach, so ATAI/CCRN/PAYO leaked as actionable setups and were never caught.

The fresh rule is a two-axis conjunction — narrow price band AND a preceding
announcement-sized volume event. These tests pin the real boundary cases from
the 405-row replay in docs/analysis/htf_deal_pin_fresh_2026-07-24.md.
"""
import pytest

from agents.market_intelligence.flag_detector import (
    _DEAL_PIN_LOOKBACK_DAYS,
    _FRESH_PIN_VOL_BASE_END,
    _FRESH_PIN_VOL_BASE_START,
    _FRESH_PIN_VOL_EVENT_DAYS,
    _evaluate_deal_pin,
    _evaluate_fresh_pin,
)


def _bars(spec):
    """spec: list of (high, low, close, volume), newest-first."""
    return [
        {"rn": i + 1, "high_price": h, "low_price": lo, "close": c, "volume": v}
        for i, (h, lo, c, v) in enumerate(spec)
    ]


def _flat(n, *, high, low, close, volume):
    return [(high, low, close, volume)] * n


# ── ATAI 2026-07-24, the case that triggered this: band 1.53%, spike ~19x ──
ATAI = _bars(
    [
        (7.19, 7.1607, 7.18, 6_956_492),
        (7.20, 7.15, 7.17, 9_035_012),
        (7.19, 7.14, 7.18, 10_971_702),
        (7.21, 7.13, 7.135, 13_794_681),
        (7.21, 7.10, 7.19, 22_277_497),
        (7.22, 7.08, 7.22, 41_794_258),
        (7.22, 7.02, 7.15, 165_634_412),   # the announcement bar
        (5.76, 5.30, 5.36, 6_141_063),
        (5.77, 4.97, 5.67, 11_463_617),
        (5.10, 4.81, 4.97, 7_854_859),
    ]
    + _flat(30, high=5.4, low=5.0, close=5.2, volume=8_000_000)
)

# ── HUM 2026-05-28: band 3.07%, spike 1.0x — then ran +25.7%. Must NOT fire. ──
HUM = _bars(
    _flat(5, high=312.0, low=303.0, close=308.7, volume=1_000_000)
    + _flat(35, high=310.0, low=304.0, close=307.0, volume=1_000_000)
)


def test_atai_fires_the_fresh_pin():
    sig = _evaluate_fresh_pin(ATAI)
    assert sig is not None
    assert sig["is_fresh_pin"] is True
    assert sig["band_pct"] <= 0.025
    assert sig["vol_spike_x"] >= 5.0


def test_atai_does_not_fire_the_mature_rule():
    """The whole point: the pre-existing rule structurally cannot reach it."""
    sig = _evaluate_deal_pin(ATAI[:_DEAL_PIN_LOOKBACK_DAYS])
    assert sig["is_pin"] is False


def test_hum_is_preserved():
    """Nearest non-pin by band; it went on to +25.7%. Suppressing it is the
    one outcome this rule must never produce."""
    sig = _evaluate_fresh_pin(HUM)
    assert sig is not None
    assert sig["is_fresh_pin"] is False
    assert sig["vol_spike_x"] < 5.0


def test_narrow_band_without_volume_event_is_not_a_pin():
    """A quiet coil is narrow too — the band alone must not suppress."""
    quiet = _bars(_flat(40, high=100.5, low=99.5, close=100.0, volume=1_000_000))
    sig = _evaluate_fresh_pin(quiet)
    assert sig["band_pct"] <= 0.025          # narrow
    assert sig["is_fresh_pin"] is False      # but no event


def test_volume_event_without_narrow_band_is_not_a_pin():
    """A gapper is heavy too — the spike alone must not suppress."""
    gapper = _bars(
        [(120.0, 100.0, 118.0, 50_000_000)]
        + _flat(4, high=115.0, low=98.0, close=110.0, volume=9_000_000)
        + _flat(35, high=101.0, low=99.0, close=100.0, volume=1_000_000)
    )
    sig = _evaluate_fresh_pin(gapper)
    assert sig["vol_spike_x"] >= 5.0         # heavy
    assert sig["is_fresh_pin"] is False      # but wide


@pytest.mark.parametrize("n_rows", [0, 1, 4, 9, 10])
def test_insufficient_history_fails_open(n_rows):
    """A missing signature must never suppress — caller treats None as pass."""
    assert _evaluate_fresh_pin(
        _bars(_flat(n_rows, high=10.1, low=10.0, close=10.05, volume=1_000))
    ) is None


def test_degenerate_volume_fails_open():
    """Every unjudgeable volume shape must resolve to None (= no suppression),
    never to a spurious pin. All three shapes below are narrow-band, so a
    mishandled volume path would suppress rather than pass."""
    # adv == 0
    assert _evaluate_fresh_pin(
        _bars(_flat(40, high=10.02, low=10.0, close=10.01, volume=0))
    ) is None
    # no volume anywhere in the event window
    rows = _bars(_flat(40, high=10.02, low=10.0, close=10.01, volume=1_000))
    for r in rows[:_FRESH_PIN_VOL_EVENT_DAYS]:
        r["volume"] = None
    assert _evaluate_fresh_pin(rows) is None
    # no volume anywhere in the baseline window
    rows = _bars(_flat(40, high=10.02, low=10.0, close=10.01, volume=1_000))
    for r in rows[_FRESH_PIN_VOL_BASE_START - 1:_FRESH_PIN_VOL_BASE_END]:
        r["volume"] = None
    assert _evaluate_fresh_pin(rows) is None


def test_mature_rule_behaviour_is_unchanged():
    """The fresh rule is additive — KALV-class mature pins keep firing."""
    kalv = _bars(_flat(_DEAL_PIN_LOOKBACK_DAYS,
                       high=26.75, low=26.69, close=26.72, volume=500_000))
    assert _evaluate_deal_pin(kalv)["is_pin"] is True
