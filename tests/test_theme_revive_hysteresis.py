"""ADR 0007 (b/d) — Fading-theme revive hysteresis.

The 2026-05-31 replay quantified the oscillation risk: a naive "revive if ANY member
rs_1m>=90" rule would fire on 86/327 = 26% of May Fading-theme-days. These tests pin
that the hysteresis (>=2 hot members + cooldown latch + Fading-only) collapses that.
"""
from agents.market_intelligence.theme_engine import _should_revive_theme


def test_single_hot_member_does_not_revive():
    # the 26% trigger was single-member — requiring >=2 hot kills it
    assert _should_revive_theme("Fading", [100, 19]) is False   # {SWMR hot, KYTX cold}


def test_drone_fragment_alone_does_not_self_revive():
    # {KYTX,SWMR}: only SWMR hot -> must gain hot members via accelerator assignment first
    assert _should_revive_theme("Fading", [100.0, 18.4]) is False


def test_two_hot_members_revives():
    assert _should_revive_theme("Fading", [95, 92]) is True


def test_cooldown_latch_blocks_recent_revive():
    # even with 2 hot members, a revive within the cooldown window is blocked (anti-oscillation)
    assert _should_revive_theme("Fading", [95, 92], days_since_last_revive=3) is False
    assert _should_revive_theme("Fading", [95, 92], days_since_last_revive=11) is True


def test_only_fading_revives():
    for stage in ("Nascent", "Accelerating", "Mainstream", "Retired"):
        assert _should_revive_theme(stage, [99, 98, 97]) is False


def test_none_safe_and_empty():
    assert _should_revive_theme("Fading", []) is False
    assert _should_revive_theme("Fading", [None, None, 99]) is False  # only 1 real hot


def test_thresholds_tunable():
    # looser hot bar / single-member allowance is possible but is the WRONG (26%) setting —
    # the default min_hot_members=2 is the anti-oscillation choice.
    assert _should_revive_theme("Fading", [100, 19], min_hot_members=1) is True
