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
    _FRESH_PIN_BAND_MAX,
    _FRESH_PIN_STICKY_SESSIONS,
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
_ATAI_SPEC = [
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
] + _flat(30, high=5.4, low=5.0, close=5.2, volume=8_000_000)

ATAI = _bars(_ATAI_SPEC)

# The most recent (newest) ATAI bar, reused to simulate later sessions still
# pinned. Prepending N of these to _ATAI_SPEC gives "the ATAI corpus as of N
# MORE sessions having elapsed" — the announcement bar (index 6) walks
# further back and, once it's pushed to combined-index >= 10, ages out of the
# _FRESH_PIN_VOL_EVENT_DAYS window (own-day conjunction stops firing) AND
# contaminates the baseline window with its own 165.6M-share volume,
# dragging the spike ratio down too. This reproduces the real 2026-07-30/31
# ATAI leak mechanically, not just by fixture-fiat — verified against the
# actual production replay (#502, docs/setups/htf.md change log).
_PIN_BAR = _ATAI_SPEC[0]


def _shifted(n_sessions: int, *, first_bar=None):
    """ATAI's corpus as of `n_sessions` additional pinned sessions later.
    `first_bar` overrides the newest (today's) bar only — used to test the
    release condition (today's band widening past _FRESH_PIN_BAND_MAX)."""
    prefix = [_PIN_BAR] * n_sessions
    if first_bar is not None and prefix:
        prefix[0] = first_bar
    elif first_bar is not None:
        prefix = [first_bar]
    return _bars(prefix + _ATAI_SPEC)


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


# ── STICKY carry (#502 refinement, 2026-08-06) ──────────────────────────────
# Bridges the measured 2-3 session hole between layer 3 aging out (the
# announcement volume event falls out of its 10-session window on session
# 11) and layer 2 (mature pin) reaching its 10-session median. ATAI leaked
# COILED on the real 07-30/07-31 sessions in exactly this hole.
#
# _shifted(0) == ATAI (own fires True, unchanged). shift 1-3 still fire on
# their OWN data (the announcement bar is still inside the 10-day event
# window). shift 4+ is where the own-day conjunction starts failing — the
# announcement bar has both aged out of the event window AND leaked into the
# baseline window, dragging the spike ratio down — reproducing the real
# 2026-07-30 leak mechanically, not by fixture-fiat.

def test_own_data_fire_is_unaffected_by_the_sticky_change():
    """Regression: sessions that already fired on their own data (shift 0-3)
    must be byte-identical to pre-2026-08-06 behaviour — sticky_from_session
    is 0 and nothing about the conjunction itself changed."""
    for n in range(0, 4):
        sig = _evaluate_fresh_pin(_shifted(n))
        assert sig["is_fresh_pin"] is True
        assert sig["sticky_from_session"] == 0


def test_sticky_bridges_the_measured_hole():
    """The bridge: a pin that fired on its own data 2 sessions ago, and whose
    band still holds today, is suppressed via the carry — reproduces the real
    ATAI 07-31 leak session (sticky_from_session=2 in the production replay)."""
    today = _shifted(5)
    sig = _evaluate_fresh_pin(today)
    assert sig["band_pct"] <= _FRESH_PIN_BAND_MAX      # still looks welded
    assert sig["is_fresh_pin"] is True
    assert sig["sticky_from_session"] == 2

    # Mutation check: revert to the pre-fix (own-data-only) code path via the
    # SAME shipped function's internal `_sticky` guard — this is the shipped
    # non-carrying evaluation, not a lookalike. Without the carry, this exact
    # row leaks through unsuppressed, proving the fix is load-bearing.
    own_only = _evaluate_fresh_pin(today, _sticky=True)
    assert own_only["is_fresh_pin"] is False


def test_sticky_release_condition_band_widening():
    """The release: once today's own band widens past _FRESH_PIN_BAND_MAX (the
    deal breaking / price moving again), stickiness lapses immediately — no
    carry is even attempted, regardless of a fired session in the lookback."""
    wide_bar = (9.50, 6.00, 7.50, 20_000_000)
    today = _shifted(5, first_bar=wide_bar)
    sig = _evaluate_fresh_pin(today)
    assert sig["band_pct"] > _FRESH_PIN_BAND_MAX
    assert sig["is_fresh_pin"] is False
    assert sig["sticky_from_session"] == 0


def test_sticky_bound_does_not_reach_past_the_configured_window():
    """The bound: a pin whose last OWN fire was 6 sessions back is NOT carried
    forward when _FRESH_PIN_STICKY_SESSIONS = 5 — the walk-back stops at 5 and
    never reaches it, even though the band still looks welded today."""
    assert _FRESH_PIN_STICKY_SESSIONS == 5, (
        "this test's shift arithmetic is calibrated to STICKY_SESSIONS=5; "
        "update the shift value if the constant changes"
    )
    today = _shifted(9)   # own-fire last happened at shift(3): 9 - 3 = 6 sessions back
    sig = _evaluate_fresh_pin(today)
    assert sig["band_pct"] <= _FRESH_PIN_BAND_MAX      # still welded — not a release
    assert sig["is_fresh_pin"] is False
    assert sig["sticky_from_session"] == 0


def test_sticky_fails_open_on_short_history():
    """A carried lookup that runs out of history (rows[i:] too short) must
    resolve to None internally and simply not contribute a hit — never raise,
    never suppress."""
    short = _bars(_flat(12, high=10.02, low=10.0, close=10.01, volume=1_000))
    # 12 rows is enough for ONE own-data evaluation (needs >= 11) but a walk
    # of 5 sessions back runs out of history well before the window closes.
    sig = _evaluate_fresh_pin(short)
    assert sig is not None
    assert sig["is_fresh_pin"] is False
    assert sig["sticky_from_session"] == 0


def test_sticky_never_recurses_past_one_level(monkeypatch):
    """No recursion blow-up: even a pathologically large sticky window is
    bounded to ONE extra call per lookback session (the `_sticky=True` guard
    prevents a carried check from itself trying to carry), so this must
    complete instantly regardless of the configured window size."""
    import agents.market_intelligence.flag_detector as fd
    monkeypatch.setattr(fd, "_FRESH_PIN_STICKY_SESSIONS", 5_000)
    # shift(5) only has real history for a handful of sessions behind it;
    # with a 5000-session walk-back this exercises thousands of _sticky=True
    # calls hitting the "not enough history" guard. No RecursionError, no
    # hang, and the true (session-2) hit still wins.
    sig = fd._evaluate_fresh_pin(_shifted(5))
    assert sig["is_fresh_pin"] is True
    assert sig["sticky_from_session"] == 2


def test_sticky_source_string_is_distinct_from_own_fire():
    """The audit-facing distinction the SSoT requires: a carried verdict must
    be identifiable as such (sticky_from_session > 0) separately from a
    verdict that fired on its own data (== 0), so the two stay separately
    auditable per the change log's discipline."""
    own = _evaluate_fresh_pin(ATAI)
    carried = _evaluate_fresh_pin(_shifted(5))
    assert own["sticky_from_session"] == 0
    assert carried["sticky_from_session"] == 2
    assert own["sticky_from_session"] != carried["sticky_from_session"]
