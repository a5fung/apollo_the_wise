"""FIX 3 (2026-08-26) — `_rs_rising` must reflect the trajectory, not two endpoints.

The defect: `hist[0] > hist[-1]` compares the newest reading to the oldest one and is blind
to everything between, so a collapse whose OLDEST reading happens to be a one-day trough
scores as RISING. Verified in prod: BLDR on 2026-08-25 read
`[10.0, 13.8, 25.7, 29.4, 29.2, 5.9]` — a 29 -> 10 collapse — and the nightly quality check
flagged it as "pruned while rising".

The fix adds ONE clause: today must not sit below EVERY intermediate reading, i.e. the
"rise" may not rest entirely on the single oldest anchor point.

⚠ These tests pin BOTH directions, because the risk of over-fixing is real and measured:
the hold exists to stop pruning genuine ignitions (IREN + APLD, 2026-07-22, #368), and four
broader shape tests were measured and REJECTED for breaking exactly that. See
`theme_engine._rs_rising`'s docstring and
`scripts/probes/_rs_rising_shape_replay_2026-08-26.py`.
"""
from agents.market_intelligence.theme_engine import (
    PRUNE_HOLD_MIN_POINTS,
    _rs_rising,
)

# ── prod-recorded histories, newest-first (docs/analysis/theme_mass_eviction_2026-08-26.md
#    and scripts/probes/_rs_rising_shape_replay_out.txt) ───────────────────────────────────
BLDR_0825 = [10.0, 13.8, 25.7, 29.4, 29.2, 5.9]     # 29 -> 10 collapse; oldest is a trough
BRUN_0820 = [12.2, 70.7, 71.6, 66.4, 36.6, 5.3]     # 71 -> 12 collapse, same shape
MPWR_0820 = [17.7, 26.9, 32.6, 36.3, 30.7, 14.7]    # 36 -> 18 collapse
IREN_0722 = [10.7, 7.4, 6.0, 1.5, 1.7, 2.4]         # verified TRUE ignition
APLD_0722 = [10.3, 8.9, 5.5, 3.1, 3.3, 4.5]         # verified TRUE ignition
SO_0826 = [22.1, 23.9, 24.4, 11.9, 19.9, 15.9]      # chop, but genuinely up over the window
ATO_0826 = [28.4, 24.2, 22.5, 15.8, 21.4, 15.6]


# ── the direction being FIXED: collapses must stop reading as rising ─────────────────────

def test_FAILS_WITHOUT_FIX_bldr_collapse_is_not_rising():
    """The recorded false-flag case. 10.0 > 5.9 is true, so the endpoint-only test said
    RISING; every other reading in the window is above 10.0, so the whole 'rise' rests on
    the single oldest point."""
    assert _rs_rising(BLDR_0825) is False


def test_FAILS_WITHOUT_FIX_other_recorded_collapses_are_not_rising():
    for hist in (BRUN_0820, MPWR_0820):
        assert _rs_rising(hist) is False, hist


def test_the_rejected_shape_is_specifically_the_lone_oldest_anchor():
    """Pin WHY each is rejected — today below every intermediate reading — so a future
    edit that rejects them for some broader reason (and takes true holds with it) still
    fails this test."""
    for hist in (BLDR_0825, BRUN_0820, MPWR_0820):
        assert hist[0] > hist[-1], "endpoint test still passes — that IS the defect"
        assert hist[0] < min(hist[1:-1]), hist


# ── the direction that must NOT break: genuine ignitions stay held ───────────────────────

def test_verified_ignitions_iren_and_apld_are_still_rising():
    """The DoD. These two were pruned from 'AI Compute & GPU Data Center Hosting
    Operators' on 2026-07-22 while igniting — the case #368's hold was built for. A fix
    that stops holding them has broken the mechanism it was meant to repair."""
    assert _rs_rising(IREN_0722) is True
    assert _rs_rising(APLD_0722) is True


def test_genuine_uptrend_through_chop_is_still_rising():
    """Honest scope: a sawtooth that is genuinely higher than it was is STILL rising, and
    the fix does not pretend otherwise. SO and ATO read rising before and after."""
    assert _rs_rising(SO_0826) is True
    assert _rs_rising(ATO_0826) is True


def test_the_fix_can_only_ever_narrow_the_hold():
    """Structural guarantee: the new clause is a conjunction on top of the old test, so no
    history the old test PRUNED can be newly HELD. That is what keeps the change from
    admitting junk — measured as 0 newly-held episodes over 645 in the replay."""
    histories = [
        BLDR_0825, BRUN_0820, MPWR_0820, IREN_0722, APLD_0722, SO_0826, ATO_0826,
        [5.0, 9.0, 8.0, 4.0], [1.0, 2.0, 3.0, 4.0], [4.0, 3.0, 2.0, 1.0],
        [10.0, 10.0, 10.0, 10.0], [50.0, 1.0, 1.0, 1.0, 1.0, 0.5],
    ]
    for hist in histories:
        old_verdict = len(hist) >= PRUNE_HOLD_MIN_POINTS and hist[0] > hist[-1]
        if _rs_rising(hist):
            assert old_verdict is True, f"{hist} newly held — the fix must only narrow"


# ── unchanged legs ───────────────────────────────────────────────────────────────────────

def test_short_history_still_fails_closed():
    assert _rs_rising([]) is False
    assert _rs_rising([9.0, 1.0]) is False
    assert _rs_rising([9.0, 5.0, 1.0]) is False          # 3 points, one short
    assert _rs_rising([9.0, 5.0, 3.0, 1.0]) is True      # exactly PRUNE_HOLD_MIN_POINTS


def test_flat_and_falling_still_prune():
    assert _rs_rising([10.0, 10.0, 10.0, 10.0]) is False   # strict `>`, unchanged
    assert _rs_rising([4.0, 6.0, 8.0, 10.0]) is False      # falling over the window


def test_oldest_point_is_excluded_from_the_floor_not_included():
    """`hist[1:-1]`, never `hist[1:]`. The oldest reading is the value being compared
    AGAINST; if it also served as the floor the clause would be vacuous (hist[0] > hist[-1]
    already implies hist[0] > min including it whenever the oldest is the minimum)."""
    # oldest is the unique minimum AND today is below everything else -> rejected
    assert _rs_rising([10.0, 20.0, 30.0, 1.0]) is False
    # same numbers, but today clears the interior floor -> still held
    assert _rs_rising([21.0, 20.0, 30.0, 1.0]) is True
